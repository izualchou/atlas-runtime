# models/__init__.py
"""
数据模型层 — 跨模块共享的纯数据契约。

本层不包含任何业务逻辑、I/O 操作或外部依赖，
仅提供 dataclass、enum 和 Exception 类型定义。
所有模块均可安全引用 models/ 而不会产生循环导入。
"""

# ---- 健康状态 ----
from .health import BatteryStatus, MemoryStatus, SystemHealth

# ---- SIM 管理 ----
from .sim import SimInfo, SimStatus, SimSwitchResult

# ---- 任务调度 ----
from .task import Task, TaskStatus

# ---- 通用异常 ----
from .errors import StorageFullError, StorageError, BackpressureError

__all__ = [
    # Health
    "BatteryStatus",
    "MemoryStatus",
    "SystemHealth",
    # SIM
    "SimInfo",
    "SimStatus",
    "SimSwitchResult",
    # Task
    "Task",
    "TaskStatus",
    # Errors
    "StorageFullError",
    "StorageError",
    "BackpressureError",
]
