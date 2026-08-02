"""
Unit tests for storage.battery_aware — BatteryAwareCheckpoint.

Actual API:
  BatteryAwareCheckpoint(storage, check_interval_seconds=30,
                         charging_autocheckpoint=1000, battery_autocheckpoint=10000,
                         charging_batch_delay_ms=50, battery_batch_delay_ms=200)
  - start() / stop()
  - set_health_checker(checker)
  - _get_charging_status() -> bool  (returns True by default = conservative)
  - _apply_policy(is_charging)
"""

import asyncio

import pytest
import pytest_asyncio

from storage.battery_aware import BatteryAwareCheckpoint
from storage.driver import SingleWriterStorage


@pytest_asyncio.fixture
async def storage(mem_db_path):
    s = SingleWriterStorage(mem_db_path)
    await s.start()
    yield s
    await s.stop()


@pytest_asyncio.fixture
async def battery(storage):
    b = BatteryAwareCheckpoint(storage=storage, check_interval_seconds=1)
    yield b
    await b.stop()


class TestBatteryAwareBasics:

    @pytest.mark.asyncio
    async def test_construction(self, storage):
        b = BatteryAwareCheckpoint(storage=storage, check_interval_seconds=30)
        assert b.check_interval == 30
        assert b._running is False

    @pytest.mark.asyncio
    async def test_start_stop(self, battery):
        await battery.start()
        assert battery._running is True
        await battery.stop()
        assert battery._running is False

    @pytest.mark.asyncio
    async def test_stop_idempotent(self, battery):
        await battery.start()
        await battery.stop()
        await battery.stop()

    @pytest.mark.asyncio
    async def test_start_twice(self, battery):
        await battery.start()
        await battery.start()  # should be no-op


class TestChargingStatus:

    @pytest.mark.asyncio
    async def test_default_charging_status(self, battery):
        """Without health_checker, defaults to True (conservative)."""
        status = await battery._get_charging_status()
        assert status is True  # conservative default

    @pytest.mark.asyncio
    async def test_with_health_checker(self, battery):
        """With a health_checker that reports battery."""
        class FakeHealth:
            async def get_charging_status(self):
                return False  # not charging
        battery.set_health_checker(FakeHealth())
        status = await battery._get_charging_status()
        assert status is False

    @pytest.mark.asyncio
    async def test_health_checker_error_fallback(self, battery):
        """If health_checker throws, falls back to True."""
        class BadHealth:
            async def get_charging_status(self):
                raise RuntimeError("no battery info")
        battery.set_health_checker(BadHealth())
        status = await battery._get_charging_status()
        assert status is True

    @pytest.mark.asyncio
    async def test_health_checker_none_result(self, battery):
        """If health_checker returns None, falls back to True."""
        class NoneHealth:
            async def get_charging_status(self):
                return None
        battery.set_health_checker(NoneHealth())
        status = await battery._get_charging_status()
        assert status is True


class TestPolicyApplication:

    @pytest.mark.asyncio
    async def test_apply_charging_policy(self, battery, storage):
        await battery._apply_policy(is_charging=True)
        # Should not crash

    @pytest.mark.asyncio
    async def test_apply_battery_policy(self, battery, storage):
        await battery._apply_policy(is_charging=False)
        # Should not crash
