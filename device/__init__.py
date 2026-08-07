# device/__init__.py
"""
设备抽象层 — 平台检测与健康监控。

本层封装了所有平台相关的 I/O 操作（Termux API、Android 命令行、/proc 文件系统），
供 core 微内核和其他模块使用。

导出：
- PlatformInfo: 设备平台完整信息（制造商、One UI 版本、命令可用性等）
- HealthChecker: 周期性电池/内存/温度健康检查器
"""

from .detector import PlatformInfo, TERMUX_PREFIX, TERMUX_HOME, TERMUX_TMP
from .health import HealthChecker

__all__ = [
    "PlatformInfo",
    "HealthChecker",
    "TERMUX_PREFIX",
    "TERMUX_HOME",
    "TERMUX_TMP",
]
