# executors/high_privilege.py
"""
高权限操作执行器（Samsung One UI 8.5 + Termux 适配版）

职责：WiFi 控制、移动数据、飞行模式、音量调节等需要系统权限的操作。

SIM 切换逻辑已拆分至 executors/sim_switch.py（v9.0 架构优化），
HighPrivilegeExecutor 通过委托调用 ShizukuSimManager 完成 SIM 操作。

三星 One UI 8.5 关键差异：
- service call 事务码与 AOSP 不同（已在 runtime.yaml 中配置）
- 三星 Knox 平台可能限制某些 service call 命令
- 优先使用 svc / settings / cmd 命令，service call 作为回退
- 双 SIM 切换走 Shizuku/Rish 独占路径
"""

import logging
from typing import Dict, Any, Optional

from models.sim import SimSwitchResult
from .shell_executor import SafeShellExecutor
from .sim_switch import ShizukuSimManager, AutoJS6SimSwitcher  # noqa: F401 — re-export

logger = logging.getLogger("Atlas.HighPrivilege")


# ---------------------------------------------------------------------------
# HighPrivilegeExecutor — 对外统一接口
# ---------------------------------------------------------------------------


class HighPrivilegeExecutor:
    """
    高权限操作执行器。

    SIM 切换委托给 ShizukuSimManager（Rish 方案），不再走 settings/service call phone 回退。
    WiFi / 移动数据 / 飞行模式 / 音量保持原有的多层回退机制。
    """

    def __init__(
        self,
        shell_executor: Optional[SafeShellExecutor] = None,
        samsung_codes: Optional[Dict[str, int]] = None,
        sim_manager: Optional[ShizukuSimManager] = None,
    ):
        """
        Args:
            shell_executor: Shell 命令执行器（可选，会自动创建）
            samsung_codes:   三星 service call 事务码配置（WiFi/Data/Airplane 用）
            sim_manager:     ShizukuSimManager 实例（可选，自动创建默认配置）
        """
        self.shell = shell_executor or SafeShellExecutor()
        self._samsung_codes = samsung_codes or {}
        self._sim = sim_manager or ShizukuSimManager(shell_executor=self.shell)

        # AOSP 标准事务码（回退用 — 仅 WiFi/数据/飞行模式）
        self._aosp_codes = {
            "wifi_enable":   28,
            "wifi_disable":  28,
            "data_enable":   53,
            "data_disable":  53,
            "airplane_on":   59,
            "airplane_off":  59,
        }

    # ------------------------------------------------------------------
    # SIM 切换（v9.1 — 仅 Shizuku/Rish 方案）
    # ------------------------------------------------------------------

    async def switch_sim(self, sim_id: int, timeout: float = 8.0) -> Dict[str, Any]:
        """
        切换默认数据 SIM 卡（兼容旧 API，委托给 ShizukuSimManager）。

        Args:
            sim_id: 0=主卡, 1=副卡（按 primary_keyword 匹配）
        """
        result = await self._sim.switch_sim_by_id(sim_id, timeout)
        return {
            "success": result.success,
            "method": result.method,
            "target_label": result.target_label,
            "transaction_code": result.transaction_code,
            "verified": result.verified,
            "error": result.error if not result.success else "",
        }

    async def switch_sim_primary(self, timeout: float = 8.0) -> Dict[str, Any]:
        """切换到主卡（primary_keyword 匹配的卡）"""
        result = await self._sim.switch_to_primary(timeout)
        return self._format_result(result)

    async def switch_sim_secondary(self, timeout: float = 8.0) -> Dict[str, Any]:
        """切换到副卡"""
        result = await self._sim.switch_to_secondary(timeout)
        return self._format_result(result)

    async def toggle_sim(self, timeout: float = 8.0) -> Dict[str, Any]:
        """在主卡和副卡之间切换数据"""
        result = await self._sim.toggle(timeout)
        return self._format_result(result)

    async def get_sim_status(self, timeout: float = 5.0) -> Dict[str, Any]:
        """
        获取双卡数据状态详情。

        返回：
            primary_name, primary_sub_id, secondary_name, secondary_sub_id,
            active_data_sub_id, active_label, active_is_primary
        """
        status = await self._sim.get_status(timeout)
        return {
            "success": True,
            "primary_name": status.primary.name if status.primary else "",
            "primary_sub_id": status.primary.sub_id if status.primary else -1,
            "secondary_name": status.secondary.name if status.secondary else "",
            "secondary_sub_id": status.secondary.sub_id if status.secondary else -1,
            "active_data_sub_id": status.active_data_sub_id,
            "active_label": status.active_label,
            "active_is_primary": status.active_is_primary,
        }

    async def get_sim_state(self, timeout: float = 5.0) -> Dict[str, Any]:
        """
        获取当前 SIM 卡状态（向后兼容旧 API，委托给 get_sim_status）。

        返回字段与旧版本兼容：
            - success: bool
            - multisim_config: 主卡 SubID
            - default_data_sim: 当前激活的数据 SubID
            - primary_name, secondary_name, active_label: 扩展字段
        """
        info = await self.get_sim_status(timeout)
        return {
            "success": info.get("success", True),
            "multisim_config": str(info.get("primary_sub_id", -1)),
            "default_data_sim": str(info.get("active_data_sub_id", -1)),
            "primary_name": info.get("primary_name", ""),
            "secondary_name": info.get("secondary_name", ""),
            "active_label": info.get("active_label", ""),
        }

    @staticmethod
    def _format_result(result: SimSwitchResult) -> Dict[str, Any]:
        return {
            "success": result.success,
            "method": result.method,
            "target_label": result.target_label,
            "transaction_code": result.transaction_code,
            "active_data_sub_id": result.active_data_sub_id,
            "verified": result.verified,
            "error": result.error if not result.success else "",
        }

    # ------------------------------------------------------------------
    # WiFi 控制（保持原有回退逻辑不变）
    # ------------------------------------------------------------------

    async def set_wifi_enabled(self, enabled: bool, timeout: float = 3.0) -> Dict[str, Any]:
        """
        启用/禁用 WiFi。

        三星 One UI 8.5 路径：
        1. svc wifi enable/disable（最常用）
        2. cmd wifi set-wifi-enabled enabled/disabled
        3. settings put global wifi_on 1/0
        4. service call（三星/AOSP 事务码回退）
        """
        state = "enable" if enabled else "disable"
        methods_tried = []

        cmd1 = f"svc wifi {state}"
        rc, stdout, stderr = await self.shell.run_command(cmd1, timeout)
        methods_tried.append("svc")
        if rc == 0:
            return {"success": True, "enabled": enabled, "method": "svc", "stdout": stdout, "stderr": stderr}

        val = "enabled" if enabled else "disabled"
        cmd2 = f"cmd wifi set-wifi-enabled {val}"
        rc, stdout, stderr = await self.shell.run_command(cmd2, timeout)
        methods_tried.append("cmd")
        if rc == 0:
            return {"success": True, "enabled": enabled, "method": "cmd", "stdout": stdout, "stderr": stderr}

        val = "1" if enabled else "0"
        cmd3 = f"settings put global wifi_on {val}"
        rc, stdout, stderr = await self.shell.run_command(cmd3, timeout)
        methods_tried.append("settings")
        if rc == 0:
            return {"success": True, "enabled": enabled, "method": "settings", "stdout": stdout, "stderr": stderr}

        for method_name, codes in [
            ("samsung_service_call", self._samsung_codes),
            ("aosp_service_call", self._aosp_codes),
        ]:
            code_key = "wifi_enable" if enabled else "wifi_disable"
            code = codes.get(code_key)
            if code:
                cmd4 = f"service call wifi {code}"
                rc, stdout, stderr = await self.shell.run_command(cmd4, timeout)
                methods_tried.append(method_name)
                if rc == 0:
                    return {"success": True, "enabled": enabled, "method": method_name, "stdout": stdout, "stderr": stderr}

        return {
            "success": False,
            "enabled": not enabled,
            "error": f"Failed after trying: {', '.join(methods_tried)}",
            "stderr": stderr,
        }

    # ------------------------------------------------------------------
    # 移动数据控制（保持原有回退逻辑不变）
    # ------------------------------------------------------------------

    async def set_mobile_data_enabled(self, enabled: bool, timeout: float = 3.0) -> Dict[str, Any]:
        """
        启用/禁用移动数据。

        三星 One UI 8.5 路径：
        1. svc data enable/disable
        2. settings put global mobile_data 1/0
        3. service call（三星/AOSP 回退）
        """
        state = "enable" if enabled else "disable"

        cmd1 = f"svc data {state}"
        rc, stdout, stderr = await self.shell.run_command(cmd1, timeout)
        if rc == 0:
            return {"success": True, "enabled": enabled, "method": "svc", "stdout": stdout, "stderr": stderr}

        val = "1" if enabled else "0"
        cmd2 = f"settings put global mobile_data {val}"
        rc, stdout, stderr = await self.shell.run_command(cmd2, timeout)
        if rc == 0:
            return {"success": True, "enabled": enabled, "method": "settings", "stdout": stdout, "stderr": stderr}

        for method_name, codes in [
            ("samsung_service_call", self._samsung_codes),
            ("aosp_service_call", self._aosp_codes),
        ]:
            code_key = "data_enable" if enabled else "data_disable"
            code = codes.get(code_key)
            if code:
                cmd3 = f"service call phone {code}"
                rc, stdout, stderr = await self.shell.run_command(cmd3, timeout)
                if rc == 0:
                    return {"success": True, "enabled": enabled, "method": method_name, "stdout": stdout, "stderr": stderr}

        return {
            "success": False,
            "enabled": not enabled,
            "error": "No compatible mobile data method found",
            "stderr": stderr,
        }

    # ------------------------------------------------------------------
    # 飞行模式（保持原有逻辑不变）
    # ------------------------------------------------------------------

    async def set_airplane_mode(self, enabled: bool, timeout: float = 3.0) -> Dict[str, Any]:
        """
        启用/禁用飞行模式。

        注意：三星 One UI 上飞行模式切换可能触发系统确认对话框，
        这在自动化场景中可能导致命令阻塞。建议仅在已知兼容的设备上使用。
        """
        state = "enable" if enabled else "disable"

        val = "1" if enabled else "0"
        cmd1 = f"settings put global airplane_mode_on {val}"
        rc, stdout, stderr = await self.shell.run_command(cmd1, timeout)
        if rc == 0:
            broadcast_state = "true" if enabled else "false"
            await self.shell.run_command(
                f"am broadcast -a android.intent.action.AIRPLANE_MODE --ez state {broadcast_state}",
                timeout,
            )
            return {"success": True, "enabled": enabled, "method": "settings", "stdout": stdout, "stderr": stderr}

        for method_name, codes in [
            ("samsung_service_call", self._samsung_codes),
            ("aosp_service_call", self._aosp_codes),
        ]:
            code_key = "airplane_on" if enabled else "airplane_off"
            code = codes.get(code_key)
            if code:
                cmd2 = f"service call connectivity {code}"
                rc, stdout, stderr = await self.shell.run_command(cmd2, timeout)
                if rc == 0:
                    return {"success": True, "enabled": enabled, "method": method_name, "stdout": stdout, "stderr": stderr}

        return {
            "success": False,
            "enabled": not enabled,
            "error": "No compatible airplane mode method found",
            "stderr": stderr,
        }

    # ------------------------------------------------------------------
    # 音量控制（保持原有逻辑不变）
    # ------------------------------------------------------------------

    async def set_volume(
        self, stream: str, level: int, timeout: float = 2.0
    ) -> Dict[str, Any]:
        """
        设置音量。

        Args:
            stream: 音频流类型 — 'music', 'ring', 'system', 'alarm', 'notification'
            level: 音量等级 (0-15)

        注意：在 Samsung One UI 上，media 命令可能受限，
        回退到 input keyevent 模拟按键。
        """
        cmd1 = f"media volume --stream {stream} --set {level}"
        rc, stdout, stderr = await self.shell.run_command(cmd1, timeout)
        if rc == 0:
            return {"success": True, "stream": stream, "level": level, "method": "media", "stdout": stdout, "stderr": stderr}

        cmd2 = f"cmd media_session volume --stream {stream} --set {level}"
        rc, stdout, stderr = await self.shell.run_command(cmd2, timeout)
        if rc == 0:
            return {"success": True, "stream": stream, "level": level, "method": "cmd_media", "stdout": stdout, "stderr": stderr}

        return {
            "success": False,
            "stream": stream,
            "error": f"Failed to set volume for stream '{stream}'",
            "stderr": stderr,
        }

    # ------------------------------------------------------------------
    # 状态查询（非 SIM 部分保持原有逻辑）
    # ------------------------------------------------------------------

    async def get_wifi_state(self, timeout: float = 3.0) -> Dict[str, Any]:
        """获取当前 WiFi 状态"""
        cmd = "settings get global wifi_on"
        rc, stdout, stderr = await self.shell.run_command(cmd, timeout)
        return {
            "success": rc == 0,
            "wifi_enabled": stdout.strip() == "1" if rc == 0 else None,
            "stdout": stdout,
            "stderr": stderr,
        }

    async def check_state(
        self, resource: str, target: Any, timeout: float = 3.0
    ) -> bool:
        """
        幂等性检查：查询当前硬件状态是否等于目标值。

        用于快照恢复时判断操作是否已执行。
        """
        if resource == "sim_state":
            result = await self.get_sim_state(timeout)
            return result.get("success") and result.get("multisim_config") == str(target)

        if resource == "wifi_state":
            result = await self.get_wifi_state(timeout)
            return result.get("wifi_enabled") == target

        if resource == "mobile_data":
            cmd = "settings get global mobile_data"
            rc, stdout, _ = await self.shell.run_command(cmd, timeout)
            return rc == 0 and stdout.strip() == ("1" if target else "0")

        return False
