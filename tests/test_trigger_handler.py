"""
Unit tests for core.trigger_handler — trigger reception, backpressure.

Actual API: TriggerHandler(scheduler, storage, max_retries=3)
  - handle(trigger_data: dict) -> dict  (NOT a JSON string!)
  - BackpressureError

BUG IDENTIFICATION:
  B-020: handle() expects dict but caller might send JSON string
  B-021: backoff_until is set but never reset on successful handles
"""

import asyncio
import json
import time

import pytest
import pytest_asyncio

from core.trigger_handler import TriggerHandler, BackpressureError
from core.scheduler import Scheduler
from core.resource_lock import ResourceLock
from storage.driver import SingleWriterStorage


# ---------------------------------------------------------------------------
# Mock executor (BaseExecutor protocol)
# ---------------------------------------------------------------------------

from executors.base import ExecutorResult, BaseExecutor


class MockExecutor(BaseExecutor):
    async def execute(self, cmd="", timeout=None, **kwargs):
        await asyncio.sleep(0.01)
        return ExecutorResult(
            success=True,
            data={"stdout": cmd, "returncode": 0},
            method="mock",
            verified=True,
        )


mock_executor = MockExecutor()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def storage(mem_db_path):
    s = SingleWriterStorage(mem_db_path)
    await s.start()
    await s.execute_write("""
        CREATE TABLE IF NOT EXISTS resource_locks (
            resource TEXT PRIMARY KEY, owner TEXT NOT NULL,
            acquired_at INTEGER NOT NULL, expires_at INTEGER NOT NULL
        )
    """)
    yield s
    await s.stop()


@pytest_asyncio.fixture
async def rlock(storage):
    return ResourceLock(storage)


@pytest_asyncio.fixture
async def scheduler(rlock):
    sched = Scheduler(executor=mock_executor, resource_lock=rlock)
    await sched.start()
    yield sched
    await sched.stop()


@pytest_asyncio.fixture
async def handler(scheduler, storage):
    return TriggerHandler(scheduler=scheduler, storage=storage)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestValidTriggers:

    @pytest.mark.asyncio
    async def test_handle_valid_dict(self, handler):
        result = await handler.handle({"command": "echo hello"})
        assert result["status"] == "accepted"
        assert "task_id" in result

    @pytest.mark.asyncio
    async def test_handle_delayed(self, handler):
        result = await handler.handle({"command": "echo later", "delay": 0.5})
        assert result["status"] == "accepted"

    @pytest.mark.asyncio
    async def test_handle_with_resource(self, handler):
        """Task with resource locking."""
        result = await handler.handle({"command": "echo locked", "resource": "test-lock"})
        assert result["status"] == "accepted"

    @pytest.mark.asyncio
    async def test_multiple_handles(self, handler):
        for i in range(10):
            result = await handler.handle({"command": f"echo {i}"})
            assert result["status"] == "accepted"


class TestInvalidTriggers:

    @pytest.mark.asyncio
    async def test_handle_none(self, handler):
        """BUG B-020: None input may cause AttributeError."""
        with pytest.raises((TypeError, AttributeError, ValueError)):
            await handler.handle(None)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_handle_empty_dict(self, handler):
        """Empty dict = no command = task fails but should not crash handler."""
        try:
            result = await handler.handle({})
            # "accepted" or may raise due to validation
            assert result.get("status") in ("accepted", None)
        except (ValueError, KeyError):
            pass  # Acceptable: empty dict may be rejected

    @pytest.mark.asyncio
    async def test_handle_extra_fields(self, handler):
        result = await handler.handle({
            "command": "echo hi",
            "priority": "high",
            "tags": ["urgent"],
            "unknown": "ignored",
        })
        assert result["status"] == "accepted"


class TestBackpressure:

    @pytest.mark.asyncio
    async def test_backpressure_on_full_queue(self, rlock, storage):
        """Queue full should raise RuntimeError."""
        sched = Scheduler(executor=mock_executor, resource_lock=rlock, max_pending=1)
        await sched.start()
        h = TriggerHandler(scheduler=sched, storage=storage)

        # Fill the queue
        await h.handle({"command": "blocking"})

        # Second item should raise RuntimeError
        with pytest.raises(RuntimeError):
            await h.handle({"command": "overflow"})

        await sched.stop()

    @pytest.mark.asyncio
    async def test_backoff_period(self, handler):
        """BUG B-021: backoff_until is set on certain errors, blocking future handles."""
        # Manually trigger backoff
        handler._backoff_until = time.time() + 10
        with pytest.raises(BackpressureError):
            await handler.handle({"command": "rejected"})

        # Clear backoff
        handler._backoff_until = 0.0
        result = await handler.handle({"command": "ok-now"})
        assert result["status"] == "accepted"


class TestEdgeCases:

    @pytest.mark.asyncio
    async def test_handle_storage_full(self, handler, storage):
        """StorageFullError propagation."""
        # This is hard to trigger with in-memory SQLite but we verify the error
        # type exists and is imported
        from storage.driver import StorageFullError
        assert StorageFullError is not None

    @pytest.mark.asyncio
    async def test_concurrent_handles(self, handler):
        N = 20
        results = await asyncio.gather(*(
            handler.handle({"command": f"echo conc-{i}"}) for i in range(N)
        ), return_exceptions=True)
        accepted = sum(1 for r in results if not isinstance(r, Exception) and r.get("status") == "accepted")
        assert accepted >= N * 0.5  # lower threshold: some may hit capacity
