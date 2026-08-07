# core/health_checker.py（兼容性存根）
"""
已迁移至 device/health.py（v9.0 架构优化）。

本文件保留以维护向后兼容性——所有通过 `from core.health_checker import ...`
的导入路径仍然有效。新代码请使用 `from device import HealthChecker`。
"""

from device.health import *  # noqa: F401, F403
from device.health import HealthChecker
