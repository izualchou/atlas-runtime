# core/resource_lock.py
"""
资源锁（Resource Lock）

职责：
1. 资源互斥锁（持久化到 SQLite）
2. 支持 TTL（租约）
3. 支持重入（同一任务可多次获取）
4. 启动时清理过期的孤儿锁

关联修复：E14（孤儿锁清理）
"""

import time
import logging
import asyncio
from typing import Optional
from storage.driver import SingleWriterStorage

logger = logging.getLogger("Atlas.ResourceLock")


class ResourceLock:
    def __init__(self, storage: SingleWriterStorage):
        self.storage = storage
        self._lock = asyncio.Lock()  # 内存锁防止并发写冲突

    async def try_acquire(self, resource: str, owner: str, ttl: int = 60) -> bool:
        """
        尝试获取资源锁
        
        Args:
            resource: 资源名
            owner: 持有者标识（通常是 task_id）
            ttl: 租约时间（秒）
        
        Returns:
            是否成功获取
        """
        async with self._lock:
            # 查询当前锁
            rows = await self.storage.execute_read(
                "SELECT owner, expires_at FROM resource_locks WHERE resource = ?",
                (resource,)
            )

            now = int(time.time())

            if rows:
                owner_current, expires_at = rows[0]
                if owner_current == owner:
                    # 重入：更新过期时间
                    await self.storage.execute_write(
                        "UPDATE resource_locks SET expires_at = ? WHERE resource = ?",
                        (now + ttl, resource)
                    )
                    logger.debug(f"Lock re-acquired for {resource} by {owner}")
                    return True

                if expires_at > now:
                    # 锁仍有效，被其他持有者占用
                    return False

                # 锁已过期，覆盖
                await self.storage.execute_write(
                    "UPDATE resource_locks SET owner = ?, acquired_at = ?, expires_at = ? "
                    "WHERE resource = ?",
                    (owner, now, now + ttl, resource)
                )
                logger.info(f"Lock overwritten for expired {resource} by {owner}")
                return True
            else:
                # 无锁，插入
                await self.storage.execute_write(
                    "INSERT INTO resource_locks (resource, owner, acquired_at, expires_at) "
                    "VALUES (?, ?, ?, ?)",
                    (resource, owner, now, now + ttl)
                )
                logger.debug(f"Lock acquired for {resource} by {owner}")
                return True

    async def release(self, resource: str, owner: str) -> bool:
        """释放资源锁"""
        async with self._lock:
            rows = await self.storage.execute_read(
                "SELECT owner FROM resource_locks WHERE resource = ?",
                (resource,)
            )
            if not rows:
                return False

            if rows[0][0] != owner:
                logger.warning(f"Attempt to release lock {resource} by non-owner {owner}")
                return False

            await self.storage.execute_write(
                "DELETE FROM resource_locks WHERE resource = ? AND owner = ?",
                (resource, owner)
            )
            logger.debug(f"Lock released for {resource} by {owner}")
            return True

    async def renew(self, resource: str, owner: str, ttl: int = 60) -> bool:
        """续约锁（延长租约）"""
        async with self._lock:
            rows = await self.storage.execute_read(
                "SELECT owner FROM resource_locks WHERE resource = ?",
                (resource,)
            )
            if not rows or rows[0][0] != owner:
                return False

            now = int(time.time())
            await self.storage.execute_write(
                "UPDATE resource_locks SET expires_at = ? WHERE resource = ? AND owner = ?",
                (now + ttl, resource, owner)
            )
            return True

    async def clean_expired(self) -> int:
        """清理所有过期的锁（启动时调用）"""
        now = int(time.time())
        result = await self.storage.execute_write(
            "DELETE FROM resource_locks WHERE expires_at <= ?",
            (now,)
        )
        logger.info(f"Cleaned {result} expired locks")
        return result

    async def get_locks(self) -> dict:
        """获取当前所有锁（调试用）"""
        rows = await self.storage.execute_read(
            "SELECT resource, owner, expires_at FROM resource_locks"
        )
        return {row[0]: {"owner": row[1], "expires_at": row[2]} for row in rows}