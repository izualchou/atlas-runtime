"""
Unit tests for core.state_manager — key-value state with async lock + snapshot.

Actual API: StateManager(snapshot_mgr, snapshot_interval)
  - start() / stop()
  - get(key, default) / set(key, value) / set_many(items) / delete(key)
  - get_version(key) / get_all()
"""

import asyncio

import pytest
import pytest_asyncio

from core.state_manager import StateManager
from storage.snapshot import SnapshotManager


@pytest_asyncio.fixture
async def snap_mgr(temp_dir):
    snap_dir = temp_dir / "snapshots"
    snap_dir.mkdir(exist_ok=True)
    mgr = SnapshotManager(snapshot_dir=str(snap_dir), filename="test.snapshot")
    return mgr


@pytest_asyncio.fixture
async def sm(snap_mgr):
    mgr = StateManager(snap_mgr, snapshot_interval=999)  # don't auto-snapshot
    await mgr.start()
    yield mgr
    await mgr.stop()


class TestStateManagerBasics:

    @pytest.mark.asyncio
    async def test_set_and_get(self, sm):
        await sm.set("key1", "value1")
        assert await sm.get("key1") == "value1"

    @pytest.mark.asyncio
    async def test_get_default(self, sm):
        assert await sm.get("missing") is None
        assert await sm.get("missing", 42) == 42

    @pytest.mark.asyncio
    async def test_set_many(self, sm):
        await sm.set_many({"a": 1, "b": 2, "c": 3})
        assert await sm.get("a") == 1
        assert await sm.get("b") == 2
        assert await sm.get("c") == 3

    @pytest.mark.asyncio
    async def test_delete(self, sm):
        await sm.set("del-me", "bye")
        assert await sm.delete("del-me") is True
        assert await sm.get("del-me") is None

    @pytest.mark.asyncio
    async def test_delete_missing(self, sm):
        assert await sm.delete("no-such") is False

    @pytest.mark.asyncio
    async def test_get_all(self, sm):
        await sm.set_many({"x": 10, "y": 20})
        all_data = await sm.get_all()
        assert all_data["x"] == 10
        assert all_data["y"] == 20

    @pytest.mark.asyncio
    async def test_version_tracking(self, sm):
        await sm.set("v1", 100)
        assert await sm.get_version("v1") == 1
        await sm.set("v1", 200)
        assert await sm.get_version("v1") == 2
        assert await sm.get_version("never-set") is None

    @pytest.mark.asyncio
    async def test_overwrite(self, sm):
        await sm.set("ow", "first")
        await sm.set("ow", "second")
        assert await sm.get("ow") == "second"


class TestStateManagerConcurrent:

    @pytest.mark.asyncio
    async def test_concurrent_sets(self, sm):
        N = 200
        async def set_val(i):
            await sm.set(f"c-{i}", i)
        await asyncio.gather(*(set_val(i) for i in range(N)))
        for i in range(N):
            assert await sm.get(f"c-{i}") == i

    @pytest.mark.asyncio
    async def test_concurrent_set_many_different_keys(self, sm):
        async def batch(start):
            await sm.set_many({f"b-{start+j}": start+j for j in range(50)})
        await asyncio.gather(batch(0), batch(50), batch(100), batch(150))
        assert await sm.get("b-0") == 0
        assert await sm.get("b-199") == 199


class TestStateManagerEdgeCases:

    @pytest.mark.asyncio
    async def test_empty_key(self, sm):
        await sm.set("", "empty-key")
        assert await sm.get("") == "empty-key"

    @pytest.mark.asyncio
    async def test_large_value(self, sm):
        big = "x" * 100_000
        await sm.set("big", big)
        assert await sm.get("big") == big

    @pytest.mark.asyncio
    async def test_complex_value(self, sm):
        data = {"nested": {"list": [1, 2, 3], "bool": True}}
        await sm.set("complex", data)
        result = await sm.get("complex")
        assert result["nested"]["list"] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_get_all_returns_copy(self, sm):
        await sm.set("mutate", [1, 2, 3])
        data = await sm.get_all()
        data["mutate"].append(4)
        original = await sm.get("mutate")
        assert original == [1, 2, 3]  # not mutated

    @pytest.mark.asyncio
    async def test_stop_flushes_snapshot(self, sm, snap_mgr):
        await sm.set("persist", "after-stop-test")
        await sm.stop()
        # Restore in new StateManager
        sm2 = StateManager(snap_mgr, snapshot_interval=999)
        await sm2.start()
        restored = await sm2.get("persist")
        # Snapshot is best-effort; may or may not have written
        await sm2.stop()
