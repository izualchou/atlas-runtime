# tests/test_high_privilege.py
"""
HighPrivilegeExecutor 测试套件（Shizuku/Rish SIM 切换 + WiFi/Data/Airplane/Volume）

SIM 测试策略：
- 所有 SIM 切换测试通过注入 mock ShizukuSimManager 进行，
  不依赖真实 Rish 环境。
- WiFi/Data/Airplane/Volume 测试通过 mock SafeShellExecutor.run_command 进行。
"""

import asyncio
import os
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from executors.high_privilege import (
    AutoJS6SimSwitcher,
    HighPrivilegeExecutor,
    ShizukuSimManager,
    SimInfo,
    SimStatus,
    SimSwitchResult,
)
from executors.shell_executor import SafeShellExecutor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _fake_rish_path():
    """返回一个模拟的 Rish 路径"""
    return os.path.expanduser("~/.atlas_sentinel/bin/rish")


def _make_sim_info(
    sub_id: int, slot: int, display: str = "", carrier: str = ""
) -> SimInfo:
    return SimInfo(
        sub_id=sub_id,
        slot_index=slot,
        display_name=display,
        carrier_name=carrier,
    )


def _make_primary(sub_id: int = 1) -> SimInfo:
    return _make_sim_info(sub_id, 0, "Vodafone", "vodafone IT")


def _make_secondary(sub_id: int = 2) -> SimInfo:
    return _make_sim_info(sub_id, 1, "TIM", "Telecom Italia")


def _make_status(active_sub: int, primary: SimInfo, secondary: SimInfo) -> SimStatus:
    return SimStatus(
        primary=primary,
        secondary=secondary,
        active_data_sub_id=active_sub,
        active_is_primary=(active_sub == primary.sub_id),
    )


def _make_switch_result(success: bool, **kwargs) -> SimSwitchResult:
    defaults = {
        "method": "rish_preset",
        "target_label": "主卡",
        "transaction_code": 31,
        "active_data_sub_id": 1,
        "verified": True,
    }
    defaults.update(kwargs)
    return SimSwitchResult(success=success, **defaults)


# ---------------------------------------------------------------------------
# ShizukuSimManager 单元测试
# ---------------------------------------------------------------------------


