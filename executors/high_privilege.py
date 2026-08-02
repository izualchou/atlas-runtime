# executors/high_privilege.py
"""
高权限操作执行器（Samsung One UI 8.5 + Termux 适配版）

职责：SIM 切换、WiFi 控制、音量调节等需要系统权限的操作。

三星 One UI 8.5 关键差异：
- service call 事务码与 AOSP 不同（已在 runtime.yaml 中配置）
- 三星 Knox 平台可能限制某些 service call 命令
- 优先使用 svc / settings / cmd 命令，service call 作为回退
- 双 SIM 切换在三星设备上有专属实现路径

回退链（按优先级）：
1. termux-api（如果可用且安装了对应包）
2. svc / settings / cmd（Android 标准命令）
3. service call（三星特定事务码）
4. service call（AOSP 标准事务码）
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Tuple

from .shell_executor import SafeShellExecutor

logger = logging.getLogger("Atlas.HighPrivilege")


class HighPrivilegeExecutor:
    """
    高权限操作执行器。

    在 Samsung One UI 8.5 上测试过的操作：WiFi 开关、移动数据、飞行模式、SIM 切换。
    所有操作都有多层回退机制，确保在 One UI 安全策略限制下尽可能成功。
    """

    def __init__(
        self,
        shell_executor: Optional[SafeShellExecutor] = None,
        samsung_codes: Optional[Dict[str, int]] = None,
    ):
        """
        Args:
            shell_executor: Shell 命令执行器（可选，会自动创建）
            samsung_codes: 三星 service call 事务码配置（从 runtime.yaml 读取）
        """
        self.shell = shell_executor or SafeShellExecutor()
        self._samsung_codes = samsung_codes or {}

        # AOSP 标准事务码（回退用）
        self._aosp_codes = {
            "wifi_enable":   28,
            "wifi_disable":  28,
            "data_enable":   53,
            "data_disable":  53,
            "airplane_on":   59,
            "airplane_off":  59,
            "sim1_enable":   86,
            "sim1_disable":  86,
        }

    # ------------------------------------------------------------------
    # SIM 切换
    # ------------------------------------------------------------------

    async def switch_sim(self, sim_id: int, timeout: float = 5.0) -> Dict[str, Any]:
        """
        切换默认数据 SIM 卡（适用于支持双卡的设备）。

        三星 One UI 8.5 路径（按优先级）：
        1. settings put global multi_sim_data_call {sim_id+1}
        2. service call phone {samsung_code} i32 {sim_id}
        3. service call phone {aosp_code} i32 {sim_id}

        Args:
            sim_id: 0=卡1, 1=卡2
        """
        # 方法 1：settings 路径（最可靠，大多数三星设备支持）
        code = sim_id + 1
        cmd = f"settings put global multi_sim_data_call {code}"
        rc, stdout, stderr = await self.shell.run_command(cmd, timeout)
        if rc == 0:
            logger.info(f"SIM switched to slot {sim_id} via settings")
            return {"success": True, "method": "settings", "stdout": stdout, "stderr": stderr}

        # 方法 2：service call + 三星专用事务码
        samsung_code = self._samsung_codes.get(
            f"sim{sim_id+1}_enable",
            self._samsung_codes.get(f"sim1_{'enable' if sim_id == 0 else 'disable'}"),
        )
        if samsung_code:
            cmd = f"service call phone {samsung_code} i32 {sim_id}"
            rc, stdout, stderr = await self.shell.run_command(cmd, timeout)
            if rc == 0:
                logger.info(f"SIM switched to slot {sim_id} via Samsung service call")
                return {"success": True, "method": "samsung_service_call", "stdout": stdout, "stderr": stderr}

        # 方法 3：service call + AOSP 标准事务码
        aosp_code = self._aosp_codes.get(
            f"sim{sim_id+1}_enable",
            self._aosp_codes.get("sim1_enable"),
        )
        if aosp_code:
            cmd = f"service call phone {aosp_code} i32 {sim_id}"
            rc, stdout, stderr = await self.shell.run_command(cmd, timeout)
            if rc == 0:
                logger.info(f"SIM switched to slot {sim_id} via AOSP service call")
                return {"success": True, "method": "aosp_service_call", "stdout": stdout, "stderr": stderr}

        return {
            "success": False,
            "error": f"No compatible SIM switch method found for sim_id={sim_id}",
            "stderr": stderr,
        }

    # ------------------------------------------------------------------
    # WiFi 控制
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

        # 方法 1：svc wifi
        cmd1 = f"svc wifi {state}"
        rc, stdout, stderr = await self.shell.run_command(cmd1, timeout)
        methods_tried.append("svc")
        if rc == 0:
            return {"success": True, "enabled": enabled, "method": "svc", "stdout": stdout, "stderr": stderr}

        # 方法 2：cmd wifi
        val = "enabled" if enabled else "disabled"
        cmd2 = f"cmd wifi set-wifi-enabled {val}"
        rc, stdout, stderr = await self.shell.run_command(cmd2, timeout)
        methods_tried.append("cmd")
        if rc == 0:
            return {"success": True, "enabled": enabled, "method": "cmd", "stdout": stdout, "stderr": stderr}

        # 方法 3：settings
        val = "1" if enabled else "0"
        cmd3 = f"settings put global wifi_on {val}"
        rc, stdout, stderr = await self.shell.run_command(cmd3, timeout)
        methods_tried.append("settings")
        if rc == 0:
            return {"success": True, "enabled": enabled, "method": "settings", "stdout": stdout, "stderr": stderr}

        # 方法 4：service call（三星专用 + AOSP 回退）
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
    # 移动数据控制
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

        # 方法 1：svc data
        cmd1 = f"svc data {state}"
        rc, stdout, stderr = await self.shell.run_command(cmd1, timeout)
        if rc == 0:
            return {"success": True, "enabled": enabled, "method": "svc", "stdout": stdout, "stderr": stderr}

        # 方法 2：settings
        val = "1" if enabled else "0"
        cmd2 = f"settings put global mobile_data {val}"
        rc, stdout, stderr = await self.shell.run_command(cmd2, timeout)
        if rc == 0:
            return {"success": True, "enabled": enabled, "method": "settings", "stdout": stdout, "stderr": stderr}

        # 方法 3：service call
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
    # 飞行模式
    # ------------------------------------------------------------------

    async def set_airplane_mode(self, enabled: bool, timeout: float = 3.0) -> Dict[str, Any]:
        """
        启用/禁用飞行模式。

        注意：三星 One UI 上飞行模式切换可能触发系统确认对话框，
        这在自动化场景中可能导致命令阻塞。建议仅在已知兼容的设备上使用。
        """
        state = "enable" if enabled else "disable"

        # 方法 1：settings（最可靠，不会触发对话框）
        val = "1" if enabled else "0"
        cmd1 = f"settings put global airplane_mode_on {val}"
        rc, stdout, stderr = await self.shell.run_command(cmd1, timeout)
        if rc == 0:
            # 广播飞行模式变更意图
            broadcast_state = "true" if enabled else "false"
            await self.shell.run_command(
                f"am broadcast -a android.intent.action.AIRPLANE_MODE --ez state {broadcast_state}",
                timeout,
            )
            return {"success": True, "enabled": enabled, "method": "settings", "stdout": stdout, "stderr": stderr}

        # 方法 2：service call
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
    # 音量控制
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
        # 方法 1：media 命令
        cmd1 = f"media volume --stream {stream} --set {level}"
        rc, stdout, stderr = await self.shell.run_command(cmd1, timeout)
        if rc == 0:
            return {"success": True, "stream": stream, "level": level, "method": "media", "stdout": stdout, "stderr": stderr}

        # 方法 2：cmd media
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
    # 状态查询
    # ------------------------------------------------------------------

    async def get_sim_state(self, timeout: float = 3.0) -> Dict[str, Any]:
        """获取当前 SIM 卡状态"""
        cmd = "getprop persist.radio.multisim.config"
        rc, stdout, stderr = await self.shell.run_command(cmd, timeout)

        # 同时查询默认数据 SIM
        cmd2 = "settings get global multi_sim_data_call"
        rc2, stdout2, stderr2 = await self.shell.run_command(cmd2, timeout)

        return {
            "success": rc == 0,
            "multisim_config": stdout.strip() if rc == 0 else None,
            "default_data_sim": stdout2.strip() if rc2 == 0 else None,
            "stdout": stdout,
            "stderr": stderr,
        }

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
