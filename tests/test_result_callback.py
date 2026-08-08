"""
Tests for transport/result_callback.py — ResultCallback v9.1.

Covers:
- tc_rc_01: Constructor with default config
- tc_rc_02: Constructor with custom config
- tc_rc_03: _build_payload produces valid JSON-serializable dict
- tc_rc_04: _write_atomic succeeds with temp directory
- tc_rc_05: Disk space check warns on low space (mock)
- tc_rc_06: _prune_old_files cleans excess history files
- tc_rc_07: get_stats tracks write counts correctly
"""

import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from transport.result_callback import (
    ResultCallback,
    ResultCallbackConfig,
    CallbackResult,
    DEFAULT_SHARED_DIR,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def default_callback():
    """ResultCallback with default config."""
    return ResultCallback()


@pytest.fixture
def custom_config():
    """Custom ResultCallbackConfig with small max_history."""
    return ResultCallbackConfig(
        max_history_files=5,
        min_free_space_mb=1,
        enable_history=True,
        enable_latest=True,
    )


@pytest.fixture
def custom_callback(custom_config):
    """ResultCallback with custom config."""
    return ResultCallback(config=custom_config)


@pytest.fixture
def tmp_shared_dir(tmp_path):
    """Temporary shared directory for atomic write tests."""
    d = tmp_path / "atlas_shared"
    d.mkdir()
    return str(d)


# ---------------------------------------------------------------------------
# Mock Task helper
# ---------------------------------------------------------------------------

class MockTask:
    """Minimal Task mock for callback testing."""

    def __init__(self, task_id="mock-001", status=None, action="test.action"):
        self.id = task_id
        self.status = MagicMock()
        self.status.value = status or "SUCCESS"
        self.action = action
        self.created_at = time.time()
        self.completed_at = time.time()
        self.correlation_id = None
        self.result = None
        self.error = None

    def with_result(self, exit_code=0, stdout="ok", stderr=""):
        self.result = MagicMock()
        self.result.exit_code = exit_code
        self.result.stdout = stdout
        self.result.stderr = stderr
        return self

    def with_error(self, msg="test error"):
        self.error = msg
        return self

    def with_correlation_id(self, cid):
        self.correlation_id = cid
        return self


# ---------------------------------------------------------------------------
# Tests: Constructor
# ---------------------------------------------------------------------------

class TestResultCallbackConstructor:
    """tc_rc_01 / tc_rc_02: constructor with default and custom config."""

    def test_default_config(self):
        """tc_rc_01: default config uses DEFAULT_SHARED_DIR."""
        rc = ResultCallback()
        assert rc.config.shared_dir == DEFAULT_SHARED_DIR
        assert rc.config.max_history_files == 100
        assert rc.config.min_free_space_mb == 10
        assert rc.config.enable_history is True
        assert rc.config.enable_latest is True

    def test_custom_config(self):
        """tc_rc_02: custom config values are respected."""
        rc = ResultCallback(config=ResultCallbackConfig(
            shared_dir="/tmp/test",
            max_history_files=3,
            min_free_space_mb=5,
        ))
        assert rc.config.shared_dir == "/tmp/test"
        assert rc.config.max_history_files == 3
        assert rc.config.min_free_space_mb == 5


# ---------------------------------------------------------------------------
# Tests: _build_payload
# ---------------------------------------------------------------------------

class TestBuildPayload:
    """tc_rc_03: _build_payload output validation."""

    def test_basic_payload(self, default_callback):
        """Payload contains required fields."""
        task = MockTask("task-abc")
        payload = default_callback._build_payload(task)

        assert payload["version"] == "1.0"
        assert payload["task_id"] == "task-abc"
        assert payload["status"] == "SUCCESS"
        assert payload["action"] == "test.action"
        assert isinstance(payload["created_at"], float)

        # Verify JSON-serializable
        json.dumps(payload)

    def test_payload_with_result(self, default_callback):
        """Payload includes result fields when task has result."""
        task = MockTask("task-xyz").with_result(exit_code=0, stdout="hello")
        payload = default_callback._build_payload(task)

        assert payload["result"]["exit_code"] == 0
        assert payload["result"]["stdout"] == "hello"

    def test_payload_with_error(self, default_callback):
        """Payload includes error field when task has error."""
        task = MockTask("task-err").with_error("command not found")
        payload = default_callback._build_payload(task)

        assert payload["error"] == "command not found"
        assert "result" not in payload

    def test_payload_with_correlation_id(self, default_callback):
        """Payload includes correlation_id when set."""
        task = MockTask("task-cid").with_correlation_id("req-42")
        payload = default_callback._build_payload(task)

        assert payload["correlation_id"] == "req-42"


# ---------------------------------------------------------------------------
# Tests: _write_atomic
# ---------------------------------------------------------------------------

class TestWriteAtomic:
    """tc_rc_04: atomic write in temporary directory."""

    @pytest.mark.asyncio
    async def test_write_success(self, custom_callback, tmp_shared_dir):
        """Write to tmp directory succeeds and file is valid JSON."""
        custom_callback.config.shared_dir = tmp_shared_dir

        payload = {"test": "data", "number": 42}
        result = await custom_callback._write_atomic("last_result.json", payload)

        assert result.success is True
        assert result.size_bytes > 0

        target = Path(tmp_shared_dir) / "last_result.json"
        assert target.exists()
        with open(target, 'r') as f:
            data = json.load(f)
        assert data["test"] == "data"

    @pytest.mark.asyncio
    async def test_write_multiple(self, custom_callback, tmp_shared_dir):
        """Multiple writes to same filename overwrite correctly."""
        custom_callback.config.shared_dir = tmp_shared_dir

        for i in range(3):
            result = await custom_callback._write_atomic(
                "last_result.json",
                {"seq": i}
            )
            assert result.success

        target = Path(tmp_shared_dir) / "last_result.json"
        with open(target, 'r') as f:
            data = json.load(f)
        assert data["seq"] == 2


# ---------------------------------------------------------------------------
# Tests: Disk space check
# ---------------------------------------------------------------------------

class TestDiskSpaceCheck:
    """tc_rc_05: disk space warning threshold."""

    def test_ok_space(self, custom_callback, tmp_shared_dir):
        """No warning when free space is above threshold."""
        custom_callback.config.shared_dir = tmp_shared_dir
        custom_callback.config.min_free_space_mb = 1

        # Should not raise
        custom_callback._check_disk_space(Path(tmp_shared_dir))

    def test_low_space_warning(self, custom_callback, tmp_shared_dir):
        """Warning logged when free space below threshold (via mock)."""
        custom_callback.config.shared_dir = tmp_shared_dir
        custom_callback.config.min_free_space_mb = 999999  # unrealistically high

        with patch.object(custom_callback.__class__, '_check_disk_space',
                          wraps=custom_callback._check_disk_space) as spy:
            import logging
            with patch.object(logging.getLogger("Atlas.ResultCallback"), 'warning') as mock_warn:
                spy(Path(tmp_shared_dir))
                mock_warn.assert_called_once()
                assert "low disk space" in mock_warn.call_args[0][0]


# ---------------------------------------------------------------------------
# Tests: Prune old files
# ---------------------------------------------------------------------------

class TestPruneOldFiles:
    """tc_rc_06: history file cleanup."""

    @pytest.mark.asyncio
    async def test_prune_excess_files(self, custom_callback, tmp_shared_dir):
        """Old files beyond max_history_files are deleted."""
        custom_callback.config.shared_dir = tmp_shared_dir
        custom_callback.config.max_history_files = 3

        # Create 8 history files
        for i in range(8):
            f = Path(tmp_shared_dir) / f"result_{i}_test.json"
            f.write_text(json.dumps({"idx": i}))
            # Stagger mtime
            os.utime(f, (time.time() - 100 + i * 10, time.time() - 100 + i * 10))

        # Also create last_result.json (should NOT be pruned)
        last = Path(tmp_shared_dir) / "last_result.json"
        last.write_text(json.dumps({"last": True}))

        await custom_callback._prune_old_files()

        remaining = sorted(Path(tmp_shared_dir).glob("result_*.json"))
        assert len(remaining) == 3
        assert last.exists()

    @pytest.mark.asyncio
    async def test_prune_nonexistent_dir(self, default_callback):
        """Prune skips gracefully for nonexistent directory."""
        default_callback.config.shared_dir = "/nonexistent/path/xyz"
        # Should not raise
        await default_callback._prune_old_files()


# ---------------------------------------------------------------------------
# Tests: Stats tracking
# ---------------------------------------------------------------------------

class TestStats:
    """tc_rc_07: write statistics."""

    def test_initial_stats(self, default_callback):
        """Stats start at zero."""
        stats = default_callback.get_stats()
        assert stats["total_writes"] == 0
        assert stats["failed_writes"] == 0
        assert stats["last_write_time"] is None

    @pytest.mark.asyncio
    async def test_stats_after_write(self, custom_callback, tmp_shared_dir):
        """Stats increment after successful write."""
        custom_callback.config.shared_dir = tmp_shared_dir
        custom_callback.config.enable_history = False

        task = MockTask("stats-test")
        await custom_callback.on_task_complete(task)

        stats = custom_callback.get_stats()
        assert stats["total_writes"] >= 1
        assert stats["failed_writes"] == 0
        assert stats["last_write_time"] is not None