class TestShizukuSimManagerParsing:
    """dumpsys isub 解析逻辑测试"""

    DUMP_PRIMARY_ACTIVE = """
Current state
=============
SubscriptionManager
  activeDataSubId=1
  defaultDataSubId=1

SubscriptionInfo:
  id=1 mcc=222 mnc=10 simSlotIndex=0 displayName=Vodafone carrierName=vodafone IT
  dataRoaming=0
  isEmbedded=0
  nativeAccessRules=null

SubscriptionInfo:
  id=2 mcc=222 mnc=01 simSlotIndex=1 displayName=TIM carrierName=Telecom Italia
  dataRoaming=0
  isEmbedded=0
  nativeAccessRules=null
"""

    DUMP_SECONDARY_ACTIVE = """
Current state
=============
SubscriptionManager
  activeDataSubId=2
  defaultDataSubId=1

SubscriptionInfo:
  id=1 mcc=222 mnc=10 simSlotIndex=0 displayName=Vodafone carrierName=vodafone IT
  dataRoaming=0

SubscriptionInfo:
  id=2 mcc=222 mnc=01 simSlotIndex=1 displayName=TIM carrierName=Telecom Italia
  dataRoaming=0
"""

    DUMP_SINGLE_SIM = """
Current state
=============
SubscriptionManager
  activeDataSubId=1
  defaultDataSubId=1

SubscriptionInfo:
  id=1 mcc=222 mnc=10 simSlotIndex=0 displayName=Vodafone carrierName=vodafone IT
  dataRoaming=0
"""

    DUMP_ESIM = """
Current state
=============
SubscriptionManager
  activeDataSubId=2
  defaultDataSubId=2

SubscriptionInfo:
  id=1 mcc=222 mnc=10 simSlotIndex=0 displayName=Vodafone carrierName=vodafone IT
  dataRoaming=0

SubscriptionInfo:
  id=2 simSlotIndex=-1 displayName=eSIM carrierName=T-Mobile
  dataRoaming=0
  isEmbedded=1
"""

    def _make_manager(self, primary_keyword="Vodafone"):
        """创建 ShizukuSimManager（不验证 Rish 路径）"""
        mgr = ShizukuSimManager(
            rish_path="/fake/rish",
            primary_keyword=primary_keyword,
            preset_tx_code=31,
        )
        # 绕过 _ensure_rish 校验
        mgr._rish = "/fake/rish"
        with patch.object(mgr, "_ensure_rish", return_value=None):
            pass
        return mgr

    def test_parse_primary_active(self):
        """主卡激活状态解析"""
        mgr = self._make_manager()
        status = mgr._parse_dump(self.DUMP_PRIMARY_ACTIVE)

        assert status.active_data_sub_id == 1
        assert status.active_is_primary is True
        assert status.primary is not None
        assert status.primary.sub_id == 1
        assert status.primary.slot_index == 0
        assert "Vodafone" in status.primary.name

    def test_parse_secondary_active(self):
        """副卡激活状态解析"""
        mgr = self._make_manager()
        status = mgr._parse_dump(self.DUMP_SECONDARY_ACTIVE)

        assert status.active_data_sub_id == 2
        assert status.active_is_primary is False
        assert status.secondary is not None
        assert status.secondary.sub_id == 2
        assert "TIM" in status.secondary.name

    def test_parse_single_sim(self):
        """单卡设备：无副卡"""
        mgr = self._make_manager()
        status = mgr._parse_dump(self.DUMP_SINGLE_SIM)

        assert status.primary is not None
        assert status.secondary is None
        assert status.active_is_primary is True

    def test_parse_esim_filtered(self):
        """eSIM (simSlotIndex=-1) 被正确过滤，即使关键字匹配也不计入"""
        mgr = self._make_manager("T-Mobile")
        status = mgr._parse_dump(self.DUMP_ESIM)

        # eSIM (id=2, simSlotIndex=-1) 被过滤 → T-Mobile 不出现
        # Vodafone (id=1, simSlotIndex=0) → 不匹配 primary_keyword "T-Mobile" → 列为副卡
        assert status.primary is None  # eSIM 被过滤，物理卡不匹配关键字
        assert status.secondary is not None
        assert "Vodafone" in status.secondary.name
        assert status.active_data_sub_id == 2  # dump 中 activeDataSubId=2（即使对应被过滤的 eSIM）
        assert status.active_is_primary is False

    def test_extract_active_sub_id(self):
        """activeDataSubId 提取"""
        assert ShizukuSimManager._extract_active_sub_id("activeDataSubId=3\n") == 3
        assert ShizukuSimManager._extract_active_sub_id("no match") == -1

    def test_keyword_case_insensitive(self):
        """关键字匹配不区分大小写"""
        mgr = self._make_manager("vodafone")  # 小写
        status = mgr._parse_dump(self.DUMP_PRIMARY_ACTIVE)
        assert status.primary is not None
        assert "Vodafone" in status.primary.name  # 原样保留大写


# ---------------------------------------------------------------------------
# ShizukuSimManager 切换逻辑测试（模拟 Shell Executor）
# ---------------------------------------------------------------------------


