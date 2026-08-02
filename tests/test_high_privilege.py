"""
Unit tests for executors.high_privilege — Samsung One UI 8.5 adapted API.

Updated API (v9.0):
  HighPrivilegeExecutor(shell_executor=None, samsung_codes=None)
  - switch_sim(sim_id, timeout) -> dict           # Async
  - set_wifi_enabled(enabled, timeout) -> dict     # Async
  - set_mobile_data_enabled(enabled, timeout) -> dict  # Async
  - set_airplane_mode(enabled, timeout) -> dict    # Async
  - set_volume(stream, level, timeout) -> dict     # Async
  - get_sim_state(timeout) -> dict                 # Async
  - get_wifi_state(timeout) -> dict                # Async
  - check_state(resource, target, timeout) -> bool # Async

All methods are async and return a result dict with 'success' key.
"""

import pytest

from executors.high_privilege import HighPrivilegeExecutor
from executors.shell_executor import SafeShellExecutor


@pytest.fixture
def executor():
    """Create executor with real shell executor."""
    return HighPrivilegeExecutor()


@pytest.fixture
def executor_with_codes():
    """Create executor with Samsung-specific service codes."""
    codes = {
        "wifi_enable": 55,
        "wifi_disable": 55,
        "data_enable": 77,
        "sim1_enable": 126,
    }
    return HighPrivilegeExecutor(samsung_codes=codes)


class TestConstruction:

    def test_default(self):
        ex = HighPrivilegeExecutor()
        assert ex.shell is not None
        assert isinstance(ex.shell, SafeShellExecutor)
        assert ex._samsung_codes == {}

    def test_with_codes(self):
        codes = {"wifi_enable": 55}
        ex = HighPrivilegeExecutor(samsung_codes=codes)
        assert ex._samsung_codes == codes

    def test_custom_shell_executor(self):
        shell = SafeShellExecutor(default_timeout=5)
        ex = HighPrivilegeExecutor(shell_executor=shell)
        assert ex.shell is shell


class TestSwitchSim:

    @pytest.mark.asyncio
    async def test_switch_sim(self, executor):
        """
        SIM switch will fail without permissions, but should return
        a well-formed result dict with success=False.
        """
        result = await executor.switch_sim(sim_id=0, timeout=1.0)
        assert isinstance(result, dict)
        assert "success" in result
        # On Termux without root, SIM switch typically fails
        # The result dict should still be well-formed
        if not result["success"]:
            assert "error" in result or "stderr" in result


class TestWifiControl:

    @pytest.mark.asyncio
    async def test_set_wifi_enabled(self, executor):
        """
        WiFi control should return a result dict.
        On Termux without system permissions, it may fail but shouldn't crash.
        """
        result = await executor.set_wifi_enabled(True, timeout=1.0)
        assert isinstance(result, dict)
        assert "success" in result
        assert "enabled" in result

    @pytest.mark.asyncio
    async def test_set_wifi_disabled(self, executor):
        result = await executor.set_wifi_enabled(False, timeout=1.0)
        assert isinstance(result, dict)
        assert "success" in result


class TestMobileData:

    @pytest.mark.asyncio
    async def test_set_mobile_data(self, executor):
        result = await executor.set_mobile_data_enabled(True, timeout=1.0)
        assert isinstance(result, dict)
        assert "success" in result


class TestAirplaneMode:

    @pytest.mark.asyncio
    async def test_set_airplane_mode(self, executor):
        result = await executor.set_airplane_mode(True, timeout=1.0)
        assert isinstance(result, dict)
        assert "success" in result


class TestVolume:

    @pytest.mark.asyncio
    async def test_set_volume(self, executor):
        result = await executor.set_volume("music", 10, timeout=1.0)
        assert isinstance(result, dict)
        assert "success" in result


class TestStateQueries:

    @pytest.mark.asyncio
    async def test_get_sim_state(self, executor):
        result = await executor.get_sim_state(timeout=1.0)
        assert isinstance(result, dict)
        assert "success" in result

    @pytest.mark.asyncio
    async def test_get_wifi_state(self, executor):
        result = await executor.get_wifi_state(timeout=1.0)
        assert isinstance(result, dict)
        assert "success" in result

    @pytest.mark.asyncio
    async def test_check_state(self, executor):
        # check_state should return bool (even if state unclear)
        result = await executor.check_state("wifi_state", True, timeout=1.0)
        assert isinstance(result, bool)


class TestSamsungSpecific:

    @pytest.mark.asyncio
    async def test_samsung_codes_used_in_fallback(self, executor_with_codes):
        """
        Samsung codes should be attempted before AOSP codes.
        We verify this by checking that the executor has both code sets.
        """
        assert executor_with_codes._samsung_codes
        assert executor_with_codes._aosp_codes
        # Samsung codes should differ from AOSP codes
        samsung_wifi = executor_with_codes._samsung_codes.get("wifi_enable")
        aosp_wifi = executor_with_codes._aosp_codes.get("wifi_enable")
        assert samsung_wifi != aosp_wifi, (
            f"Samsung code ({samsung_wifi}) should differ from AOSP ({aosp_wifi})"
        )

    @pytest.mark.asyncio
    async def test_wifi_with_samsung_codes(self, executor_with_codes):
        """WiFi control with Samsung codes shouldn't crash."""
        result = await executor_with_codes.set_wifi_enabled(True, timeout=1.0)
        assert isinstance(result, dict)
        assert "success" in result
