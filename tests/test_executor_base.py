"""
Unit tests for executors/base.py — BaseExecutor ABC and ExecutorResult dataclass.

Verifies the unified executor contract defined in v9.0 architecture.
"""

import asyncio

import pytest

from executors.base import BaseExecutor, ExecutorResult


# ---------------------------------------------------------------------------
# ExecutorResult
# ---------------------------------------------------------------------------

class TestExecutorResult:
    def test_success_result(self):
        er = ExecutorResult(
            success=True,
            data={"stdout": "ok", "returncode": 0},
            method="shell",
            verified=True,
        )
        assert er.success is True
        assert er.data["stdout"] == "ok"
        assert er.method == "shell"
        assert er.verified is True

    def test_failure_result(self):
        er = ExecutorResult(
            success=False,
            error="permission denied",
            method="shell",
            verified=False,
        )
        assert er.success is False
        assert er.error == "permission denied"
        assert er.verified is False

    def test_execution_time(self):
        er = ExecutorResult(
            success=True,
            method="shell",
            verified=True,
            execution_time_ms=123.4,
        )
        assert er.execution_time_ms == 123.4


# ---------------------------------------------------------------------------
# BaseExecutor ABC
# ---------------------------------------------------------------------------

class TestBaseExecutor:
    def test_cannot_instantiate_abstract(self):
        """ABC 不可直接实例化（execute 是抽象方法）。"""
        with pytest.raises(TypeError):
            BaseExecutor()

    def test_subclass_can_implement(self):
        """子类实现 execute() 后可以实例化。"""

        class MyExecutor(BaseExecutor):
            async def execute(self, **kwargs):
                return ExecutorResult(success=True, method="test", verified=True)

        executor = MyExecutor()
        assert isinstance(executor, BaseExecutor)

    @pytest.mark.asyncio
    async def test_execute_returns_executor_result(self):
        """execute() 返回标准的 ExecutorResult。"""

        class MyExecutor(BaseExecutor):
            async def execute(self, **kwargs):
                return ExecutorResult(success=True, method="test", verified=True)

        executor = MyExecutor()
        result = await executor.execute()
        assert isinstance(result, ExecutorResult)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_with_args(self):
        """execute() 接收并传递参数。"""

        class MyExecutor(BaseExecutor):
            async def execute(self, **kwargs):
                cmd = kwargs.get("cmd", "")
                timeout = kwargs.get("timeout", None)
                return ExecutorResult(
                    success=True,
                    data={"cmd": cmd, "timeout": timeout},
                    method="test",
                    verified=True,
                )

        executor = MyExecutor()
        result = await executor.execute(cmd="echo hello", timeout=30.0)
        assert result.data["cmd"] == "echo hello"
        assert result.data["timeout"] == 30.0

    def test_safe_shell_inherits_base(self):
        """SafeShellExecutor 继承 BaseExecutor。"""
        from executors.shell_executor import SafeShellExecutor
        assert issubclass(SafeShellExecutor, BaseExecutor)
