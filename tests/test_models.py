"""
Unit tests for models/ — pure data contracts.

Tests cover the v9.0 models layer: health, SIM, task, and errors.
"""

import pytest

from models import (
    BatteryStatus,
    MemoryStatus,
    SystemHealth,
    SimInfo,
    SimStatus,
    SimSwitchResult,
    Task,
    TaskStatus,
    StorageFullError,
    StorageError,
    BackpressureError,
)


# ---------------------------------------------------------------------------
# Health models
# ---------------------------------------------------------------------------

class TestBatteryStatus:
    def test_default_values(self):
        bs = BatteryStatus()
        assert bs.level == 100
        assert bs.charging is False
        assert bs.temperature_c == 25.0
        assert bs.health == "unknown"

    def test_custom_values(self):
        bs = BatteryStatus(level=85, charging=True, temperature_c=32.0)
        assert bs.level == 85
        assert bs.charging is True
        assert bs.temperature_c == 32.0

    def test_mutable_after_default(self):
        bs = BatteryStatus()
        bs.level = 99
        assert bs.level == 99


class TestSystemHealth:
    def test_all_fields_present(self):
        sh = SystemHealth()
        assert hasattr(sh, "battery")
        assert hasattr(sh, "memory")
        assert isinstance(sh.battery, BatteryStatus)
        assert isinstance(sh.memory, MemoryStatus)

    def test_custom_battery(self):
        battery = BatteryStatus(level=50)
        sh = SystemHealth(battery=battery)
        assert sh.battery is battery
        assert sh.battery.level == 50

    def test_class_thresholds(self):
        assert SystemHealth.LOW_BATTERY_THRESHOLD == 15
        assert SystemHealth.CRITICAL_BATTERY_THRESHOLD == 5
        assert SystemHealth.HIGH_MEMORY_THRESHOLD == 85.0


# ---------------------------------------------------------------------------
# Task models
# ---------------------------------------------------------------------------

class TestTaskStatus:
    def test_all_statuses_defined(self):
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.SCHEDULED.value == "scheduled"
        assert TaskStatus.SUCCESS.value == "success"
        assert TaskStatus.FAILED.value == "failed"

    def test_status_is_enum(self):
        assert isinstance(TaskStatus.PENDING, TaskStatus)


class TestTask:
    def test_minimal_construction(self):
        t = Task(id="t1", action={"cmd": "echo hello"})
        assert t.id == "t1"
        assert t.status == TaskStatus.PENDING
        assert t.priority == 5
        assert t.retries == 0
        assert t.max_retries == 3

    def test_resource_extracted_from_action(self):
        t = Task(id="t2", action={"cmd": "ls", "resource": "camera"})
        assert t.resource == "camera"

    def test_resource_defaults_to_none(self):
        t = Task(id="t3", action={"cmd": "date"})
        assert t.resource is None

    def test_created_at_is_set(self):
        import time
        before = time.time()
        t = Task(id="t4", action={"cmd": "true"})
        after = time.time()
        assert before <= t.created_at <= after

    def test_custom_priority(self):
        t = Task(id="t5", action={}, priority=1)
        assert t.priority == 1


# ---------------------------------------------------------------------------
# SIM models
# ---------------------------------------------------------------------------

class TestSimSwitchResult:
    def test_success_result(self):
        r = SimSwitchResult(success=True)
        assert r.success is True

    def test_failure_result(self):
        r = SimSwitchResult(success=False, error="no permission")
        assert r.success is False
        assert r.error == "no permission"


class TestSimInfo:
    def test_requires_sub_id_and_slot_index(self):
        s = SimInfo(sub_id=1, slot_index=0)
        assert s.sub_id == 1
        assert s.slot_index == 0
        assert s.display_name == ""
        assert s.carrier_name == ""

    def test_with_custom_name(self):
        s = SimInfo(sub_id=2, slot_index=1, display_name="AT&T", carrier_name="att")
        assert s.display_name == "AT&T"
        assert s.carrier_name == "att"

    def test_name_property_falls_back(self):
        s = SimInfo(sub_id=3, slot_index=0)
        assert s.name == "SIM-3"


# ---------------------------------------------------------------------------
# Error models
# ---------------------------------------------------------------------------

class TestStorageError:
    def test_is_exception(self):
        e = StorageError("disk error")
        assert isinstance(e, Exception)
        assert str(e) == "disk error"


class TestStorageFullError:
    def test_is_atlas_error(self):
        from models.errors import AtlasError
        e = StorageFullError("quota exceeded")
        assert isinstance(e, AtlasError)

    def test_is_not_storage_error(self):
        """StorageFullError 继承 AtlasError，与 StorageError 是兄弟关系。"""
        e = StorageFullError("quota exceeded")
        assert not isinstance(e, StorageError)


class TestBackpressureError:
    def test_is_exception(self):
        e = BackpressureError("queue full")
        assert isinstance(e, Exception)
        assert "queue full" in str(e)
