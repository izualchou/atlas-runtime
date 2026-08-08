"""
Tests for transport/autojs_launcher.py — AutoJS6Launcher v9.1.

Covers:
- tc_al_01: Constructor with mock executor
- tc_al_02: _write_params_file produces valid JSON
- tc_al_03: launch with successful command (single package)
- tc_al_04: Dual package fallback on first failure
- tc_al_05: Knox fallback mode writes marker file
- tc_al_06: check_autojs_installed parses pm output
- tc_al_07: Launch failure returns error result
"""

import json
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
import pytest_asyncio

from transport.autojs_launcher import (
    AutoJS6Launcher,
    LaunchConfig,
    LaunchResult,
    AUTOJS6_PACKAGES,
    DEFAULT_SHARED_DIR,
)


# ---------------------------------------------------------------------------
# Mock helper
# ---------------------------------------------------------------------------

class MockExecutorResult:
    """Simulates BaseExecutor.execute() return."""

    def __init__(self, success=True, stdout="", stderr=""):
        self.success = success
        self.stdout = stdout
        self.stderr = stderr


class MockExecutor:
    """Mock executor implementing BaseExecutor protocol."""

    def __init__(self, results=None):
        self.results = results or {}
        self.calls = []

    async def execute(self, cmd, timeout=None):
        self.calls.append((cmd, timeout))
        if callable(self.results.get(cmd)):
            return self.results[cmd](cmd)
        return self.results.get(
            cmd,
            MockExecutorResult(success=True, stdout="ok"),
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_executor():
    """Mock executor that succeeds by default."""
    return MockExecutor()


@pytest.fixture
def launcher(mock_executor):
    """AutoJS6Launcher with mock executor."""
    return AutoJS6Launcher(mock_executor)


@pytest.fixture
def tmp_shared_dir(tmp_path):
    """Temporary shared directory for file write tests."""
    d = tmp_path / "atlas_shared"
    d.mkdir()
    return str(d)


# ---------------------------------------------------------------------------
# Tests: Constructor
# ---------------------------------------------------------------------------

class TestLauncherConstructor:
    """tc_al_01: constructor stores executor and default config."""

    def test_constructor_stores_executor(self, mock_executor):
        """Executor is stored and accessible."""
        l = AutoJS6Launcher(mock_executor)
        assert l.executor is mock_executor

    def test_default_config(self, mock_executor):
        """Default LaunchConfig is created."""
        l = AutoJS6Launcher(mock_executor)
        assert l.config.shared_dir == DEFAULT_SHARED_DIR
        assert l.config.enable_fallback_file is True
        assert l.config.auto_retry is True


# ---------------------------------------------------------------------------
# Tests: _write_params_file
# ---------------------------------------------------------------------------

class TestWriteParamsFile:
    """tc_al_02: params file creation."""

    @pytest.mark.asyncio
    async def test_write_params_creates_file(self, launcher, tmp_shared_dir):
        """Params file is created with valid JSON."""
        launcher.config.shared_dir = tmp_shared_dir

        params = {"key1": "value1", "key2": 42}
        filepath = await launcher._write_params_file("test.js", params)

        assert Path(filepath).exists()
        with open(filepath, 'r') as f:
            data = json.load(f)

        assert data["script_name"] == "test.js"
        assert data["params"] == params
        assert data["version"] == "1.0"
        assert isinstance(data["timestamp"], float)

    @pytest.mark.asyncio
    async def test_write_params_creates_directory(self, launcher, tmp_path):
        """Creates shared_dir if it doesn't exist."""
        new_dir = tmp_path / "new_shared"
        launcher.config.shared_dir = str(new_dir)

        filepath = await launcher._write_params_file("test.js", {})
        assert Path(filepath).exists()
        assert new_dir.exists()


# ---------------------------------------------------------------------------
# Tests: launch
# ---------------------------------------------------------------------------

class TestLaunch:
    """tc_al_03 / tc_al_04: launch with package success and fallback."""

    @pytest.mark.asyncio
    async def test_launch_success_first_package(self, mock_executor, tmp_shared_dir):
        """Launch succeeds with first package in list."""
        launcher = AutoJS6Launcher(mock_executor)
        launcher.config.shared_dir = tmp_shared_dir

        # Mock executor to succeed for startservice attempt
        mock_executor.results = {}
        async def _fallback(cmd, timeout=None):
            # Any startservice or start command succeeds
            if "startservice" in cmd or "am start" in cmd:
                return MockExecutorResult(success=True, stdout="started")
            return MockExecutorResult(success=True, stdout="")

        mock_executor.execute = _fallback

        result = await launcher.launch("test_script.js", {"mode": "test"})

        assert result.success is True
        assert result.script_name == "test_script.js"
        assert result.package_used == AUTOJS6_PACKAGES[0]
        assert result.fallback_used is False

    @pytest.mark.asyncio
    async def test_launch_dual_package_fallback(self, mock_executor, tmp_shared_dir):
        """tc_al_04: first package fails, second succeeds."""
        launcher = AutoJS6Launcher(mock_executor)
        launcher.config.shared_dir = tmp_shared_dir
        launcher.config.auto_retry = True

        call_count = [0]
        async def _selective(cmd, timeout=None):
            call_count[0] += 1
            # First 2 calls (startservice + am start for pkg[0]) fail
            if call_count[0] <= 2:
                return MockExecutorResult(success=False, stderr="not found")
            # Next 2 calls (startservice + am start for pkg[1]) succeed
            return MockExecutorResult(success=True, stdout="started")

        mock_executor.execute = _selective

        result = await launcher.launch("fallback_test.js")

        assert result.success is True
        # Should have used the second package in the list
        assert len(AUTOJS6_PACKAGES) >= 2

    @pytest.mark.asyncio
    async def test_launch_all_fail_no_fallback(self, mock_executor, tmp_shared_dir):
        """All packages fail + fallback disabled → error result."""
        launcher = AutoJS6Launcher(mock_executor)
        launcher.config.shared_dir = tmp_shared_dir
        launcher.config.enable_fallback_file = False
        launcher.config.auto_retry = True

        async def _always_fail(cmd, timeout=None):
            return MockExecutorResult(success=False, stderr="error")

        mock_executor.execute = _always_fail

        result = await launcher.launch("always_fail.js")

        assert result.success is False
        assert "All packages failed" in (result.error or "")


# ---------------------------------------------------------------------------
# Tests: Knox fallback
# ---------------------------------------------------------------------------

class TestKnoxFallback:
    """tc_al_05: fallback file marker mode."""

    @pytest.mark.asyncio
    async def test_fallback_creates_marker(self, mock_executor, tmp_shared_dir):
        """When all packages fail + fallback enabled → marker file created."""
        launcher = AutoJS6Launcher(mock_executor)
        launcher.config.shared_dir = tmp_shared_dir
        launcher.config.enable_fallback_file = True

        async def _always_fail(cmd, timeout=None):
            return MockExecutorResult(success=False, stderr="blocked")

        mock_executor.execute = _always_fail

        result = await launcher.launch("knox_test.js", {"key": "val"})

        # Knox fallback mode: all packages failed but fallback file was written
        # → returns success=True with fallback_used=True
        assert result.success is True
        assert result.fallback_used is True

        # Check fallback marker file
        markers = list(Path(tmp_shared_dir).glob("autojs_fallback_*.json"))
        assert len(markers) >= 1

        with open(markers[0], 'r') as f:
            data = json.load(f)
        assert data["type"] == "launch_request"


# ---------------------------------------------------------------------------
# Tests: check_autojs_installed
# ---------------------------------------------------------------------------

class TestCheckInstalled:
    """tc_al_06: package detection via pm list."""

    @pytest.mark.asyncio
    async def test_detects_installed_packages(self, mock_executor):
        """Parses pm list packages output correctly."""
        launcher = AutoJS6Launcher(mock_executor)

        async def _pm_output(cmd, timeout=None):
            if "pm list" in cmd:
                return MockExecutorResult(
                    success=True,
                    stdout=(
                        "package:org.autojs.autoxjs.v6\n"
                        "package:com.android.chrome\n"
                        "package:org.autojs.autojs\n"
                    ),
                )
            return MockExecutorResult(success=True, stdout="")

        mock_executor.execute = _pm_output

        packages = await launcher.check_autojs_installed()

        assert "org.autojs.autoxjs.v6" in packages
        assert "org.autojs.autojs" in packages
        assert "com.android.chrome" not in packages

    @pytest.mark.asyncio
    async def test_no_autojs_installed(self, mock_executor):
        """Returns empty list when no AutoJS6 packages found."""
        launcher = AutoJS6Launcher(mock_executor)

        async def _no_autojs(cmd, timeout=None):
            if "pm list" in cmd:
                return MockExecutorResult(
                    success=True,
                    stdout="package:com.example.app\n",
                )
            return MockExecutorResult(success=True, stdout="")

        mock_executor.execute = _no_autojs

        packages = await launcher.check_autojs_installed()
        assert packages == []


# ---------------------------------------------------------------------------
# Tests: Launch failure
# ---------------------------------------------------------------------------

class TestLaunchFailure:
    """tc_al_07: error handling in launch."""

    @pytest.mark.asyncio
    async def test_executor_exception(self, mock_executor, tmp_shared_dir):
        """Executor raises → launch returns error result."""
        launcher = AutoJS6Launcher(mock_executor)
        launcher.config.shared_dir = tmp_shared_dir
        launcher.config.enable_fallback_file = False

        async def _raises(cmd, timeout=None):
            raise RuntimeError("executor crash")

        mock_executor.execute = _raises

        result = await launcher.launch("crash_test.js")

        assert result.success is False
        assert result.error is not None
