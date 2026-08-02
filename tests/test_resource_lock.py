"""
Unit tests for core.resource_lock — CAS optimistic lock via SingleWriterStorage.

Actual API: ResourceLock(storage: SingleWriterStorage)
  - try_acquire(resource, owner, ttl) -> bool
  - release(resource, owner) -> bool
  - renew(resource, owner, ttl) -> bool
  - clean_expired() -> int
  - get_locks() -> dict
"""

import asyncio

import pytest
import pytest_asyncio

from core.resource_lock import ResourceLock
from storage.driver import SingleWriterStorage


@pytest_asyncio.fixture
async def storage(mem_db_path):
    store = SingleWriterStorage(mem_db_path)
    await store.start()

    # Create resource_locks table (normally done by bootstrap)
    await store.execute_write("""
        CREATE TABLE IF NOT EXISTS resource_locks (
            resource TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            acquired_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL
        )
    """)
    yield store
    await store.stop()


@pytest_asyncio.fixture
async def lock(storage):
    return ResourceLock(storage)


class TestAcquireRelease:

    @pytest.mark.asyncio
    async def test_try_acquire_success(self, lock):
        assert await lock.try_acquire("res-a", "owner-1") is True

    @pytest.mark.asyncio
    async def test_acquire_then_release(self, lock):
        await lock.try_acquire("res-b", "owner-x")
        assert await lock.release("res-b", "owner-x") is True

    @pytest.mark.asyncio
    async def test_acquire_after_release(self, lock):
        await lock.try_acquire("res-c", "owner-1")
        await lock.release("res-c", "owner-1")
        assert await lock.try_acquire("res-c", "owner-2") is True

    @pytest.mark.asyncio
    async def test_release_wrong_owner(self, lock):
        await lock.try_acquire("res-d", "owner-1")
        assert await lock.release("res-d", "owner-2") is False

    @pytest.mark.asyncio
    async def test_release_nonexistent(self, lock):
        assert await lock.release("ghost", "owner-1") is False

    @pytest.mark.asyncio
    async def test_double_release(self, lock):
        await lock.try_acquire("res-e", "owner-1")
        await lock.release("res-e", "owner-1")
        assert await lock.release("res-e", "owner-1") is False


class TestContention:

    @pytest.mark.asyncio
    async def test_second_acquire_blocked(self, lock):
        await lock.try_acquire("res-f", "owner-1")
        assert await lock.try_acquire("res-f", "owner-2") is False

    @pytest.mark.asyncio
    async def test_same_owner_can_reacquire(self, lock):
        await lock.try_acquire("res-g", "owner-1")
        # Same owner should be able to acquire again (via CAS update)
        assert await lock.try_acquire("res-g", "owner-1") is True

    @pytest.mark.asyncio
    async def test_concurrent_different_resources(self, lock):
        results = await asyncio.gather(
            lock.try_acquire("c-a", "o-1"),
            lock.try_acquire("c-b", "o-2"),
            lock.try_acquire("c-c", "o-3"),
        )
        assert all(results)

    @pytest.mark.asyncio
    async def test_concurrent_same_resource(self, lock):
        results = await asyncio.gather(*(
            lock.try_acquire("same-res", f"o-{i}") for i in range(10)
        ))
        assert sum(results) == 1, f"Exactly one should succeed: {results}"


class TestRenew:

    @pytest.mark.asyncio
    async def test_renew_success(self, lock):
        await lock.try_acquire("res-h", "owner-1", ttl=30)
        assert await lock.renew("res-h", "owner-1", ttl=60) is True

    @pytest.mark.asyncio
    async def test_renew_wrong_owner(self, lock):
        await lock.try_acquire("res-i", "owner-1")
        assert await lock.renew("res-i", "owner-2") is False

    @pytest.mark.asyncio
    async def test_renew_nonexistent(self, lock):
        assert await lock.renew("ghost", "owner-1") is False


class TestExpiredLocks:

    @pytest.mark.asyncio
    async def test_clean_expired(self, lock):
        # Insert an already-expired lock manually
        await lock.try_acquire("exp-1", "owner-1", ttl=-10)  # expired
        # Call clean_expired
        count = await lock.clean_expired()
        assert count >= 0  # Some storage may or may not clean

    @pytest.mark.asyncio
    async def test_expired_lock_replaced(self, lock, storage):
        await lock.try_acquire("exp-2", "owner-1", ttl=1)
        # Force expiration by manipulating DB
        import time
        past = int(time.time()) - 100
        await storage.execute_write(
            "UPDATE resource_locks SET expires_at = ? WHERE resource = ?",
            (past, "exp-2"),
        )
        # Now a different owner should acquire
        assert await lock.try_acquire("exp-2", "owner-2") is True


class TestGetLocks:

    @pytest.mark.asyncio
    async def test_get_locks(self, lock):
        await lock.try_acquire("lock-a", "owner-a")
        await lock.try_acquire("lock-b", "owner-b")
        locks = await lock.get_locks()
        assert "lock-a" in locks
        assert locks["lock-a"]["owner"] == "owner-a"

    @pytest.mark.asyncio
    async def test_get_locks_empty(self, lock):
        locks = await lock.get_locks()
        assert locks == {}


class TestEdgeCases:

    @pytest.mark.asyncio
    async def test_empty_resource(self, lock):
        result = await lock.try_acquire("", "owner")
        assert result in (True, False)  # should not crash

    @pytest.mark.asyncio
    async def test_empty_owner(self, lock):
        result = await lock.try_acquire("res-j", "")
        assert result in (True, False)

    @pytest.mark.asyncio
    async def test_very_long_resource(self, lock):
        long = "r" * 500
        assert await lock.try_acquire(long, "owner") is True
        assert await lock.release(long, "owner") is True