class TestShizukuSimManagerSwitching:
    """SIM 切换端到端逻辑测试"""

    @pytest.fixture
    def mock_shell(self):
        """创建 mock SafeShellExecutor"""
        shell = MagicMock(spec=SafeShellExecutor)
        shell.run_command = AsyncMock()
        return shell

    @pytest.fixture
    def manager(self, mock_shell):
        """创建带 mock shell 的 ShizukuSimManager"""
        mgr = ShizukuSimManager(
            rish_path="/fake/rish",
            primary_keyword="Vodafone",
            preset_tx_code=31,
            shell_executor=mock_shell,
        )
        # 直接替换 _ensure_rish 为空操作（绕过磁盘上的文件校验）
        mgr._ensure_rish = lambda: None
        return mgr

    def _dump_response(self, active_sub_id: int = 2) -> str:
        """生成模拟 dumpsys isub 输出（副卡激活）"""
        return (
            "Current state\n"
            "=============\n"
            "SubscriptionManager\n"
            f"  activeDataSubId={active_sub_id}\n"
            "SubscriptionInfo:\n"
            "  id=1 mcc=222 mnc=10 simSlotIndex=0 displayName=Vodafone carrierName=vodafone IT\n"
            "SubscriptionInfo:\n"
            "  id=2 mcc=222 mnc=01 simSlotIndex=1 displayName=TIM carrierName=Telecom Italia\n"
        )

    @pytest.mark.asyncio
    async def test_switch_to_primary_success(self, manager, mock_shell):
        """切换到主卡成功"""
        # dumpsys 返回当前副卡激活，准备切换到主卡
        call_count = 0

        async def side_effect(cmd, timeout):
            nonlocal call_count
            call_count += 1
            if "dumpsys isub" in cmd:
                # 第一次 dumpsys → 副卡激活 (get_status)
                # 第二次 dumpsys → 切换后获取 active sub (校验)
                if call_count == 1:
                    return (0, self._dump_response(2), "")
                elif call_count >= 3:
                    return (0, self._dump_response(1), "")
            # service call → 成功
            return (0, "", "")

        mock_shell.run_command.side_effect = side_effect

        result = await manager.switch_to_primary(timeout=2.0)

        assert result.success is True
        assert result.method == "rish_preset"
        assert result.target_label == "主卡"
        assert result.verified is True

    @pytest.mark.asyncio
    async def test_switch_already_active(self, manager, mock_shell):
        """数据已在目标卡上，无需切换"""
        mock_shell.run_command.return_value = (0, self._dump_response(1), "")

        result = await manager.switch_to_primary(timeout=2.0)

        assert result.success is True
        assert result.method == "already_active"

    @pytest.mark.asyncio
    async def test_switch_heal_scan(self, manager, mock_shell):
        """预设事务码失败，自愈扫描成功"""
        call_count = 0

        async def side_effect(cmd, timeout):
            nonlocal call_count
            call_count += 1

            if "dumpsys isub" in cmd:
                if call_count <= 2:
                    return (0, self._dump_response(2), "")
                # 自愈扫描过程中的校验 → 前几次返回副卡（失败），
                # 第 N 次返回主卡（成功）。N = 35 - 31 + 1 = 5
                # 实际：call 1=dumpsys, call 2=service call 31, call 3=dumpsys (check fail)
                # call 4=service call 32, call 5=dumpsys (check fail=2)
                # ...
                # 当 code=37 时: call N=service call 37, call N+1=dumpsys (check: 1)
                # 所以我们让第 7 次 dumpsys 返回 active=1
                # call 1, 3, 5, 7, 9, 11, 13, 15 → dumpsys (8次)
                # call count = 1 (get_status dumpsys) + (code-31+1)*2 pairs
                # 当 code=37: 1 + (37-31+1)*2 = 1 + 14 = 15
                # 所以 call 15 返回 1
                if call_count >= 15:
                    return (0, self._dump_response(1), "")
            return (0, "", "")

        mock_shell.run_command.side_effect = side_effect

        result = await manager.switch_to_primary(timeout=10.0)

        assert result.success is True
        assert result.method == "rish_scan"
        # scan_range 是 20-50，找到的事务码应在扫描范围内（不一定 > 31）
        assert 20 <= result.transaction_code <= 50
        assert result.verified is True

    @pytest.mark.asyncio
    async def test_switch_no_primary_found(self, manager, mock_shell):
        """未找到匹配 primary_keyword 的 SIM 卡"""
        dump = (
            "SubscriptionManager\n"
            "  activeDataSubId=1\n"
            "SubscriptionInfo:\n"
            "  id=1 simSlotIndex=0 displayName=TIM carrierName=Telecom Italia\n"
        )
        mock_shell.run_command.return_value = (0, dump, "")

        result = await manager.switch_to_primary(timeout=2.0)

        assert result.success is False
        assert "未检测到匹配关键字" in result.error

    @pytest.mark.asyncio
    async def test_toggle_primary_to_secondary(self, manager, mock_shell):
        """toggle：当前主卡激活 → 切换到副卡"""
        call_count = 0

        async def side_effect(cmd, timeout):
            nonlocal call_count
            call_count += 1
            if "dumpsys isub" in cmd:
                if call_count == 1:
                    return (0, self._dump_response(1), "")  # 主卡激活
                if call_count >= 3:
                    return (0, self._dump_response(2), "")  # 副卡激活（校验）
            return (0, "", "")

        mock_shell.run_command.side_effect = side_effect

        result = await manager.toggle(timeout=2.0)

        assert result.success is True
        assert result.target_label == "副卡"

    @pytest.mark.asyncio
    async def test_rish_path_validation(self):
        """Rish 路径校验失败"""
        mgr = ShizukuSimManager(
            rish_path="/nonexistent/rish",
            primary_keyword="Vodafone",
        )
        with pytest.raises(FileNotFoundError, match="Rish 执行文件不可用"):
            mgr._ensure_rish()


