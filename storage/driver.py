# storage/driver.py
"""
单写者队列 SQLite 驱动 - 修复版
使用哨兵模式平滑关闭，不丢失任何写入
"""

import os
import asyncio
import logging
import sqlite3
from typing import Any, List, Tuple, Optional, Dict

logger = logging.getLogger("Atlas.Storage")

class StorageFullError(Exception):
    pass

class StorageError(Exception):
    pass

# 哨兵对象
_SENTINEL = object()


class SingleWriterStorage:
    def __init__(
        self,
        db_path: str,
        max_queue_size: int = 1000,
        busy_timeout: int = 5000,
        batch_size: int = 100,
        batch_delay_ms: int = 50,
    ):
        self.db_path = db_path
        self.max_queue_size = max_queue_size
        self.busy_timeout = busy_timeout
        self._batch_size = batch_size
        self._batch_delay_ms = batch_delay_ms

        self._write_queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self._writer_task: Optional[asyncio.Task] = None
        self._running = False
        self._readonly_mode = False

        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    def set_batch_delay(self, delay_ms: int) -> None:
        self._batch_delay_ms = delay_ms

    async def start(self) -> None:
        if self._running:
            return
        await self._init_database()
        self._running = True
        self._writer_task = asyncio.create_task(self._writer_loop())
        logger.info(f"Storage driver started: {self.db_path}, queue_size={self.max_queue_size}")

    async def _init_database(self) -> None:
        loop = asyncio.get_running_loop()
        def _init():
            conn = sqlite3.connect(self.db_path, timeout=self.busy_timeout / 1000.0)
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute(f"PRAGMA busy_timeout={self.busy_timeout};")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute("PRAGMA wal_autocheckpoint=1000;")
                self._create_tables(conn)
                conn.commit()
            finally:
                conn.close()
        await loop.run_in_executor(None, _init)

    def _create_tables(self, conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL,
                source TEXT NOT NULL,
                type TEXT NOT NULL,
                payload BLOB,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_trace ON events(trace_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value BLOB,
                version INTEGER DEFAULT 1,
                updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS resource_locks (
                resource TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                acquired_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshot (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                data BLOB NOT NULL,
                checksum TEXT NOT NULL,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dead_letters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_data BLOB NOT NULL,
                error TEXT,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            )
        """)

    async def execute_write(self, sql: str, params: Tuple[Any, ...] = ()) -> Any:
        if self._readonly_mode:
            raise StorageError("Storage is in read-only mode")
        future = asyncio.get_running_loop().create_future()
        await self._write_queue.put(("write", sql, params, future))
        return await future

    async def execute_write_many(self, sql: str, params_list: List[Tuple[Any, ...]]) -> int:
        if self._readonly_mode:
            raise StorageError("Storage is in read-only mode")
        future = asyncio.get_running_loop().create_future()
        await self._write_queue.put(("many", sql, params_list, future))
        return await future

    async def execute_read(self, sql: str, params: Tuple[Any, ...] = ()) -> List[Tuple[Any, ...]]:
        loop = asyncio.get_running_loop()
        def _read():
            conn = sqlite3.connect(self.db_path, timeout=self.busy_timeout / 1000.0)
            try:
                conn.execute(f"PRAGMA busy_timeout={self.busy_timeout};")
                cursor = conn.execute(sql, params)
                return cursor.fetchall()
            finally:
                conn.close()
        return await loop.run_in_executor(None, _read)

    async def _writer_loop(self) -> None:
        """写循环：持续消费队列，遇到哨兵则退出"""
        while self._running:
            batch = []
            try:
                item = await asyncio.wait_for(
                    self._write_queue.get(),
                    timeout=self._batch_delay_ms / 1000.0
                )
                if item is _SENTINEL:
                    self._write_queue.task_done()
                    break
                batch.append(item)
            except asyncio.TimeoutError:
                continue

            while len(batch) < self._batch_size and not self._write_queue.empty():
                item = self._write_queue.get_nowait()
                if item is _SENTINEL:
                    self._write_queue.task_done()
                    await self._write_queue.put(_SENTINEL)
                    break
                batch.append(item)

            if not batch:
                continue

            conn = None
            try:
                conn = sqlite3.connect(self.db_path, timeout=self.busy_timeout / 1000.0)
                conn.execute(f"PRAGMA busy_timeout={self.busy_timeout};")
                results = []
                for item in batch:
                    mode, sql, params_arg, future = item
                    if mode == "write":
                        cursor = conn.execute(sql, params_arg)
                        results.append(cursor.lastrowid)
                    elif mode == "many":
                        cursor = conn.executemany(sql, params_arg)
                        results.append(cursor.rowcount)
                    else:
                        raise ValueError(f"Unknown mode: {mode}")
                conn.commit()
                for idx, item in enumerate(batch):
                    future = item[3]
                    if not future.done():
                        future.set_result(results[idx])
            except Exception as e:
                if conn:
                    conn.rollback()
                for item in batch:
                    future = item[3]
                    if not future.done():
                        future.set_exception(StorageError(f"Writer loop error: {e}"))
            finally:
                if conn:
                    conn.close()
                for _ in batch:
                    self._write_queue.task_done()

        # 处理剩余队列
        while not self._write_queue.empty():
            item = self._write_queue.get_nowait()
            if item is _SENTINEL:
                self._write_queue.task_done()
                continue
            mode, sql, params_arg, future = item
            future.set_exception(StorageError("Storage stopped before write completed"))
            self._write_queue.task_done()
        logger.info("Writer loop exited")

    async def checkpoint(self, full: bool = False) -> None:
        if self._readonly_mode:
            return
        loop = asyncio.get_running_loop()
        def _checkpoint():
            conn = sqlite3.connect(self.db_path, timeout=self.busy_timeout / 1000.0)
            try:
                if full:
                    conn.execute("PRAGMA wal_checkpoint(FULL);")
                else:
                    conn.execute("PRAGMA wal_checkpoint(PASSIVE);")
                conn.commit()
            finally:
                conn.close()
        await loop.run_in_executor(None, _checkpoint)

    async def vacuum(self) -> None:
        if self._readonly_mode:
            return
        loop = asyncio.get_running_loop()
        def _vacuum():
            conn = sqlite3.connect(self.db_path, timeout=self.busy_timeout / 1000.0)
            try:
                conn.execute("VACUUM;")
                conn.commit()
            finally:
                conn.close()
        await loop.run_in_executor(None, _vacuum)

    async def set_readonly_mode(self, enabled: bool) -> None:
        self._readonly_mode = enabled
        logger.warning(f"Read-only mode {'enabled' if enabled else 'disabled'}")

    async def get_disk_usage(self) -> Dict[str, int]:
        import shutil
        stat = shutil.disk_usage(os.path.dirname(self.db_path))
        return {
            "total": stat.total,
            "used": stat.used,
            "free": stat.free,
            "free_mb": stat.free // (1024 * 1024),
        }

    async def stop(self) -> None:
        """优雅关闭：发送哨兵，等待写线程自然结束"""
        self._running = False
        try:
            await self._write_queue.put(_SENTINEL)
        except asyncio.QueueFull:
            self._write_queue.put_nowait(_SENTINEL)

        if self._writer_task:
            try:
                await asyncio.wait_for(self._writer_task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.error("Writer task stop timeout, forcing cancel")
                self._writer_task.cancel()
                try:
                    await self._writer_task
                except asyncio.CancelledError:
                    pass
        logger.info("Storage driver stopped")