# storage/battery_aware.py
import logging
import asyncio
from typing import Optional

logger = logging.getLogger("Atlas.BatteryAware")


class BatteryAwareCheckpoint:
    def __init__(
        self,
        storage,
        check_interval_seconds: int = 30,
        charging_autocheckpoint: int = 1000,
        battery_autocheckpoint: int = 10000,
        charging_batch_delay_ms: int = 50,
        battery_batch_delay_ms: int = 200,
    ):
        self.storage = storage
        self.check_interval = check_interval_seconds
        self.charging_autocheckpoint = charging_autocheckpoint
        self.battery_autocheckpoint = battery_autocheckpoint
        self.charging_batch_delay = charging_batch_delay_ms
        self.battery_batch_delay = battery_batch_delay_ms

        self._current_is_charging = False
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._health_checker = None

    def set_health_checker(self, health_checker) -> None:
        self._health_checker = health_checker

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Battery-aware checkpoint started")

    async def _monitor_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.check_interval)
                is_charging = await self._get_charging_status()
                if is_charging != self._current_is_charging:
                    self._current_is_charging = is_charging
                    await self._apply_policy(is_charging)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Battery-aware monitor error: {e}")

    async def _get_charging_status(self) -> bool:
        if self._health_checker:
            try:
                status = await self._health_checker.get_charging_status()
                if status is not None:
                    return status
            except Exception:
                pass
        # 默认返回 True（充电状态，保守策略）
        return True

    async def _apply_policy(self, is_charging: bool) -> None:
        if is_charging:
            autocheckpoint = self.charging_autocheckpoint
            batch_delay = self.charging_batch_delay
            mode = "CHARGING"
        else:
            autocheckpoint = self.battery_autocheckpoint
            batch_delay = self.battery_batch_delay
            mode = "BATTERY"

        # 更新 SQLite PRAGMA
        try:
            await self.storage.execute_write(f"PRAGMA wal_autocheckpoint={autocheckpoint};")
        except Exception as e:
            logger.error(f"Failed to update autocheckpoint: {e}")

        # 更新存储驱动的批量延迟
        if hasattr(self.storage, 'set_batch_delay'):
            try:
                self.storage.set_batch_delay(batch_delay)
            except Exception as e:
                logger.error(f"Failed to set batch delay: {e}")

        logger.info(f"Battery policy: {mode}, autocheckpoint={autocheckpoint}, batch_delay={batch_delay}ms")

        if is_charging:
            try:
                await self.storage.checkpoint(full=True)
            except Exception as e:
                logger.error(f"Checkpoint failed: {e}")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Battery-aware checkpoint stopped")