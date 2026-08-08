# core/dedup.py
"""
去重过滤器（Dedup Filter）。

基于 correlation_id + TTL 的内存去重窗口，防止相同触发事件被重复处理。
在 FIFO 和 HTTP 双通道并存的场景下尤为重要——两个通道可能同时收到相同事件。

设计原则:
- 内存去重窗口：使用 OrderedDict + TTL，基于 correlation_id 去重
- 惰性过期清理：访问时清理而非后台轮询，零 CPU 持续开销
- 碰撞概率：key 为 64 位整数 hash，碰撞概率可忽略
- 容量安全：max_entries 上限防止内存无限增长

v9.1: 引入定期清理（每 100 次操作触发一次），避免长时间无请求导致条目堆积。
"""

import time
import hashlib
import logging
from collections import OrderedDict
from typing import Optional, Set

logger = logging.getLogger("Atlas.DedupFilter")


class DedupFilter:
    """
    基于 TTL 的内存去重过滤器。

    每个 correlation_id 在 TTL 窗口内只会记录一次，重复返回 True。
    使用 OrderedDict + 惰性清理实现 O(1) 查询与插入。

    Attributes:
        ttl: 去重窗口（秒），默认 60 秒
        max_entries: 最大条目数，默认 10000
    """

    def __init__(
        self,
        ttl: float = 60.0,
        max_entries: int = 10000,
    ):
        if ttl <= 0:
            raise ValueError(f"ttl must be > 0, got {ttl}")
        if max_entries < 1:
            raise ValueError(f"max_entries must be >= 1, got {max_entries}")

        self.ttl = ttl
        self.max_entries = max_entries

        # 内部存储: OrderedDict[hash_key, expire_time]
        self._entries: "OrderedDict[int, float]" = OrderedDict()
        self._operation_counter: int = 0

        # 统计
        self._total_checks: int = 0
        self._duplicates_found: int = 0
        self._expirations_cleaned: int = 0

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def is_duplicate(self, correlation_id: str) -> bool:
        """
        检查 correlation_id 是否在去重窗口内已出现。

        O(1) 查询，同时在入口触发惰性过期清理。

        Args:
            correlation_id: 关联 ID（如 trigger 的 correlation_id）

        Returns:
            True 如果已存在且未过期（重复），False 如果是新 ID
        """
        self._total_checks += 1
        self._operation_counter += 1

        key = self._hash_key(correlation_id)
        now = time.time()

        # 惰性清理：移除过期条目
        self._lazy_expire(now)

        # 检查是否存在且未过期
        if key in self._entries:
            expire_time = self._entries[key]
            if now < expire_time:
                self._duplicates_found += 1
                # 将命中的条目移到末尾（OrderedDict 不保证 LRU，这里显式操作）
                self._touch(key)
                logger.debug(f"Dedup: duplicate detected for {correlation_id[:20]}... (key={key})")
                return True
            else:
                # 已过期，移除
                del self._entries[key]
                self._expirations_cleaned += 1

        return False

    def mark_seen(self, correlation_id: str) -> None:
        """
        将 correlation_id 标记为已见。

        在确认非重复后调用，记录到去重窗口。

        Args:
            correlation_id: 关联 ID
        """
        self._operation_counter += 1

        key = self._hash_key(correlation_id)
        now = time.time()

        # 惰性清理
        self._lazy_expire(now)

        # 容量检查：如果已满，移除最旧的条目
        if len(self._entries) >= self.max_entries:
            oldest_key, _ = self._entries.popitem(last=False)
            logger.warning(
                f"Dedup: max entries ({self.max_entries}) reached, "
                f"evicting oldest entry (key={oldest_key})"
            )

        # 插入或更新
        self._entries[key] = now + self.ttl
        # 移到末尾表示最新
        self._touch(key)

        # 定期清理检查（每 100 次操作）
        if self._operation_counter >= 100:
            self._periodic_cleanup(now)
            self._operation_counter = 0

    def cleanup_expired(self) -> int:
        """
        显式清理所有已过期条目。

        Returns:
            清理的条目数
        """
        now = time.time()
        count = 0
        keys_to_remove = []

        for key, expire_time in self._entries.items():
            if now >= expire_time:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self._entries[key]
            count += 1

        if count > 0:
            self._expirations_cleaned += count
            logger.debug(f"Dedup: cleaned {count} expired entries, "
                        f"{len(self._entries)} remaining")

        return count

    def size(self) -> int:
        """返回当前条目数。"""
        return len(self._entries)

    def clear(self) -> None:
        """清空所有条目（用于测试）。"""
        self._entries.clear()
        self._operation_counter = 0
        self._total_checks = 0
        self._duplicates_found = 0
        self._expirations_cleaned = 0

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_key(correlation_id: str) -> int:
        """
        将 correlation_id 哈希为 64 位整数。

        使用 SHA-256 的前 8 字节，碰撞概率 ~2^-64，在 10000 条目下概率 < 10^-15。
        """
        digest = hashlib.sha256(correlation_id.encode('utf-8')).digest()
        # 取前 8 字节转为有符号 64 位整数
        return int.from_bytes(digest[:8], byteorder='big', signed=True)

    def _lazy_expire(self, now: float) -> None:
        """
        惰性过期清理：移除最旧的已过期条目。

        每次调用最多清理 50 个，防止单次调用耗时过长。
        """
        cleaned = 0
        keys_to_remove = []

        for key, expire_time in self._entries.items():
            if now >= expire_time:
                keys_to_remove.append(key)
                cleaned += 1
                if cleaned >= 50:
                    break
            else:
                # OrderedDict 按插入顺序遍历，
                # 最旧的条目在前面，遇到第一个未过期的即可停止
                break

        for key in keys_to_remove:
            del self._entries[key]

        if cleaned > 0:
            self._expirations_cleaned += cleaned

    def _touch(self, key: int) -> None:
        """将条目移到 OrderedDict 末尾（标记为最近使用）。"""
        if key in self._entries:
            self._entries.move_to_end(key)

    def _periodic_cleanup(self, now: float) -> None:
        """定期清理：当条目超过容量 80% 时，清理超过 TTL 2 倍的过期条目。"""
        threshold = int(self.max_entries * 0.8)
        if len(self._entries) < threshold:
            return

        extended_expiry = now + self.ttl * 2
        keys_to_remove = [
            key for key, expire_time in self._entries.items()
            if expire_time < extended_expiry
        ]

        for key in keys_to_remove:
            del self._entries[key]

        if keys_to_remove:
            self._expirations_cleaned += len(keys_to_remove)
            logger.info(
                f"Dedup: periodic cleanup removed {len(keys_to_remove)} entries, "
                f"{len(self._entries)} remaining (threshold={threshold})"
            )
