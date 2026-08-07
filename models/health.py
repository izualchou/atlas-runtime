# models/health.py
"""
健康状态数据模型。

定义电池状态、内存状态和综合健康状态的纯数据结构。
从 core/health_checker.py 提取，供所有模块安全引用。
"""

from dataclasses import dataclass, field
from typing import List


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

    # 告警阈值（类级别常量，方便外部引用）
    LOW_BATTERY_THRESHOLD: int = 15        # 低于 15% 告警
    CRITICAL_BATTERY_THRESHOLD: int = 5    # 低于 5% 严重告警
    HIGH_TEMP_THRESHOLD: float = 45.0      # 高于 45°C 告警
    HIGH_MEMORY_THRESHOLD: float = 85.0   # 高于 85% 内存使用告警
