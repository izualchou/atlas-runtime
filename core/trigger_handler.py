# core/trigger_handler.py
"""
触发处理器（Trigger Handler）
职责：接收触发数据，提交到 Scheduler，背压控制，死信管理
"""

import asyncio
import logging
import time
import msgpack
from typing import Dict, Any
from models.errors import StorageFullError, BackpressureError

# 仅用于类型注解，避免循环导入
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.scheduler import Scheduler
    from storage.driver import AsyncSQLiteStorage

logger = logging.getLogger("Atlas.TriggerHandler")


class TriggerHandler:
    def __init__(
        self,
        scheduler: "Scheduler",
        storage: "AsyncSQLiteStorage",
        max_retries: int = 3,
    ) -> None:
        self.scheduler = scheduler
        self.storage = storage
        self.max_retries = max_retries
        self._backoff_until = 0.0

    async def handle(self, trigger_data: Dict[str, Any]) -> Dict[str, Any]:
        if time.time() < self._backoff_until:
            raise BackpressureError("Backoff active, please retry later")

        try:
            delay = trigger_data.get("delay", 0.0)
            task_id = await self.scheduler.submit(trigger_data, delay=delay)
            return {"task_id": task_id, "status": "accepted"}

        except StorageFullError as e:
            logger.warning(f"Storage backpressure: {e}. Entering backoff.")
            self._backoff_until = time.time() + 1.0
            raise BackpressureError("Storage full, backoff applied") from e

        except Exception as e:
            logger.error(f"Trigger handling error: {e}")
            await self._write_dead_letter(trigger_data, str(e))
            raise

    async def _write_dead_letter(self, data: Dict[str, Any], error: str) -> None:
        try:
            packed = msgpack.packb(data, default=str, use_bin_type=True)
            await self.storage.execute_write(
                "INSERT INTO dead_letters (task_data, error) VALUES (?, ?)",
                (packed, error)
            )
            logger.debug("Dead letter written")
        except Exception as e:
            logger.error(f"Failed to write dead letter: {e}")