# executors/__init__.py
"""
执行器层。

导出所有执行器类型，供 core 微内核和其他模块使用。

v9.0 架构优化新增：
- BaseExecutor / ExecutorResult：统一执行器基类与结果类型
- sim_switch 独立模块：SIM 卡切换逻辑从 high_privilege 拆分
"""

from .base import BaseExecutor, ExecutorResult
from .shell_executor import SafeShellExecutor
from .ui_automation import UIAutomationExecutor
from .sim_switch import ShizukuSimManager, AutoJS6SimSwitcher
from .high_privilege import HighPrivilegeExecutor

__all__ = [
    "BaseExecutor",
    "ExecutorResult",
    "SafeShellExecutor",
    "UIAutomationExecutor",
    "ShizukuSimManager",
    "AutoJS6SimSwitcher",
    "HighPrivilegeExecutor",
]
