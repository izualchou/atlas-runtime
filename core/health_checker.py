# core/health_checker.py
"""
运行时健康检查器（Samsung One UI 8.5 + Termux 适配）

职责：
- 周期性监控电池状态、温度、内存使用率
- 当检测到低电量、高温、内存不足时发出告警
- 提供 `termux-battery-status` 优先、`dumpsys battery` 回退的双路径
- 与 BatteryAwareCheckpoint 集成，控制任务提交门控

使用方式：
    checker = HealthChecker(platform_info)
    await checker.start()
    status = await checker.get_status()
"""

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Optional, Callable, List

from core.platform import PlatformInfo

logger = logging.getLogger("Atlas.HealthChecker")


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class BatteryStatus:
    """电池状态快照"""
    level: int = 100           # 电量百分比 0-100
    charging: bool = False     # 是否充电中
    ac_connected: bool = False # 交流电源连接
    usb_connected: bool = False# USB 连接
    temperature_c: float = 25.0# 电池温度（摄氏度）
    health: str = "unknown"    # good/overheat/cold/dead/unknown


@dataclass
class MemoryStatus:
    """内存状态快照"""
    total_mb: int = 0
    available_mb: int = 0
    used_mb: int = 0
    usage_percent: float = 0.0


@dataclass
class SystemHealth:
    """综合健康状态"""
    battery: BatteryStatus = field(default_factory=BatteryStatus)
    memory: MemoryStatus = field(default_factory=MemoryStatus)
    is_healthy: bool = True
    warnings: List[str] = field(default_factory=list)

    # 告警阈值
    LOW_BATTERY_THRESHOLD: int = 15        # 低于 15% 告警
    CRITICAL_BATTERY_THRESHOLD: int = 5    # 低于 5% 严重告警
    HIGH_TEMP_THRESHOLD: float = 45.0      # 高于 45°C 告警
    HIGH_MEMORY_THRESHOLD: float = 85.0    # 高于 85% 内存使用告警


# ---------------------------------------------------------------------------
# HealthChecker
# ---------------------------------------------------------------------------

