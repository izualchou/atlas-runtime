# core/__init__.py
"""
微内核层。

仅包含有生命周期的活动组件（start/stop 生命周期），
不包含数据模型、平台检测或执行器逻辑。

v9.0 架构优化：
- platform / health_checker 已迁移至 device/ 包，保留兼容性存根
- shell_executor 已消除重复，统一使用 executors 版本
- 新增 models/ 数据模型层，所有数据类集中管理
"""

from .bootstrap import Bootstrap
from .scheduler import Scheduler
from .state_manager import StateManager
from .resource_lock import ResourceLock
from .trigger_handler import TriggerHandler

__all__ = [
    "Bootstrap",
    "Scheduler",
    "StateManager",
    "ResourceLock",
    "TriggerHandler",
]