# ---------------------------------------------------------------------------
# AutoJS6SimSwitcher 抽象接口测试
# ---------------------------------------------------------------------------


class TestAutoJS6SimSwitcher:
    """验证抽象接口定义正确"""

    def test_abstract_methods_exist(self):
        """抽象方法已定义"""
        assert hasattr(AutoJS6SimSwitcher, "switch_to_primary")
        assert hasattr(AutoJS6SimSwitcher, "switch_to_secondary")
        assert hasattr(AutoJS6SimSwitcher, "get_status")

    def test_cannot_instantiate(self):
        """不能直接实例化抽象类"""
        with pytest.raises(TypeError):
            AutoJS6SimSwitcher()


# ---------------------------------------------------------------------------
# HighPrivilegeExecutor SIM API 测试
# ---------------------------------------------------------------------------


class TestHighPrivilegeSimAPI:
    """
    测试 HighPrivilegeExecutor 的 SIM 相关方法。

    通过注入 mock ShizukuSimManager 避免真实 Rish 调用。
    """

    @pytest.fixture
    def mock_sim(self):
        """创建 mock ShizukuSimManager"""
        sim = MagicMock(spec=ShizukuSimManager)
        sim.switch_to_primary = AsyncMock()
        sim.switch_to_secondary = AsyncMock()
        sim.toggle = AsyncMock()
        sim.switch_sim_by_id = AsyncMock()
        sim.get_status = AsyncMock()
        return sim

    @pytest.fixture
    def executor(self, mock_sim):
        return HighPrivilegeExecutor(sim_manager=mock_sim)

    @pytest.mark.asyncio
    async def test_switch_sim_primary(self, executor, mock_sim):
        mock_sim.switch_to_primary.return_value = _make_switch_result(True)

        result = await executor.switch_sim_primary()

        assert result["success"] is True
        assert result["method"] == "rish_preset"
        mock_sim.switch_to_primary.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_switch_sim_secondary(self, executor, mock_sim):
        mock_sim.switch_to_secondary.return_value = _make_switch_result(
            True, target_label="副卡", active_data_sub_id=2
        )

        result = await executor.switch_sim_secondary()

        assert result["success"] is True
        assert result["target_label"] == "副卡"

    @pytest.mark.asyncio
    async def test_toggle_sim(self, executor, mock_sim):
        mock_sim.toggle.return_value = _make_switch_result(True, method="rish_scan")

        result = await executor.toggle_sim()

        assert result["success"] is True
        assert result["method"] == "rish_scan"

    @pytest.mark.asyncio
    async def test_get_sim_status(self, executor, mock_sim):
        mock_sim.get_status.return_value = _make_status(
            2, _make_primary(1), _make_secondary(2)
        )

        result = await executor.get_sim_status()

        assert result["success"] is True
        assert result["primary_name"] == "Vodafone"
        assert result["active_data_sub_id"] == 2
        assert result["active_is_primary"] is False

    @pytest.mark.asyncio
    async def test_get_sim_state_backward_compat(self, executor, mock_sim):
        """向后兼容：get_sim_state() 委托给 get_sim_status()"""
        mock_sim.get_status.return_value = _make_status(
            1, _make_primary(1), _make_secondary(2)
        )

        result = await executor.get_sim_state()

        assert result["success"] is True
        assert result["multisim_config"] == "1"
        assert result["default_data_sim"] == "1"

    @pytest.mark.asyncio
    async def test_switch_sim_backward_compat(self, executor, mock_sim):
        """向后兼容：switch_sim(sim_id) 委托给 switch_sim_by_id()"""
        mock_sim.switch_sim_by_id.return_value = _make_switch_result(True)

        result = await executor.switch_sim(0)

        assert result["success"] is True
        mock_sim.switch_sim_by_id.assert_awaited_once_with(0, 8.0)

    @pytest.mark.asyncio
    async def test_switch_sim_failure(self, executor, mock_sim):
        """切换失败时返回错误信息"""
        mock_sim.switch_sim_by_id.return_value = _make_switch_result(
            False, error="SIM not found", verified=False
        )

        result = await executor.switch_sim(1)

        assert result["success"] is False
        assert result["error"] == "SIM not found"