class HealthChecker:
    """
    运行时健康检查器。

    在后台周期性运行，提供设备实时状态。避免在关键路径上进行阻塞 I/O，
    所有探测操作在线程池中执行。
    """

    def __init__(
        self,
        platform: PlatformInfo,
        check_interval_seconds: float = 30.0,
    ):
        self._platform = platform
        self._interval = check_interval_seconds
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._latest_health: Optional[SystemHealth] = None
        self._subscribers: List[Callable] = []  # 状态变化回调

    async def start(self) -> None:
        """启动健康检查循环"""
        if self._running:
            return
        self._running = True
        # 立即执行一次检查
        await self._do_check()
        self._task = asyncio.create_task(self._loop())
        logger.info(f"HealthChecker started, interval={self._interval}s")

    async def stop(self) -> None:
        """停止健康检查"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("HealthChecker stopped")

    async def _loop(self) -> None:
        """主循环"""
        while self._running:
            try:
                await asyncio.sleep(self._interval)
                await self._do_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error: {e}")

    async def _do_check(self) -> None:
        """执行一次完整的健康检查"""
        loop = asyncio.get_running_loop()

        battery = await loop.run_in_executor(None, self._read_battery)
        memory = await loop.run_in_executor(None, self._read_memory)

        health = SystemHealth(battery=battery, memory=memory)

        # 评估健康状态
        if battery.level <= health.CRITICAL_BATTERY_THRESHOLD and not battery.charging:
            health.is_healthy = False
            health.warnings.append(
                f"CRITICAL: Battery at {battery.level}%, not charging"
            )
        elif battery.level <= health.LOW_BATTERY_THRESHOLD and not battery.charging:
            health.warnings.append(
                f"WARNING: Low battery ({battery.level}%), not charging"
            )

        if battery.temperature_c > health.HIGH_TEMP_THRESHOLD:
            health.warnings.append(
                f"WARNING: High battery temperature ({battery.temperature_c:.1f}°C)"
            )

        if memory.usage_percent > health.HIGH_MEMORY_THRESHOLD:
            health.warnings.append(
                f"WARNING: High memory usage ({memory.usage_percent:.1f}%)"
            )

        # 更新最新状态
        previous = self._latest_health
        self._latest_health = health

        # 状态变化时通知订阅者
        if previous is None or previous.warnings != health.warnings:
            for cb in self._subscribers:
                try:
                    cb(health)
                except Exception as e:
                    logger.error(f"Health subscriber error: {e}")

        # 输出日志
        if health.warnings:
            logger.warning(f"Health warnings: {'; '.join(health.warnings)}")
        else:
            logger.debug(
                f"Health OK: battery={battery.level}% "
                f"{'charging' if battery.charging else 'discharging'}, "
                f"temp={battery.temperature_c:.1f}°C, "
                f"mem={memory.usage_percent:.1f}%"
            )

    # -----------------------------------------------------------------------
    # 电池检测（termux-battery-status 优先，dumpsys 回退）
    # -----------------------------------------------------------------------

    def _read_battery(self) -> BatteryStatus:
        """读取电池状态，选择最佳可用方法"""
        if self._platform.has_termux_battery:
            return self._read_battery_termux()
        if self._platform.has_dumpsys:
            return self._read_battery_dumpsys()
        return self._read_battery_proc()

    def _read_battery_termux(self) -> BatteryStatus:
        """通过 termux-battery-status 读取（最可靠）"""
        try:
            proc = subprocess.run(
                ["termux-battery-status"],
                capture_output=True, text=True, timeout=5
            )
            if proc.returncode != 0:
                raise RuntimeError(f"termux-battery-status failed: {proc.stderr}")

            data = json.loads(proc.stdout)

            return BatteryStatus(
                level=data.get("percentage", 100),
                charging=(
                    data.get("status", "").upper() in ("CHARGING", "FULL")
                ),
                ac_connected=data.get("plugged", "").upper() == "AC",
                usb_connected=data.get("plugged", "").upper() == "USB",
                temperature_c=data.get("temperature", 25.0),
                health=data.get("health", "unknown").lower(),
            )
        except (subprocess.TimeoutExpired, json.JSONDecodeError, RuntimeError) as e:
            logger.warning(f"termux-battery-status failed: {e}, falling back")
            return self._read_battery_dumpsys()

    def _read_battery_dumpsys(self) -> BatteryStatus:
        """通过 dumpsys battery 读取（回退方案）"""
        try:
            proc = subprocess.run(
                ["/system/bin/dumpsys", "battery"],
                capture_output=True, text=True, timeout=5
            )
            output = proc.stdout

            level = 100
            charging = False
            ac = False
            usb = False
            temp = 25.0
            health = "unknown"

            for line in output.split("\n"):
                line = line.strip()
                if line.startswith("level:"):
                    try:
                        level = int(line.split(":")[1].strip())
                    except (ValueError, IndexError):
                        pass
                elif line.startswith("AC powered:"):
                    ac = "true" in line.lower()
                elif line.startswith("USB powered:"):
                    usb = "true" in line.lower()
                elif line.startswith("status:"):
                    s = line.split(":")[1].strip()
                    charging = s in ("2", "5") or s.upper() in ("CHARGING", "FULL")
                elif line.startswith("temperature:"):
                    try:
                        # dumpsys 返回的是 0.1°C 单位
                        temp = int(line.split(":")[1].strip()) / 10.0
                    except (ValueError, IndexError):
                        pass
                elif line.startswith("health:"):
                    h = line.split(":")[1].strip()
                    if h == "1":
                        health = "unknown"
                    elif h == "2":
                        health = "good"
                    elif h == "3":
                        health = "overheat"
                    elif h == "4":
                        health = "dead"
                    elif h == "5":
                        health = "over_voltage"
                    elif h == "6":
                        health = "unspecified_failure"
                    elif h == "7":
                        health = "cold"

            return BatteryStatus(
                level=level, charging=charging,
                ac_connected=ac, usb_connected=usb,
                temperature_c=temp, health=health,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(f"dumpsys battery failed: {e}")
            return self._read_battery_proc()

    def _read_battery_proc(self) -> BatteryStatus:
        """
        通过 /sys/class/power_supply/battery/ 读取。

        注意：三星 One UI 8.5 可能限制 /sys 访问，Termux 可能无权限。
        """
        status = BatteryStatus()
        batt_dir = "/sys/class/power_supply/battery"

        try:
            # 电量
            cap_path = os.path.join(batt_dir, "capacity")
            if os.path.exists(cap_path):
                with open(cap_path, "r") as f:
                    status.level = int(f.read().strip())
        except (PermissionError, FileNotFoundError, ValueError):
            pass

        try:
            # 充电状态
            stat_path = os.path.join(batt_dir, "status")
            if os.path.exists(stat_path):
                with open(stat_path, "r") as f:
                    s = f.read().strip().upper()
                    status.charging = s in ("CHARGING", "FULL")
        except (PermissionError, FileNotFoundError):
            pass

        try:
            # 温度
            temp_path = os.path.join(batt_dir, "temp")
            if os.path.exists(temp_path):
                with open(temp_path, "r") as f:
                    # 通常以 0.1°C 为单位
                    status.temperature_c = int(f.read().strip()) / 10.0
        except (PermissionError, FileNotFoundError, ValueError):
            pass

        return status

    # -----------------------------------------------------------------------
    # 内存检测
    # -----------------------------------------------------------------------

    def _read_memory(self) -> MemoryStatus:
        """读取内存使用情况"""
        try:
            with open("/proc/meminfo", "r") as f:
                meminfo = f.read()

            total = 0
            available = 0

            for line in meminfo.split("\n"):
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    available = int(line.split()[1])

            total_mb = total // 1024
            available_mb = available // 1024
            used_mb = total_mb - available_mb

            usage = (used_mb / total_mb * 100.0) if total_mb > 0 else 0.0

            return MemoryStatus(
                total_mb=total_mb,
                available_mb=available_mb,
                used_mb=used_mb,
                usage_percent=round(usage, 2),
            )
        except (FileNotFoundError, PermissionError) as e:
            logger.warning(f"Failed to read memory: {e}")
            return MemoryStatus()

    # -----------------------------------------------------------------------
    # 公共 API
    # -----------------------------------------------------------------------

    async def get_status(self) -> Optional[SystemHealth]:
        """获取最新健康状态（非阻塞）"""
        return self._latest_health

    def subscribe(self, callback: Callable) -> None:
        """注册状态变化回调"""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable) -> None:
        """取消注册"""
        try:
            self._subscribers.remove(callback)
        except ValueError:
            pass

    @property
    def is_healthy(self) -> bool:
        if self._latest_health is None:
            return True  # 尚未检查，假定健康
        return self._latest_health.is_healthy
