# core/platform.py（兼容性存根）
"""
已迁移至 device/detector.py（v9.0 架构优化）。

本文件保留以维护向后兼容性——所有通过 `from core.platform import ...`
的导入路径仍然有效。新代码请使用 `from device import PlatformInfo`。
"""

from device.detector import *  # noqa: F401, F403
from device.detector import (
    PlatformInfo,
    TERMUX_PREFIX,
    TERMUX_HOME,
    TERMUX_TMP,
)
