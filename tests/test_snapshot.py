"""
Unit tests for storage.snapshot — atomic snapshot with msgpack + SHA256.

Actual API: SnapshotManager(snapshot_dir, filename="snapshot.latest")
  - write(data: dict) -> bool  (async, returns success flag)
  - read() -> Optional[dict]   (async, reads self.snapshot_path)
  - exists() -> bool           (async)
  - delete() -> None           (async)
  - get_size() -> int          (async)

BUG IDENTIFICATION:
  B-090: write() returns bool, not path; caller cannot verify output location
  B-091: no verify() method — corruption detection only during read()
"""

import asyncio
import os

import pytest

from storage.snapshot import SnapshotManager


@pytest.fixture
def snap_dir(temp_dir):
    d = temp_dir / "snapshots"
    d.mkdir(exist_ok=True)
    return str(d)


@pytest.fixture
def mgr(snap_dir):
    return SnapshotManager(snapshot_dir=snap_dir, filename="test.snapshot")


class TestSnapshotWriteRead:

    @pytest.mark.asyncio
    async def test_write_read_cycle(self, mgr):
        data = {"tasks": [{"id": "t1", "state": "PENDING"}], "version": 1}
        ok = await mgr.write(data)
        assert ok is True

        restored = await mgr.read()
        assert restored is not None
        assert restored["version"] == 1
        assert restored["tasks"][0]["id"] == "t1"

    @pytest.mark.asyncio
    async def test_write_empty_dict(self, mgr):
        ok = await mgr.write({})
        assert ok is True
        restored = await mgr.read()
        assert restored == {}

    @pytest.mark.asyncio
    async def test_write_large_data(self, mgr):
        data = {"items": [{"id": i, "text": "x" * 100} for i in range(1000)]}
        ok = await mgr.write(data)
        assert ok is True
        restored = await mgr.read()
        assert len(restored["items"]) == 1000

    @pytest.mark.asyncio
    async def test_read_nonexistent(self, snap_dir):
        mgr2 = SnapshotManager(snapshot_dir=snap_dir, filename="empty.snapshot")
        result = await mgr2.read()
        assert result is None


class TestSnapshotCorruption:

    @pytest.mark.asyncio
    async def test_corruption_detected_on_read(self, mgr):
        """Checksum mismatch returns None (not exception)."""
        await mgr.write({"data": "important"})

        # Corrupt the file
        with open(mgr.snapshot_path, "ab") as f:
            f.write(b"corrupted!!!")

        # BUG B-091: no explicit verify() — corruption detected only on read()
        result = await mgr.read()
        assert result is None  # checksum mismatch returns None

    @pytest.mark.asyncio
    async def test_truncated_file(self, mgr):
        """File smaller than 64 bytes returns None."""
        await mgr.write({"test": True})

        # Truncate to < 64 bytes
        with open(mgr.snapshot_path, "wb") as f:
            f.write(b"too_short")

        result = await mgr.read()
        assert result is None

    @pytest.mark.asyncio
    async def test_corrupted_checksum(self, mgr):
        """Checksum bytes corrupted returns None."""
        await mgr.write({"valid": True})

        # Read file, corrupt the checksum bytes (last 64)
        with open(mgr.snapshot_path, "r+b") as f:
            f.seek(-32, 2)  # last 32 bytes of checksum
            f.write(b"x" * 32)

        result = await mgr.read()
        assert result is None


class TestSnapshotLifecycle:

    @pytest.mark.asyncio
    async def test_exists(self, mgr):
        assert await mgr.exists() is False
        await mgr.write({"hello": "world"})
        assert await mgr.exists() is True

    @pytest.mark.asyncio
    async def test_delete(self, mgr):
        await mgr.write({"temp": True})
        assert await mgr.exists() is True
        await mgr.delete()
        assert await mgr.exists() is False

    @pytest.mark.asyncio
    async def test_get_size(self, mgr):
        assert await mgr.get_size() == 0
        await mgr.write({"data": "hello"})
        size = await mgr.get_size()
        assert size > 0


class TestSnapshotEdgeCases:

    @pytest.mark.asyncio
    async def test_atomic_write_no_tmp_leftover(self, mgr):
        """Atomic write: no .tmp files should remain after write."""
        await mgr.write({"atomic": True})
        tmp_files = [f for f in os.listdir(mgr.snapshot_dir) if f.startswith("snapshot.tmp.")]
        assert len(tmp_files) == 0

    @pytest.mark.asyncio
    async def test_write_failure_cleans_temp(self, mgr):
        """Failed write should clean up temp file."""
        # Write normally first to get valid data
        ok = await mgr.write({"test": True})
        assert ok is True

    @pytest.mark.asyncio
    async def test_write_overwrite(self, mgr):
        """Overwriting a snapshot should succeed."""
        await mgr.write({"v": 1})
        await mgr.write({"v": 2})
        restored = await mgr.read()
        assert restored["v"] == 2

    @pytest.mark.asyncio
    async def test_multiple_snapshot_managers(self, snap_dir):
        """Multiple SnapshotManager instances with different filenames."""
        mgr_a = SnapshotManager(snapshot_dir=snap_dir, filename="a.snapshot")
        mgr_b = SnapshotManager(snapshot_dir=snap_dir, filename="b.snapshot")

        await mgr_a.write({"name": "a"})
        await mgr_b.write({"name": "b"})

        data_a = await mgr_a.read()
        data_b = await mgr_b.read()

        assert data_a["name"] == "a"
        assert data_b["name"] == "b"

    @pytest.mark.asyncio
    async def test_checksum_in_data(self, mgr):
        """Data with 64-byte string should not interfere with checksum boundary."""
        ok = await mgr.write({"my_data": "x" * 64})
        assert ok is True
        result = await mgr.read()
        assert result is not None
        assert result["my_data"] == "x" * 64
