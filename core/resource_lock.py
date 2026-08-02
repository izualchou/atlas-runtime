# core/resource_lock.py
"""
资源锁 - 修复版
修复过期锁被清理后 UPDATE 0 行却返回 True 的竞态问题
使用 CAS (Compare-And-Swap) 乐观锁机制
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
        self._lock = asyncio.Lock()  # 内存锁，防止并发写冲突

    async def try_acquire(self, resource: str, owner: str, ttl: int = 60) -> bool:
        """
        尝试获取资源锁（CAS 乐观锁）
        1. 尝试插入新锁（若不存在）
        2. 若存在且已过期或持有者相同，则更新
        3. 每次操作检查 rowcount，避免假成功
        """
        async with self._lock:
            now = int(time.time())
            expires_at = now + ttl

            # 步骤1：尝试插入新锁
            try:
                rowcount = await self.storage.execute_write(
                    "INSERT INTO resource_locks (resource, owner, acquired_at, expires_at) "
                    "VALUES (?, ?, ?, ?)",
                    (resource, owner, now, expires_at)
                )
                if rowcount > 0:
                    logger.debug(f"Lock inserted for {resource} by {owner}")
                    return True
            except Exception:
                # 唯一约束冲突（资源已被其他锁占用），继续尝试抢占
                pass

            # 步骤2：尝试更新（仅当锁已过期或持有者相同时）
            rowcount = await self.storage.execute_write(
                """UPDATE resource_locks 
                   SET owner = ?, acquired_at = ?, expires_at = ? 
                   WHERE resource = ? AND (expires_at <= ? OR owner = ?)""",
                (owner, now, expires_at, resource, now, owner)
            )

            if rowcount > 0:
                logger.debug(f"Lock acquired for {resource} by {owner} via CAS update")
                return True

            # 步骤3：抢占失败，锁被其他有效持有者占用
            logger.debug(f"Lock acquisition failed for {resource} by {owner}")
            return False

    async def release(self, resource: str, owner: str) -> bool:
        async with self._lock:
            rowcount = await self.storage.execute_write(
                "DELETE FROM resource_locks WHERE resource = ? AND owner = ?",
                (resource, owner)
            )
            if rowcount > 0:
                logger.debug(f"Lock released for {resource} by {owner}")
            else:
                logger.warning(f"Release called for non-existent lock {resource} by {owner}")
            return rowcount > 0

    async def renew(self, resource: str, owner: str, ttl: int = 60) -> bool:
        async with self._lock:
            now = int(time.time())
            rowcount = await self.storage.execute_write(
                "UPDATE resource_locks SET expires_at = ? "
                "WHERE resource = ? AND owner = ?",
                (now + ttl, resource, owner)
            )
            if rowcount > 0:
                logger.debug(f"Lock renewed for {resource} by {owner}")
            else:
                logger.warning(f"Renew called for non-existent lock {resource} by {owner}")
            return rowcount > 0

    async def clean_expired(self) -> int:
        now = int(time.time())
        rowcount = await self.storage.execute_write(
            "DELETE FROM resource_locks WHERE expires_at <= ?",
            (now,)
        )
        logger.info(f"Cleaned {rowcount} expired locks")
        return rowcount

    async def get_locks(self) -> dict:
        rows = await self.storage.execute_read(
            "SELECT resource, owner, expires_at FROM resource_locks"
        )
        return {row[0]: {"owner": row[1], "expires_at": row[2]} for row in rows}