# ---------------------------------------------------------------------------
# HighPrivilegeExecutor WiFi/Data/Airplane/Volume 测试
# ---------------------------------------------------------------------------


class TestHighPrivilegeWiFi:
    """WiFi 控制测试"""

    @pytest.fixture
    def mock_shell(self):
        shell = MagicMock(spec=SafeShellExecutor)
        shell.run_command = AsyncMock()
        return shell

    @pytest.fixture
    def executor(self, mock_shell):
        return HighPrivilegeExecutor(shell_executor=mock_shell)

    @pytest.mark.asyncio
    async def test_wifi_enable_svc(self, executor, mock_shell):
        mock_shell.run_command.return_value = (0, "ok", "")
        result = await executor.set_wifi_enabled(True)
        assert result["success"] is True
        assert "svc" in mock_shell.run_command.call_args_list[0].args[0]

    @pytest.mark.asyncio
    async def test_wifi_disable_cmd_fallback(self, executor, mock_shell):
        mock_shell.run_command.side_effect = [
            (1, "", "permission denied"),
            (0, "ok", ""),
        ]
        result = await executor.set_wifi_enabled(False)
        assert result["success"] is True
        assert result["method"] == "cmd"


class TestHighPrivilegeMobileData:
    """移动数据控制测试"""

    @pytest.fixture
    def mock_shell(self):
        shell = MagicMock(spec=SafeShellExecutor)
        shell.run_command = AsyncMock()
        return shell

    @pytest.fixture
    def executor(self, mock_shell):
        return HighPrivilegeExecutor(shell_executor=mock_shell)

    @pytest.mark.asyncio
    async def test_data_enable_svc(self, executor, mock_shell):
        mock_shell.run_command.return_value = (0, "ok", "")
        result = await executor.set_mobile_data_enabled(True)
        assert result["success"] is True
        assert result["method"] == "svc"

    @pytest.mark.asyncio
    async def test_data_disable_settings_fallback(self, executor, mock_shell):
        mock_shell.run_command.side_effect = [
            (1, "", "not found"),
            (0, "", ""),
        ]
        result = await executor.set_mobile_data_enabled(False)
        assert result["success"] is True
        assert result["method"] == "settings"


