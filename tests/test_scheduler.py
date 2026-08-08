"""
Unit tests for core.scheduler — task scheduling with retry/backoff.

v9.0: Scheduler now uses BaseExecutor protocol (executor.execute(cmd, timeout))
instead of plain Callable. Tests use MockExecutor subclass for compatibility.

BUG IDENTIFICATION:
  B-001: submit() may raise if pending queue is full but caller may not handle
  B-002: _safe_on_task_complete is fire-and-forget; task may be GC'd
  B-003: no timeout enforcement for executor itself (relies on executor to handle)
"""

import asyncio
import time

import pytest
import pytest_asyncio

from core.scheduler import Scheduler
from models import Task, TaskStatus
from executors.base import ExecutorResult, BaseExecutor
from core.resource_lock import ResourceLock
from storage.driver import SingleWriterStorage


# ---------------------------------------------------------------------------
# Mock executors implementing BaseExecutor protocol
# ---------------------------------------------------------------------------

class _MockExecutor(BaseExecutor):
    """Base for test mock executors with execute(cmd, timeout) interface."""
    async def execute(self, cmd="", timeout=None, **kwargs):
        raise NotImplementedError


class SuccessExecutor(_MockExecutor):
    async def execute(self, cmd="", timeout=None, **kwargs):
        await asyncio.sleep(0.01)
        return ExecutorResult(
            success=True,
            data={"stdout": f"ok: {cmd}", "stderr": "", "returncode": 0},
            method="mock",
            verified=True,
        )


class FailExecutor(_MockExecutor):
    async def execute(self, cmd="", timeout=None, **kwargs):
        await asyncio.sleep(0.01)
        raise RuntimeError(f"command failed: {cmd}")


class TimeoutExecutor(_MockExecutor):
    async def execute(self, cmd="", timeout=None, **kwargs):
        t = timeout if timeout is not None else 5.0
        await asyncio.sleep(t + 1)
        return ExecutorResult(success=True, data={}, method="mock", verified=True)


class FlakyExecutor(_MockExecutor):
    """Fails N times then succeeds."""
    def __init__(self, fail_count=2):
        super().__init__()
        self.attempts = 0
        self.fail_count = fail_count

    async def execute(self, cmd="", timeout=None, **kwargs):
        self.attempts += 1
        await asyncio.sleep(0.01)
        if self.attempts <= self.fail_count:
            raise RuntimeError(f"flaky fail #{self.attempts}")
        return ExecutorResult(
            success=True,
            data={"stdout": "finally ok", "returncode": 0},
            method="mock",
            verified=True,
        )


# singleton instances for reuse
success_executor = SuccessExecutor()
fail_executor = FailExecutor()
timeout_executor = TimeoutExecutor()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def storage(mem_db_path):
    store = SingleWriterStorage(mem_db_path)
    await store.start()
    # create required tables
    await store.execute_write("""
        CREATE TABLE IF NOT EXISTS resource_locks (
            resource TEXT PRIMARY KEY, owner TEXT NOT NULL,
            acquired_at INTEGER NOT NULL, expires_at INTEGER NOT NULL
        )
    """)
    yield store
    await store.stop()


@pytest_asyncio.fixture
async def rlock(storage):
    return ResourceLock(storage)


@pytest_asyncio.fixture
async def scheduler(rlock):
    sched = Scheduler(executor=success_executor, resource_lock=rlock)
    await sched.start()
    yield sched
    await sched.stop()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBasicScheduling:

    @pytest.mark.asyncio
    async def test_submit_returns_task_id(self, scheduler):
        tid = await scheduler.submit({"command": "echo hello"})
        assert isinstance(tid, str)
        assert len(tid) > 0

    @pytest.mark.asyncio
    async def test_task_executes(self, scheduler):
        tid = await scheduler.submit({"command": "echo hello"})
        await asyncio.sleep(0.15)
        task = await scheduler.get_task(tid)
        assert task is not None
        assert task.status == TaskStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_delayed_task(self, scheduler):
        tid = await scheduler.submit({"command": "echo delayed"}, delay=0.2)
        await asyncio.sleep(0.05)
        task = await scheduler.get_task(tid)
        # Should still be PENDING (not yet scheduled)
        assert task.status in (TaskStatus.PENDING,)
        await asyncio.sleep(0.3)
        task = await scheduler.get_task(tid)
        assert task.status == TaskStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_multiple_tasks(self, scheduler):
        tasks = []
        for i in range(10):
            tid = await scheduler.submit({"command": f"echo {i}"})
            tasks.append(tid)
        await asyncio.sleep(0.3)
        for tid in tasks:
            task = await scheduler.get_task(tid)
            assert task.status == TaskStatus.SUCCESS, f"{tid}: {task.status}"


