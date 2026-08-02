# storage/battery_aware.py
"""
电池感知存储策略（Samsung One UI 8.5 + Termux 适配版）

职责：
- 根据电池/充电状态动态调整 SQLite 写入策略
- 充电时：更激进的 WAL checkpoint、更小批量延迟（写入性能优先）
- 电池供电时：更保守的 checkpoint、更大批量延迟（省电优先）
- 低电量时：暂停非必要写入操作

Samsung One UI 8.5 适配：
- 三星设备电池优化激进，需要更频繁检测充电状态变化
- 温度过高时减少 I/O 频率以辅助散热
"""

import logging
import asyncio
from typing import Optional

logger = logging.getLogger("Atlas.BatteryAware")


class BatteryAwareCheckpoint:
    """
    电池感知的 WAL checkpoint 策略。

    策略表：
    ┌──────────────┬──────────────┬──────────────┐
    │  模式         │ autocheckpoint│ batch_delay │
    ├──────────────┼──────────────┼──────────────┤
    │ CHARGING     │ 1000 (频繁)  │ 50ms (低延迟)│
    │ BATTERY_OK   │ 5000         │ 150ms        │
    │ BATTERY_LOW  │ 10000        │ 300ms        │
    │ CRITICAL     │ 20000 (保守) │ 500ms (省电) │
    │ OVERHEAT     │ 20000        │ 500ms        │
    └──────────────┴──────────────┴──────────────┘
    """

    def __init__(
        self,
        storage,
        check_interval_seconds: int = 15,  # Samsung: 更频繁检查
        charging_autocheckpoint: int = 1000,
        battery_ok_autocheckpoint: int = 5000,
        battery_low_autocheckpoint: int = 10000,
        battery_critical_autocheckpoint: int = 20000,
        charging_batch_delay_ms: int = 50,
        battery_ok_batch_delay_ms: int = 150,
        battery_low_batch_delay_ms: int = 300,
        battery_critical_batch_delay_ms: int = 500,
        low_battery_threshold: int = 15,
        critical_battery_threshold: int = 5,
        high_temp_threshold: float = 45.0,
    ):
        """
        Args:
            storage: SingleWriterStorage 实例
            check_interval_seconds: 状态检查间隔（秒）
            *_autocheckpoint: 各模式的 WAL autocheckpoint 值
            *_batch_delay_ms: 各模式的批量写入延迟（毫秒）
            low_battery_threshold: 低电量阈值（百分比）
            critical_battery_threshold: 严重低电量阈值（百分比）
            high_temp_threshold: 高温阈值（摄氏度）
        """
        self.storage = storage
        self.check_interval = check_interval_seconds

        # 各模式的 checkpoint 配置
        self._policies = {
            "CHARGING": (charging_autocheckpoint, charging_batch_delay_ms),
            "BATTERY_OK": (battery_ok_autocheckpoint, battery_ok_batch_delay_ms),
            "BATTERY_LOW": (battery_low_autocheckpoint, battery_low_batch_delay_ms),
            "CRITICAL": (battery_critical_autocheckpoint, battery_critical_batch_delay_ms),
            "OVERHEAT": (battery_critical_autocheckpoint, battery_critical_batch_delay_ms),
        }

        # 阈值
        self.low_battery_threshold = low_battery_threshold
        self.critical_battery_threshold = critical_battery_threshold
        self.high_temp_threshold = high_temp_threshold

        # 当前状态
        self._current_mode: str = "BATTERY_OK"
        self._current_battery_level: int = 100
        self._current_is_charging: bool = False
        self._current_temperature: float = 25.0

        # 运行时
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._health_checker = None

    def set_health_checker(self, health_checker) -> None:
        """
        设置健康检查器引用。

        在 Bootstrap 中完成组件依赖注入后调用。
        """
        self._health_checker = health_checker

    def update_health(
        self,
        battery_level: int,
        is_charging: bool,
        temperature: float = 25.0,
    ) -> None:
        """
        从外部健康检查器接收实时健康数据。

        线程安全：此方法假设从事件循环线程调用（asyncio）。

        Args:
            battery_level: 电量百分比 (0-100)
            is_charging: 是否充电中
            temperature: 电池温度（摄氏度）
        """
        changed = False

        if battery_level != self._current_battery_level:
            self._current_battery_level = battery_level
            changed = True

        if is_charging != self._current_is_charging:
            self._current_is_charging = is_charging
            changed = True

        if abs(temperature - self._current_temperature) > 2.0:
            self._current_temperature = temperature
            changed = True

        if changed:
            mode = self._determine_mode()
            if mode != self._current_mode:
                logger.info(
                    f"Battery mode change: {self._current_mode} -> {mode} "
                    f"(level={battery_level}%, charging={is_charging}, temp={temperature:.1f}°C)"
                )
                self._current_mode = mode
                # 创建任务异步应用策略（避免阻塞调用方）
                asyncio.create_task(self._apply_policy(mode))

    def _determine_mode(self) -> str:
        """根据当前状态确定运行模式"""
        # 高温优先（可能对 Samsung 设备关键）
        if self._current_temperature > self.high_temp_threshold:
            return "OVERHEAT"

        # 充电状态
        if self._current_is_charging:
            return "CHARGING"

        # 电池电量状态
        if self._current_battery_level <= self.critical_battery_threshold:
            return "CRITICAL"
        if self._current_battery_level <= self.low_battery_threshold:
            return "BATTERY_LOW"

        return "BATTERY_OK"

    async def start(self) -> None:
        """启动监控循环"""
        if self._running:
            return
        self._running = True
        # 立即应用初始策略
        await self._apply_policy("BATTERY_OK")
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(
            f"Battery-aware checkpoint started (interval={self.check_interval}s)"
        )

    async def _monitor_loop(self) -> None:
        """监控循环：周期性检查充电状态"""
        while self._running:
            try:
                await asyncio.sleep(self.check_interval)
                is_charging = await self._get_charging_status()

                if is_charging != self._current_is_charging:
                    self._current_is_charging = is_charging
                    mode = self._determine_mode()
                    self._current_mode = mode
                    await self._apply_policy(mode)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Battery monitor error: {e}")

    async def _get_charging_status(self) -> bool:
        """
        获取充电状态。

        优先使用注入的 health_checker，回退到默认 True（安全策略）。
        """
        if self._health_checker:
            try:
                health = await self._health_checker.get_status()
                if health is not None:
                    return health.battery.charging
            except Exception as e:
                logger.debug(f"HealthChecker status query failed: {e}")
        return True  # 默认保守：假定充电中

    async def _apply_policy(self, mode: str) -> None:
        """应用指定模式的存储策略"""
        policy = self._policies.get(mode)
        if policy is None:
            logger.warning(f"Unknown battery mode: {mode}")
            return

        autocheckpoint, batch_delay = policy

        # 更新 SQLite PRAGMA
        try:
            await self.storage.execute_write(
                f"PRAGMA wal_autocheckpoint={autocheckpoint};"
            )
        except Exception as e:
            logger.error(f"Failed to update autocheckpoint: {e}")

        # 更新批量写入延迟
        if hasattr(self.storage, "set_batch_delay"):
            try:
                self.storage.set_batch_delay(batch_delay)
            except Exception as e:
                logger.error(f"Failed to set batch delay: {e}")

        logger.info(
            f"Battery policy: {mode}, autocheckpoint={autocheckpoint}, batch_delay={batch_delay}ms"
        )

        # 充电模式：执行一次完整 checkpoint 以释放 WAL 空间
        if mode == "CHARGING":
            try:
                await self.storage.checkpoint(full=True)
            except Exception as e:
                logger.error(f"Full checkpoint failed: {e}")

    async def stop(self) -> None:
        """停止监控"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Battery-aware checkpoint stopped")