class TestHighPrivilegeAirplane:
    """飞行模式控制测试"""

    @pytest.fixture
    def mock_shell(self):
        shell = MagicMock(spec=SafeShellExecutor)
        shell.run_command = AsyncMock()
        return shell

    @pytest.fixture
    def executor(self, mock_shell):
        return HighPrivilegeExecutor(shell_executor=mock_shell)

    @pytest.mark.asyncio
    async def test_airplane_enable(self, executor, mock_shell):
        mock_shell.run_command.return_value = (0, "ok", "")
        result = await executor.set_airplane_mode(True)
        assert result["success"] is True
        assert result["method"] == "settings"


class TestHighPrivilegeVolume:
    """音量控制测试"""

    @pytest.fixture
    def mock_shell(self):
        shell = MagicMock(spec=SafeShellExecutor)
        shell.run_command = AsyncMock()
        return shell

    @pytest.fixture
    def executor(self, mock_shell):
        return HighPrivilegeExecutor(shell_executor=mock_shell)

    @pytest.mark.asyncio
    async def test_volume_music(self, executor, mock_shell):
        mock_shell.run_command.return_value = (0, "ok", "")
        result = await executor.set_volume("music", 7)
        assert result["success"] is True
        assert result["stream"] == "music"
        assert result["level"] == 7


class TestHighPrivilegeCheckState:
    """check_state 幂等性检查测试"""

    @pytest.fixture
    def mock_shell(self):
        shell = MagicMock(spec=SafeShellExecutor)
        shell.run_command = AsyncMock()
        return shell

    @pytest.fixture
    def executor(self, mock_shell):
        mock_sim = MagicMock(spec=ShizukuSimManager)
        mock_sim.get_status = AsyncMock(return_value=_make_status(
            1, _make_primary(1), _make_secondary(2)
        ))
        return HighPrivilegeExecutor(
            shell_executor=mock_shell,
            sim_manager=mock_sim,
        )

    @pytest.mark.asyncio
    async def test_check_wifi_state(self, executor, mock_shell):
        mock_shell.run_command.return_value = (0, "1\n", "")
        assert await executor.check_state("wifi_state", True) is True

    @pytest.mark.asyncio
    async def test_check_mobile_data(self, executor, mock_shell):
        mock_shell.run_command.return_value = (0, "1\n", "")
        assert await executor.check_state("mobile_data", True) is True

    @pytest.mark.asyncio
    async def test_check_sim_state(self, executor):
        # check_state("sim_state", 1) → multisim_config == "1"
        assert await executor.check_state("sim_state", 1) is True


# ---------------------------------------------------------------------------
# SimInfo / SimStatus / SimSwitchResult 数据结构测试
# ---------------------------------------------------------------------------


class TestDataStructures:
    def test_sim_info_name_fallback(self):
        """无 displayName 和 carrierName 时使用默认名称"""
        info = SimInfo(sub_id=5, slot_index=0)
        assert "SIM-5" in info.name

    def test_sim_info_name_prefers_display(self):
        """displayName 优先于 carrierName"""
        info = SimInfo(sub_id=1, slot_index=0, display_name="MyLine", carrier_name="Vodafone")
        assert info.name == "MyLine"

    def test_sim_status_active_label(self):
        """active_label 格式化正确"""
        status = _make_status(1, _make_primary(1), _make_secondary(2))
        assert "主卡" in status.active_label
        assert "Vodafone" in status.active_label

    def test_sim_status_active_label_secondary(self):
        status = _make_status(2, _make_primary(1), _make_secondary(2))
        assert "副卡" in status.active_label

    def test_sim_switch_result_defaults(self):
        result = SimSwitchResult(success=False, error="no sim")
        assert result.success is False
        assert result.method == ""
