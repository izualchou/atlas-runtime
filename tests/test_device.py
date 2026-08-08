"""
Unit tests for device/ — platform detection and health checking.

Tests cover the v9.0 device layer: detector (PlatformInfo) and health (HealthChecker).
"""

import pytest

from device import PlatformInfo, HealthChecker
from device.detector import TERMUX_PREFIX, TERMUX_HOME, TERMUX_TMP


# ---------------------------------------------------------------------------
# Termux path constants
# ---------------------------------------------------------------------------

class TestTermuxPaths:
    def test_termux_prefix_defined(self):
        assert TERMUX_PREFIX is not None
        assert isinstance(TERMUX_PREFIX, str)

    def test_termux_tmp_is_subpath(self):
        assert TERMUX_TMP.startswith(TERMUX_PREFIX)

    def test_termux_home_defined(self):
        assert isinstance(TERMUX_HOME, str)


# ---------------------------------------------------------------------------
# PlatformInfo
# ---------------------------------------------------------------------------

class TestPlatformInfo:
    def test_default_values(self):
        pi = PlatformInfo()
        assert pi.manufacturer == "unknown"
        assert pi.model == "unknown"
        assert pi.android_version == "unknown"
        assert pi.android_sdk == 0

    def test_custom_values(self):
        pi = PlatformInfo(manufacturer="samsung", model="SM-G9980")
        assert pi.manufacturer == "samsung"
        assert pi.model == "SM-G9980"

    def test_default_capability_flags(self):
        pi = PlatformInfo()
        assert pi.is_samsung is False
        assert pi.is_one_ui is False
        assert pi.has_dual_sim is False
        assert pi.has_root is False

    def test_field_access(self):
        pi = PlatformInfo(
            manufacturer="samsung",
            is_samsung=True,
            is_one_ui=True,
            one_ui_version="8.5",
            one_ui_major=8,
        )
        assert pi.is_samsung is True
        assert pi.one_ui_major == 8
        assert pi.one_ui_version == "8.5"


# ---------------------------------------------------------------------------
# HealthChecker
# ---------------------------------------------------------------------------

class TestHealthChecker:
    def test_constructor(self):
        pi = PlatformInfo()
        hc = HealthChecker(platform=pi)
        assert hc._platform is pi
        assert hc._running is False

    def test_constructor_custom_interval(self):
        pi = PlatformInfo()
        hc = HealthChecker(platform=pi, check_interval_seconds=15.0)
        assert hc._interval == 15.0

    @pytest.mark.asyncio
    async def test_get_status_initially_none(self):
        pi = PlatformInfo()
        hc = HealthChecker(platform=pi)
        status = await hc.get_status()
        assert status is None

    def test_subscribe_and_unsubscribe(self):
        pi = PlatformInfo()
        hc = HealthChecker(platform=pi)
        called = []

        def callback(health):
            called.append(health)

        hc.subscribe(callback)
        hc.unsubscribe(callback)
        assert len(hc._subscribers) == 0

    def test_is_healthy_defaults_true(self):
        pi = PlatformInfo()
        hc = HealthChecker(platform=pi)
        assert hc.is_healthy is True
