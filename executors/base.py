# executors/base.py
"""
执行器抽象基类与统一结果类型。

为 SafeShellExecutor、UIAutomationExecutor、HighPrivilegeExecutor
提供共享的接口契约和标准化的执行结果格式。

v9.0 架构优化新增。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ExecutorResult:
    """
    标准化的执行结果。

    所有执行器返回此类型或其子类，确保调用方有统一的错误处理模式。

    Attributes:
        success:           操作是否成功
        data:              结果数据（类型由具体执行器决定）
        error:             错误描述（仅在 success=False 时有意义）
        method:            实际执行路径（如 "svc", "cmd", "rish_preset", "auto"）
        verified:          是否已进行后置校验
        execution_time_ms: 执行耗时（毫秒）
    """
    success: bool = False
    data: Any = None
    error: str = ""
    method: str = ""
    verified: bool = False
    execution_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "method": self.method,
            "verified": self.verified,
            "execution_time_ms": self.execution_time_ms,
        }


class BaseExecutor(ABC):
    """
    执行器抽象基类。

    所有执行器（Shell、UI Automation、High Privilege 等）
    应实现此接口以确保统一的调用模式。

    子类需要实现：
    - execute(**kwargs) → ExecutorResult
    - 可选的 connect/disconnect 方法用于资源管理
    """

    @abstractmethod
    async def execute(self, **kwargs) -> ExecutorResult:
        """执行操作并返回标准化结果"""
        ...

    async def connect(self) -> None:
        """建立连接/初始化资源（可选覆盖）"""
        pass

    async def disconnect(self) -> None:
        """释放连接/清理资源（可选覆盖）"""
        pass

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
        return False
