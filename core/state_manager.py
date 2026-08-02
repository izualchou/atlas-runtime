# core/state_manager.py
"""
状态管理器 - 修复版（P1 F4）
快照写入串行化，避免并发覆盖
"""

import asyncio
import logging
import copy
from typing import Any, Optional, Dict
from storage.snapshot import SnapshotManager

logger = logging.getLogger("Atlas.StateManager")


class StateManager:
    def __init__(
        self,
        snapshot_mgr: SnapshotManager,
        snapshot_interval: int = 30,
    ):
        self._snapshot_mgr = snapshot_mgr
        self._snapshot_interval = snapshot_interval

        self._lock = asyncio.Lock()
        self._data: Dict[str, Any] = {}
        self._versions: Dict[str, int] = {}

        self._running = False
        self._snapshot_task: Optional[asyncio.Task] = None
        self._pending_write_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True

        await self._restore_snapshot()
        self._snapshot_task = asyncio.create_task(self._snapshot_loop())
        logger.info("StateManager started")

    async def _restore_snapshot(self) -> None:
        data = await self._snapshot_mgr.read()
        if data is None:
            logger.info("No snapshot found, starting with empty state")
            return

        async with self._lock:
            self._data = data.get("data", {})
            self._versions = data.get("versions", {})
            logger.info(f"Restored snapshot with {len(self._data)} keys")

    async def _snapshot_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self._snapshot_interval)

                async with self._lock:
                    frozen = {
                        "data": copy.deepcopy(self._data),
                        "versions": copy.deepcopy(self._versions),
                    }

                # 如果已有待完成的写任务，等待它完成（串行化）
                if self._pending_write_task and not self._pending_write_task.done():
                    logger.debug("Waiting for pending snapshot write to complete")
                    await self._pending_write_task

                # 创建新的写任务
                self._pending_write_task = asyncio.create_task(
                    self._snapshot_mgr.write(frozen)
                )
                await self._pending_write_task

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Snapshot loop error: {e}")

    async def get(self, key: str, default: Any = None) -> Any:
        async with self._lock:
            return self._data.get(key, default)

    async def set(self, key: str, value: Any) -> None:
        async with self._lock:
            self._data[key] = value
            self._versions[key] = self._versions.get(key, 0) + 1

    async def set_many(self, items: Dict[str, Any]) -> None:
        async with self._lock:
            for key, value in items.items():
                self._data[key] = value
                self._versions[key] = self._versions.get(key, 0) + 1

    async def delete(self, key: str) -> bool:
        async with self._lock:
            if key in self._data:
                del self._data[key]
                self._versions.pop(key, None)
                return True
            return False

    async def get_version(self, key: str) -> Optional[int]:
        async with self._lock:
            return self._versions.get(key)

    async def get_all(self) -> Dict[str, Any]:
        async with self._lock:
            return copy.deepcopy(self._data)

    async def stop(self) -> None:
        self._running = False
        if self._snapshot_task:
            self._snapshot_task.cancel()
            try:
                await self._snapshot_task
            except asyncio.CancelledError:
                pass

        if self._pending_write_task and not self._pending_write_task.done():
            await self._pending_write_task

        async with self._lock:
            frozen = {
                "data": copy.deepcopy(self._data),
                "versions": copy.deepcopy(self._versions),
            }
        await self._snapshot_mgr.write(frozen)
        logger.info("StateManager stopped")