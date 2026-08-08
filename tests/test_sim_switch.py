"""
Unit tests for executors/sim_switch.py — SIM switching executor.

Tests cover ShizukuSimManager initialization, result types, and AutoJS6SimSwitcher stub.
"""

import pytest

from executors.sim_switch import ShizukuSimManager, AutoJS6SimSwitcher
from models import SimSwitchResult, SimInfo


# ---------------------------------------------------------------------------
# AutoJS6SimSwitcher (ABC stub)
# ---------------------------------------------------------------------------

class TestAutoJS6SimSwitcher:
    def test_is_abstract(self):
        """ABC 抽象基类不可直接实例化。"""
        with pytest.raises(TypeError):
            AutoJS6SimSwitcher()

    def test_subclass_must_implement_all(self):
        """子类缺少抽象方法时，实例化才触发 TypeError（类定义时不会）。"""

        class Partial(AutoJS6SimSwitcher):
            async def switch_to_primary(self, timeout=15.0):
                return SimSwitchResult(success=True)

        with pytest.raises(TypeError):
            Partial()  # 缺少 switch_to_secondary 和 get_status，不可实例化

    def test_subclass_can_extend(self):
        """子类实现全部抽象方法后可以实例化。"""

        class FutureAutoJS6Switcher(AutoJS6SimSwitcher):
            async def switch_to_primary(self, timeout=15.0):
                return SimSwitchResult(success=True)

            async def switch_to_secondary(self, timeout=15.0):
                return SimSwitchResult(success=True)

            async def get_status(self, timeout=10.0):
                from models import SimStatus
                return SimStatus()

        switcher = FutureAutoJS6Switcher()
        assert isinstance(switcher, AutoJS6SimSwitcher)


# ---------------------------------------------------------------------------
# SimSwitchResult
# ---------------------------------------------------------------------------

class TestSimSwitchResult:
    def test_success_result(self):
        r = SimSwitchResult(success=True)
        assert r.success is True

    def test_failure_with_error(self):
        r = SimSwitchResult(success=False, error="Shizuku not running")
        assert r.success is False
        assert r.error == "Shizuku not running"

    def test_result_with_data_and_method(self):
        r = SimSwitchResult(
            success=True,
            method="rish_preset",
            target_label="主卡",
            transaction_code=31,
            active_data_sub_id=1,
            verified=True,
        )
        assert r.success is True
        assert r.method == "rish_preset"
        assert r.target_label == "主卡"


# ---------------------------------------------------------------------------
# ShizukuSimManager
# ---------------------------------------------------------------------------

class TestShizukuSimManager:
    def test_instantiation(self):
        """构造 ShizukuSimManager 不抛异常。"""
        manager = ShizukuSimManager()
        assert manager is not None
        assert hasattr(manager, "switch_to_primary")
        assert hasattr(manager, "switch_to_secondary")
        assert hasattr(manager, "get_status")
        assert hasattr(manager, "toggle")

    def test_default_rish_path(self):
        manager = ShizukuSimManager()
        assert "rish" in str(manager._rish)

    def test_custom_primary_keyword(self):
        manager = ShizukuSimManager(primary_keyword="CMCC")
        assert manager._primary_keyword == "CMCC"

    def test_custom_tx_code(self):
        manager = ShizukuSimManager(preset_tx_code=25)
        assert manager._preset_tx_code == 25

    def test_scan_range_defaults(self):
        manager = ShizukuSimManager()
        assert manager._scan_low == 20
        assert manager._scan_high == 50

    def test_custom_scan_range(self):
        manager = ShizukuSimManager(scan_range=(10, 60))
        assert manager._scan_low == 10
        assert manager._scan_high == 60
