# storage/rotator.py
"""
事件表轮转器 - 修复版（P2 F5）
RETURNING 降级兼容 + 事务内原子操作
"""

import os
import gzip
import json
import logging
import asyncio
from typing import Optional
from datetime import datetime

logger = logging.getLogger("Atlas.Rotator")

class EventRotator:
    def __init__(
        self,
        storage,
        max_rows: int = 10000,
        archive_dir: Optional[str] = None,
        check_interval_hours: float = 6.0,
    ):
        self.storage = storage
        self.max_rows = max_rows
        self.archive_dir = archive_dir or os.path.join(os.getcwd(), "logs", "archive")
        self.check_interval = check_interval_hours * 3600
        self._task: Optional[asyncio.Task] = None
        self._running = False
        os.makedirs(self.archive_dir, exist_ok=True)

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._auto_rotate_loop())
        logger.info(f"Event rotator started, max_rows={self.max_rows}")

    async def _auto_rotate_loop(self):
        while self._running:
            try:
                await asyncio.sleep(self.check_interval)
                await self.rotate_if_needed()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Auto rotate error: {e}")

    async def rotate_if_needed(self) -> bool:
        count = await self._get_event_count()
        if count <= self.max_rows:
            return False

        delete_count = count - self.max_rows

        # 开启事务
        await self.storage.execute_write("BEGIN IMMEDIATE")
        try:
            rows = await self.storage.execute_read(
                "SELECT id, trace_id, source, type, payload, created_at "
                "FROM events ORDER BY id ASC LIMIT ?",
                (delete_count,)
            )
            if not rows:
                await self.storage.execute_write("COMMIT")
                return False

            cutoff_id = rows[-1][0]

            # 写入归档
            archive_path = self._generate_archive_path()
            try:
                await self._archive_rows(rows, archive_path)
            except Exception as e:
                logger.error(f"Failed to write archive file: {e}")
                await self.storage.execute_write("ROLLBACK")
                if os.path.exists(archive_path):
                    os.unlink(archive_path)
                return False

            # 删除旧数据（兼容 RETURNING）
            deleted_count = 0
            try:
                # 尝试使用 RETURNING（SQLite 3.35+）
                deleted_rows = await self.storage.execute_read(
                    "DELETE FROM events WHERE id <= ? RETURNING id",
                    (cutoff_id,)
                )
                deleted_count = len(deleted_rows)
            except Exception:
                # 降级：先查询后删除
                logger.warning("RETURNING not supported, using fallback")
                check = await self.storage.execute_read(
                    "SELECT COUNT(*) FROM events WHERE id <= ?",
                    (cutoff_id,)
                )
                expected = check[0][0] if check else 0
                await self.storage.execute_write(
                    "DELETE FROM events WHERE id <= ?",
                    (cutoff_id,)
                )
                deleted_count = expected

            await self.storage.execute_write("COMMIT")

            if deleted_count != len(rows):
                logger.warning(
                    f"Archived {len(rows)} rows, but deleted {deleted_count}. "
                    "Possible concurrent modifications."
                )
            else:
                logger.info(
                    f"Rotated {len(rows)} rows (max_id={cutoff_id}) to {archive_path}, "
                    f"deleted {deleted_count} rows"
                )

            # 回收空间
            await self.storage.checkpoint(full=True)
            return True

        except Exception as e:
            await self.storage.execute_write("ROLLBACK")
            logger.error(f"Rotate transaction failed: {e}")
            return False

    async def _get_event_count(self) -> int:
        result = await self.storage.execute_read("SELECT COUNT(*) FROM events")
        return result[0][0] if result else 0

    def _generate_archive_path(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(self.archive_dir, f"events_{timestamp}.json.gz")

    async def _archive_rows(self, rows: list, archive_path: str) -> None:
        loop = asyncio.get_running_loop()
        def _write():
            with gzip.open(archive_path, 'wt', encoding='utf-8') as f:
                f.write('[\n')
                for i, row in enumerate(rows):
                    obj = {
                        "id": row[0],
                        "trace_id": row[1],
                        "source": row[2],
                        "type": row[3],
                        "payload": row[4].hex() if isinstance(row[4], bytes) else row[4],
                        "created_at": row[5],
                    }
                    json.dump(obj, f)
                    if i < len(rows) - 1:
                        f.write(',\n')
                f.write('\n]\n')
        await loop.run_in_executor(None, _write)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Event rotator stopped")