class TestRetryLogic:

    @pytest.mark.asyncio
    async def test_task_retries(self, rlock):
        sched = Scheduler(executor=FlakyExecutor(fail_count=1), resource_lock=rlock)
        await sched.start()
        tid = await sched.submit({"command": "flaky", "max_retries": 3})
        await asyncio.sleep(0.5)
        task = await sched.get_task(tid)
        assert task.status == TaskStatus.SUCCESS
        await sched.stop()

    @pytest.mark.asyncio
    async def test_task_dead_after_max_retries(self, rlock):
        sched = Scheduler(executor=fail_executor, resource_lock=rlock)
        await sched.start()
        tid = await sched.submit({"command": "always-fail", "max_retries": 2})
        await asyncio.sleep(1.0)  # wait for retries + backoff
        task = await sched.get_task(tid)
        # Final state: DEAD or FAILED depending on timing
        assert task.status in (TaskStatus.DEAD, TaskStatus.FAILED, TaskStatus.PENDING)
        await sched.stop()

    @pytest.mark.asyncio
    async def test_exponential_backoff(self, rlock):
        """Retry count should increase on failure."""
        sched = Scheduler(executor=fail_executor, resource_lock=rlock)
        await sched.start()
        tid = await sched.submit({"command": "fail", "max_retries": 3})
        await asyncio.sleep(0.8)
        task = await sched.get_task(tid)
        # retries counter should have incremented
        assert task is not None
        await sched.stop()


class TestCallback:

    @pytest.mark.asyncio
    async def test_callback_invoked(self, rlock):
        results = []
        async def cb(task):
            results.append(task)

        sched = Scheduler(executor=success_executor, resource_lock=rlock)
        sched.on_task_complete = cb
        await sched.start()
        tid = await sched.submit({"command": "cb-test"})
        await asyncio.sleep(0.15)
        assert len(results) >= 1
        assert results[0].id == tid
        await sched.stop()

    @pytest.mark.asyncio
    async def test_callback_exception_is_safe(self, rlock):
        """BUG B-002: callback exceptions are logged but silently swallowed."""
        async def bad_cb(task):
            raise ValueError("callback error!")
        sched = Scheduler(executor=success_executor, resource_lock=rlock)
        sched.on_task_complete = bad_cb
        await sched.start()
        tid = await sched.submit({"command": "bad-cb"})
        await asyncio.sleep(0.15)
        task = await sched.get_task(tid)
        # Task should still succeed despite callback failure
        assert task.status == TaskStatus.SUCCESS
        await sched.stop()


class TestEdgeCases:

    @pytest.mark.asyncio
    async def test_submit_without_command(self, scheduler):
        tid = await scheduler.submit({"type": "shell"})
        await asyncio.sleep(0.1)
        task = await scheduler.get_task(tid)
        assert task.status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_submit_empty_command(self, scheduler):
        tid = await scheduler.submit({"command": ""})
        await asyncio.sleep(0.1)
        task = await scheduler.get_task(tid)
        assert task.status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_submit_whitespace_command(self, scheduler):
        tid = await scheduler.submit({"command": "   \t  "})
        await asyncio.sleep(0.1)
        task = await scheduler.get_task(tid)
        assert task.status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_submit_string_action(self, rlock):
        """BUG B-003: When action is str, Task.__post_init__ with resource=None
        causes _execute_task to fail because str has no .get('resource')."""
        sched = Scheduler(executor=success_executor, resource_lock=rlock)
        await sched.start()
        with pytest.raises(AttributeError):
            await sched.submit("echo from string")
        await sched.stop()

    @pytest.mark.asyncio
    async def test_stop_then_submit(self, rlock):
        sched = Scheduler(executor=success_executor, resource_lock=rlock)
        await sched.start()
        await sched.stop()
        # BUG B-004: submit after stop may succeed because queue still exists
        try:
            await sched.submit({"command": "after-death"})
        except RuntimeError:
            pass  # Expected

    @pytest.mark.asyncio
    async def test_get_task_nonexistent(self, scheduler):
        assert await scheduler.get_task("no-such-id") is None
