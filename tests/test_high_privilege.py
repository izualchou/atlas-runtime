"""
Unit tests for executors.high_privilege — ADB privileged operations.

Actual API: HighPrivilegeExecutor(adb_path="/system/bin/adb", timeout=30)
  - run_command(cmd, timeout) -> (rc, stdout, stderr)  # wraps SafeShellExecutor
  - execute(action) -> dict
  - switch_sim(sim_id, preferred_id) -> bool
  - set_prop(key, value) -> bool
  - get_prop(key) -> str

BUG IDENTIFICATION:
  B-050: switch_sim fallback command may set network type instead of SIM slot
  B-051: no ADB connectivity check before attempting commands
"""

import pytest

from executors.high_privilege import HighPrivilegeExecutor


class TestConstruction:

    def test_default(self):
        ex = HighPrivilegeExecutor()
        assert ex.timeout == 30
        assert ex.adb_path in ("/system/bin/adb", "adb")

    def test_custom(self):
        ex = HighPrivilegeExecutor(adb_path="/custom/adb", timeout=15)
        assert ex.adb_path == "/custom/adb"
        assert ex.timeout == 15


class TestCommandBuilding:

    def test_set_prop_cmd(self):
        ex = HighPrivilegeExecutor()
        cmd = ex._adb_cmd("shell", "setprop", "test.key", "test.value")
        assert ex.adb_path in cmd
        assert "shell" in cmd
        assert "setprop" in cmd
        assert "test.key" in cmd

    def test_get_prop_cmd(self):
        ex = HighPrivilegeExecutor()
        cmd = ex._adb_cmd("shell", "getprop", "ro.build.version.sdk")
        assert "getprop" in cmd


class TestSwitchSim:

    def test_invalid_sim_id(self):
        ex = HighPrivilegeExecutor()
        # switch_sim expects integer sim_id
        result = ex.switch_sim(sim_id=-1)
        assert result is False

    def test_invalid_preferred_id(self):
        ex = HighPrivilegeExecutor()
        result = ex.switch_sim(sim_id=0, preferred_id=-1)
        assert result is False


class TestExecute:

    @pytest.mark.asyncio
    async def test_execute_shell_command(self):
        """Without ADB, executing shell commands through ADB will fail gracefully."""
        ex = HighPrivilegeExecutor()
        result = await ex.execute({"command": "echo hello", "type": "shell"})
        # Will fail because no ADB device connected; this is expected
        assert result["status"] == "error"
        assert result["returncode"] != 0

    @pytest.mark.asyncio
    async def test_execute_no_command(self):
        ex = HighPrivilegeExecutor()
        result = await ex.execute({"type": "shell"})
        assert result["status"] == "error"
        assert "No command" in result.get("error", "")
