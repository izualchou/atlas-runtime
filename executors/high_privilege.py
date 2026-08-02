# executors/high_privilege.py
"""
高权限操作执行器
职责：SIM 切换、WiFi 控制、音量调节等需要系统权限的操作
优先使用 Android 系统命令 (service call, settings)
"""

import asyncio
import logging
from typing import Dict, Any, Optional

from .shell_executor import SafeShellExecutor

logger = logging.getLogger("Atlas.HighPrivilege")

class HighPrivilegeExecutor:
    def __init__(self, shell_executor: Optional[SafeShellExecutor] = None):
        self.shell = shell_executor or SafeShellExecutor()

    async def switch_sim(self, sim_id: int, timeout: float = 5.0) -> Dict[str, Any]:
        """
        切换默认数据 SIM 卡（适用于支持双卡的设备）。
        sim_id: 0 或 1（取决于设备，0=卡1, 1=卡2）。

        警告：SIM 切换在不同 OEM（小米/华为/三星等）和 Android 版本间
        差异极大，service call 方法并非通用。部署前需在目标设备上验证。
        """
        # 方法 1: service call phone（适用于 AOSP / Pixel / 部分设备）
        cmd = f"service call phone 0 s16 'setPreferredDataSubscription' i32 {sim_id}"
        returncode, stdout, stderr = await self.shell.run_command(cmd, timeout)
        if returncode == 0:
            return {"success": True, "method": "service_call", "stdout": stdout, "stderr": stderr}

        # 方法 2: 通过 settings 切换首选网络（注意：此命令设置的是网络类型而非 SIM 卡，
        # 但在某些 OEM ROM 中可能有副作用，仅作为最后尝试）
        cmd2 = f"settings put global multi_sim_data_call {sim_id + 1}"
        returncode2, stdout2, stderr2 = await self.shell.run_command(cmd2, timeout)
        if returncode2 == 0:
            return {"success": True, "method": "settings_multi_sim", "stdout": stdout2, "stderr": stderr2}

        return {
            "success": False,
            "error": f"No compatible SIM switch method found for sim_id={sim_id}",
            "stderr": stderr2,
        }

    async def set_wifi_enabled(self, enabled: bool, timeout: float = 3.0) -> Dict[str, Any]:
        """启用/禁用 WiFi"""
        state = "enable" if enabled else "disable"
        cmd = f"svc wifi {state}"
        returncode, stdout, stderr = await self.shell.run_command(cmd, timeout)
        return {
            "success": returncode == 0,
            "enabled": enabled,
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
        }

    async def set_volume(self, stream: str, level: int, timeout: float = 2.0) -> Dict[str, Any]:
        """
        设置音量
        stream: 音频流类型，如 'music', 'ring', 'system', 'alarm', 'notification'
        level: 音量等级 (0-15)
        """
        cmd = f"media volume --{stream} {level}"
        returncode, stdout, stderr = await self.shell.run_command(cmd, timeout)
        return {
            "success": returncode == 0,
            "stream": stream,
            "level": level,
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
        }

    async def get_sim_state(self, timeout: float = 3.0) -> Dict[str, Any]:
        """获取当前活跃 SIM 卡状态 (仅获取信息)"""
        # 尝试读取系统属性
        cmd = "getprop persist.radio.multisim.config"
        returncode, stdout, stderr = await self.shell.run_command(cmd, timeout)
        return {
            "success": returncode == 0,
            "multisim_config": stdout.strip() if returncode == 0 else None,
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
        }

    async def check_state(self, resource: str, target: Any, timeout: float = 3.0) -> bool:
        """
        幂等性检查：查询当前硬件状态是否等于目标值
        用于快照恢复时判断操作是否已执行
        """
        if resource == "sim_state":
            # 简单示例：查询当前 SIM 状态（需要更精确）
            result = await self.get_sim_state(timeout)
            return result.get("success") and result.get("multisim_config") == str(target)
        # 其他资源可扩展
        return False