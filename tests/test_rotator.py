"""
Unit tests for storage.rotator — EventRotator with archive + cleanup.

Actual API:
  EventRotator(storage, max_rows=10000, archive_dir=None, check_interval_hours=6.0)
  - start() / stop()
  - rotate_if_needed() -> bool
  - _get_event_count() -> int
"""

import asyncio

import pytest
import pytest_asyncio

from storage.rotator import EventRotator
from storage.driver import SingleWriterStorage


@pytest_asyncio.fixture
async def storage(mem_db_path):
    s = SingleWriterStorage(mem_db_path)
    await s.start()
    # Create events table matching rotator's expected schema
    await s.execute_write("DROP TABLE IF EXISTS events")
    await s.execute_write("""
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'test',
            type TEXT NOT NULL,
            payload BLOB,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    yield s
    await s.stop()


@pytest_asyncio.fixture
async def rotator(storage):
    r = EventRotator(
        storage=storage,
        max_rows=5,
        check_interval_hours=0.0001,  # very fast for testing
    )
    yield r
    await r.stop()


class TestRotatorBasics:

    @pytest.mark.asyncio
    async def test_construction(self, storage):
        r = EventRotator(storage=storage, max_rows=1000, check_interval_hours=1)
        assert r.max_rows == 1000
        assert r.check_interval == 3600
        assert r._running is False

    @pytest.mark.asyncio
    async def test_start_stop(self, rotator):
        await rotator.start()
        assert rotator._running is True
        await rotator.stop()
        assert rotator._running is False

    @pytest.mark.asyncio
    async def test_stop_idempotent(self, rotator):
        await rotator.start()
        await rotator.stop()
        await rotator.stop()

    @pytest.mark.asyncio
    async def test_start_twice(self, rotator):
        await rotator.start()
        await rotator.start()


class TestRotatorCleanup:

    @pytest.mark.asyncio
    async def test_rotate_if_needed_below_limit(self, rotator, storage):
        """When count <= max_rows, rotate_if_needed returns False."""
        for i in range(3):
            await storage.execute_write(
                "INSERT INTO events (type, trace_id) VALUES (?, ?)",
                (f"test_{i}", f"trace-{i}"),
            )
        result = await rotator.rotate_if_needed()
        assert result is False

    @pytest.mark.asyncio
    async def test_rotate_if_needed_above_limit(self, rotator, storage):
        """When count > max_rows, rotation should occur."""
        for i in range(10):
            await storage.execute_write(
                "INSERT INTO events (type, trace_id) VALUES (?, ?)",
                (f"test_{i}", f"trace-{i}"),
            )
        await asyncio.sleep(0.05)
        result = await rotator.rotate_if_needed()
        assert result is True

    @pytest.mark.asyncio
    async def test_get_event_count(self, rotator, storage):
        await storage.execute_write("INSERT INTO events (type, trace_id) VALUES (?, ?)", ("count-test", "t-ct"))
        count = await rotator._get_event_count()
        assert count >= 1

    @pytest.mark.asyncio
    async def test_rotate_empty_db(self, rotator):
        result = await rotator.rotate_if_needed()
        assert result is False

    @pytest.mark.asyncio
    async def test_archive_file_created(self, rotator, storage):
        """After rotation above limit, database should be cleaned below max_rows."""
        for i in range(10):
            await storage.execute_write(
                "INSERT INTO events (type, trace_id) VALUES (?, ?)",
                (f"archive-test_{i}", f"trace-{i}"),
            )
        await asyncio.sleep(0.05)
        await rotator.rotate_if_needed()
        # After rotation, count should be <= max_rows
        count = await rotator._get_event_count()
        assert count <= rotator.max_rows + 5
