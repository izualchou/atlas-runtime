# core/resource_lock.py
"""
资源锁 - 修复版
修复过期锁被清理后 UPDATE 0 行却返回 True 的竞态问题
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
        self._lock = asyncio.Lock()

    async def try_acquire(self, resource: str, owner: str, ttl: int = 60) -> bool:
        async with self._lock:
            now = int(time.time())

            # 1. 查询当前锁
            rows = await self.storage.execute_read(
                "SELECT owner, expires_at FROM resource_locks WHERE resource = ?",
                (resource,)
            )

            if rows:
                current_owner, expires_at = rows[0]

                # 重入：更新过期时间
                if current_owner == owner:
                    await self.storage.execute_write(
                        "UPDATE resource_locks SET expires_at = ? WHERE resource = ? AND owner = ?",
                        (now + ttl, resource, owner)
                    )
                    return True

                # 锁有效且不属于当前所有者
                if expires_at > now:
                    return False

                # 锁已过期，尝试抢占（CAS 条件更新）
                rowcount = await self.storage.execute_write(
                    "UPDATE resource_locks SET owner = ?, acquired_at = ?, expires_at = ? "
                    "WHERE resource = ? AND expires_at = ?",
                    (owner, now, now + ttl, resource, expires_at)
                )
                if rowcount > 0:
                    logger.debug(f"Lock acquired (overwrote expired) for {resource} by {owner}")
                    return True
                else:
                    # 说明在查询到更新之间被其他线程修改或删除，降级为尝试 INSERT
                    pass

            # 2. 尝试插入新锁（若已被其他线程插入，则失败）
            try:
                await self.storage.execute_write(
                    "INSERT INTO resource_locks (resource, owner, acquired_at, expires_at) "
                    "VALUES (?, ?, ?, ?)",
                    (resource, owner, now, now + ttl)
                )
                logger.debug(f"Lock acquired for {resource} by {owner}")
                return True
            except Exception as e:
                # 唯一约束冲突（资源已被其他人抢占）
                logger.debug(f"Lock insert failed for {resource}: {e}")
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