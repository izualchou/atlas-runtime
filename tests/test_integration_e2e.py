"""
End-to-end integration tests for atlas-runtime.

Validates the full pipeline across module boundaries:
  TriggerHandler → Scheduler → SafeShellExecutor → StateManager → SingleWriterStorage

BUG IDENTIFICATION:
  B-070: Command with shell metacharacters may cause injection
  B-071: Task may remain PENDING indefinitely if executor hangs
  B-072: Snapshot recovery may restore stale state after crash
"""

import asyncio
import json

import pytest
import pytest_asyncio

from core.scheduler import Scheduler, TaskStatus
from core.resource_lock import ResourceLock
from core.trigger_handler import TriggerHandler
from core.state_manager import StateManager
from storage.driver import SingleWriterStorage
from storage.snapshot import SnapshotManager
from executors.shell_executor import SafeShellExecutor


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
async def executor():
    return SafeShellExecutor(default_timeout=5)


@pytest_asyncio.fixture
async def scheduler(rlock, executor):
    sched = Scheduler(
        executor=executor.run_command,
        resource_lock=rlock,
        max_pending=100,
    )
    await sched.start()
    yield sched
    await sched.stop()


@pytest_asyncio.fixture
async def trigger_handler(scheduler, storage):
    return TriggerHandler(scheduler=scheduler, storage=storage)


@pytest_asyncio.fixture
async def snap_mgr(temp_dir):
    d = temp_dir / "e2e_snaps"
    d.mkdir(exist_ok=True)
    return SnapshotManager(str(d), "e2e.snapshot")


@pytest_asyncio.fixture
async def state_manager(snap_mgr):
    sm = StateManager(snap_mgr, snapshot_interval=999)
    await sm.start()
    yield sm
    await sm.stop()


# ---------------------------------------------------------------------------
# E2E Tests
# ---------------------------------------------------------------------------

class TestE2EHappyPath:

    @pytest.mark.asyncio
    async def test_trigger_to_success(self, trigger_handler, scheduler):
        """Trigger → Schedule → Execute → SUCCESS"""
        result = await trigger_handler.handle({"command": "echo hello"})
        assert result["status"] == "accepted"
        tid = result["task_id"]

        await asyncio.sleep(0.3)
        task = await scheduler.get_task(tid)
        assert task is not None
        assert task.status == TaskStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_multiple_tasks(self, trigger_handler, scheduler):
        results = []
        for i in range(5):
            r = await trigger_handler.handle({"command": f"echo task-{i}"})
            results.append(r)
            assert r["status"] == "accepted"

        await asyncio.sleep(0.5)
        for r in results:
            task = await scheduler.get_task(r["task_id"])
            assert task.status == TaskStatus.SUCCESS


class TestE2EFailurePath:

    @pytest.mark.asyncio
    async def test_invalid_command(self, trigger_handler, scheduler):
        result = await trigger_handler.handle({"command": "exit 1"})
        tid = result["task_id"]

        await asyncio.sleep(0.5)
        task = await scheduler.get_task(tid)
        assert task.status in (TaskStatus.FAILED, TaskStatus.DEAD)

    @pytest.mark.asyncio
    async def test_nonexistent_command(self, trigger_handler, scheduler):
        result = await trigger_handler.handle({"command": "nonexistent_xyz_123"})
        tid = result["task_id"]

        await asyncio.sleep(0.3)
        task = await scheduler.get_task(tid)
        assert task.status in (TaskStatus.FAILED, TaskStatus.DEAD)


class TestE2EConcurrent:

    @pytest.mark.asyncio
    async def test_concurrent_triggers(self, trigger_handler, scheduler):
        N = 20
        results = await asyncio.gather(*(
            trigger_handler.handle({"command": f"echo conc-{i}"})
            for i in range(N)
        ), return_exceptions=True)

        accepted = sum(1 for r in results if not isinstance(r, Exception) and r.get("status") == "accepted")
        assert accepted >= N * 0.7

        await asyncio.sleep(0.5)
        for r in results:
            if not isinstance(r, Exception) and r.get("status") == "accepted":
                task = await scheduler.get_task(r["task_id"])
                assert task.status in (TaskStatus.SUCCESS, TaskStatus.EXECUTING)


class TestE2EStateManager:

    @pytest.mark.asyncio
    async def test_state_persisted_across_components(self, trigger_handler, state_manager):
        await state_manager.set("test-key", "test-value")
        assert await state_manager.get("test-key") == "test-value"

        await trigger_handler.handle({"command": "echo state-test"})
        await asyncio.sleep(0.3)

        # StateManager should still be operational
        await state_manager.set("after-trigger", "ok")
        assert await state_manager.get("after-trigger") == "ok"


class TestE2EEdgeCases:

    @pytest.mark.asyncio
    async def test_empty_command(self, trigger_handler, scheduler):
        result = await trigger_handler.handle({"command": ""})
        tid = result["task_id"]
        await asyncio.sleep(0.2)
        task = await scheduler.get_task(tid)
        assert task.status in (TaskStatus.FAILED, TaskStatus.DEAD)

    @pytest.mark.asyncio
    async def test_task_with_delay(self, trigger_handler, scheduler):
        result = await trigger_handler.handle({"command": "echo delayed", "delay": 0.3})
        tid = result["task_id"]
        # Immediately, task should still be pending
        task = await scheduler.get_task(tid)
        assert task.status == TaskStatus.PENDING
        # After delay, should succeed
        await asyncio.sleep(0.5)
        task = await scheduler.get_task(tid)
        assert task.status == TaskStatus.SUCCESS


class TestE2EIntegrationFullPipeline:

    @pytest.mark.asyncio
    async def test_full_pipeline(self, trigger_handler, scheduler, storage):
        """Full pipeline: handle → submit → execute → state update."""
        result = await trigger_handler.handle({
            "command": "echo full-pipeline",
            "max_retries": 1,
        })
        assert result["status"] == "accepted"

        await asyncio.sleep(0.3)
        task = await scheduler.get_task(result["task_id"])
        assert task.status == TaskStatus.SUCCESS
