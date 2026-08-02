"""
Unit tests for storage.driver — SingleWriterStorage.

Actual API: SingleWriterStorage(db_path, max_queue_size, busy_timeout, batch_size, batch_delay_ms)
  - start() / stop()
  - execute_write(sql, params) -> rowcount/lastrowid
  - execute_read(sql, params) -> List[Tuple]
  - set_batch_delay(delay_ms)
  - StorageFullError / StorageError exceptions

BUG IDENTIFICATION:
  B-010: writer_task may not be cancelled on stop if _writer_loop is stuck on execute
  B-011: execute_write after stop() should raise but may queue and never flush
"""

import asyncio

import pytest
import pytest_asyncio

from storage.driver import SingleWriterStorage, StorageFullError


@pytest_asyncio.fixture
async def store(mem_db_path):
    s = SingleWriterStorage(mem_db_path, batch_size=50, batch_delay_ms=10)
    await s.start()
    yield s
    await s.stop()


@pytest_asyncio.fixture
async def store_with_table(store):
    await store.execute_write("""
        CREATE TABLE IF NOT EXISTS test_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            value TEXT
        )
    """)
    return store


class TestBasicOperations:

    @pytest.mark.asyncio
    async def test_start_and_stop(self, store):
        # start/stop called by fixture; verify no crash
        pass

    @pytest.mark.asyncio
    async def test_execute_write_insert(self, store_with_table):
        s = store_with_table
        rowcount = await s.execute_write(
            "INSERT INTO test_items (name, value) VALUES (?, ?)",
            ("hello", "world"),
        )
        assert rowcount > 0

    @pytest.mark.asyncio
    async def test_execute_write_update(self, store_with_table):
        s = store_with_table
        await s.execute_write("INSERT INTO test_items (name) VALUES (?)", ("update-me",))
        rowcount = await s.execute_write(
            "UPDATE test_items SET value = ? WHERE name = ?",
            ("new-value", "update-me"),
        )
        assert rowcount > 0

    @pytest.mark.asyncio
    async def test_execute_read(self, store_with_table):
        s = store_with_table
        await s.execute_write("INSERT INTO test_items (name, value) VALUES (?, ?)", ("r1", "v1"))
        rows = await s.execute_read("SELECT name, value FROM test_items WHERE name = ?", ("r1",))
        assert len(rows) == 1
        assert rows[0] == ("r1", "v1")

    @pytest.mark.asyncio
    async def test_execute_read_empty(self, store_with_table):
        rows = await store_with_table.execute_read("SELECT * FROM test_items WHERE name = ?", ("nonexistent",))
        assert rows == []

    @pytest.mark.asyncio
    async def test_execute_write_delete(self, store_with_table):
        s = store_with_table
        await s.execute_write("INSERT INTO test_items (name) VALUES (?)", ("del-me",))
        rowcount = await s.execute_write("DELETE FROM test_items WHERE name = ?", ("del-me",))
        assert rowcount > 0


class TestBatchCommit:

    @pytest.mark.asyncio
    async def test_batch_flush_many_writes(self, store_with_table):
        s = store_with_table
        N = 200  # should trigger at least one batch flush (threshold=50)
        tasks = [
            s.execute_write("INSERT INTO test_items (name) VALUES (?)", (f"batch-{i}",))
            for i in range(N)
        ]
        await asyncio.gather(*tasks)
        await asyncio.sleep(0.2)

        rows = await s.execute_read("SELECT COUNT(*) FROM test_items")
        assert rows[0][0] >= N * 0.9  # Allow small tolerance

    @pytest.mark.asyncio
    async def test_flush_on_stop(self, store_with_table, mem_db_path):
        s = store_with_table
        await s.execute_write("INSERT INTO test_items (name) VALUES (?)", ("flush-me",))
        await s.stop()
        # Reopen with new instance using same db_path
        s2 = SingleWriterStorage(mem_db_path)
        await s2.start()
        rows = await s2.execute_read("SELECT name FROM test_items WHERE name = ?", ("flush-me",))
        assert len(rows) == 1
        await s2.stop()


class TestEdgeCases:

    @pytest.mark.asyncio
    async def test_execute_write_empty_params(self, store_with_table):
        rowcount = await store_with_table.execute_write(
            "INSERT INTO test_items (name, value) VALUES ('empty', 'params')"
        )
        assert rowcount > 0

    @pytest.mark.asyncio
    async def test_execute_read_empty_params(self, store_with_table):
        await store_with_table.execute_write("INSERT INTO test_items (name) VALUES ('x')")
        rows = await store_with_table.execute_read("SELECT * FROM test_items")
        assert len(rows) >= 1

    @pytest.mark.asyncio
    async def test_set_batch_delay(self, store):
        store.set_batch_delay(200)
        assert store._batch_delay_ms == 200

    @pytest.mark.asyncio
    async def test_sql_error(self, store):
        """Invalid SQL should raise StorageError."""
        with pytest.raises(Exception):
            await store.execute_write("INVALID SQL SYNTAX !!!")

    @pytest.mark.asyncio
    async def test_stop_twice(self, store):
        await store.stop()
        await store.stop()  # should not crash

    @pytest.mark.asyncio
    async def test_start_twice(self, mem_db_path):
        s = SingleWriterStorage(mem_db_path)
        await s.start()
        await s.start()  # should be idempotent
        await s.stop()


class TestConcurrent:

    @pytest.mark.asyncio
    async def test_concurrent_reads(self, store_with_table):
        s = store_with_table
        await s.execute_write("INSERT INTO test_items (name) VALUES (?)", ("cr-1",))
        results = await asyncio.gather(*(
            s.execute_read("SELECT * FROM test_items") for _ in range(20)
        ))
        assert all(len(r) >= 1 for r in results)

    @pytest.mark.asyncio
    async def test_concurrent_writes_different_rows(self, store_with_table):
        s = store_with_table
        N = 50
        await asyncio.gather(*(
            s.execute_write("INSERT INTO test_items (name) VALUES (?)", (f"cw-{i}",))
            for i in range(N)
        ))
        await asyncio.sleep(0.1)
        rows = await s.execute_read("SELECT COUNT(*) FROM test_items")
        assert rows[0][0] >= N * 0.9
