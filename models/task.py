# models/task.py
"""
任务调度数据模型 — Task 和 TaskStatus 纯数据契约。

本模块仅定义跨层共享的数据类和枚举，无任何业务逻辑、I/O 操作或外部依赖。
从 core/scheduler.py 迁移至 models/ 以遵循 v9.0 六层架构依赖规则。
"""

import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Optional


class TaskStatus(Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    EXECUTING = "executing"
    SUCCESS = "success"
    TIMEOUT = "timeout"
    FAILED = "failed"
    DEAD = "dead"


@dataclass
class Task:
    id: str
    action: Dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 5
    retries: int = 0
    max_retries: int = 3
    created_at: float = field(default_factory=time.time)
    scheduled_at: Optional[float] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    result: Any = None
    correlation_id: Optional[str] = None
    resource: Optional[str] = None

    def __post_init__(self):
        self.resource = self.action.get("resource")
