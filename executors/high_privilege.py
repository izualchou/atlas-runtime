# executors/high_privilege.py
"""
高权限操作执行器（Samsung One UI 8.5 + Termux 适配版）

职责：SIM 切换、WiFi 控制、音量调节等需要系统权限的操作。

双卡数据切换方案（v9.1）：
────────────────────────────────────────────────────────────
唯一采用 Shizuku/Rish 方案执行 service call isub 进行切换。
不再使用 settings put global multi_sim_data_call 或 service call phone 回退。

流程：
  1. Rish 执行 dumpsys isub 解析 SubID 与卡槽信息
  2. 关键字匹配识别主卡（如 "Vodafone"）
  3. 使用预设事务码 31 执行切换：service call isub 31 i32 <sub_id>
  4. 失败时自动扫描事务码 20-50 自愈

备用接口：
  AutoJS6SimSwitcher 抽象类已预留，暂不实现具体逻辑。
────────────────────────────────────────────────────────────

三星 One UI 8.5 关键差异：
- service call 事务码与 AOSP 不同（已在 runtime.yaml 中配置）
- 三星 Knox 平台可能限制某些 service call 命令
- 优先使用 svc / settings / cmd 命令，service call 作为回退
- 双 SIM 切换走 Shizuku/Rish 独占路径
"""

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

from .shell_executor import SafeShellExecutor

logger = logging.getLogger("Atlas.HighPrivilege")

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class SimInfo:
    """单张 SIM 卡的信息"""
    sub_id: int
    slot_index: int
    display_name: str = ""
    carrier_name: str = ""

    @property
    def name(self) -> str:
        return self.display_name or self.carrier_name or f"SIM-{self.sub_id}"


@dataclass
class SimStatus:
    """双卡数据状态快照"""
    primary: Optional[SimInfo] = None
    secondary: Optional[SimInfo] = None
    active_data_sub_id: int = -1
    active_is_primary: bool = False
    raw_dump: str = ""

    @property
    def active_label(self) -> str:
        if self.active_is_primary and self.primary:
            return f"[主卡] {self.primary.name}"
        if not self.active_is_primary and self.secondary:
            return f"[副卡] {self.secondary.name}"
        return f"未知 (SubID: {self.active_data_sub_id})"


@dataclass
class SimSwitchResult:
    """SIM 切换操作结果"""
    success: bool
    method: str = ""              # "rish_preset", "rish_scan"
    target_label: str = ""
    transaction_code: int = 0
    active_data_sub_id: int = -1
    verified: bool = False
    error: str = ""


# ---------------------------------------------------------------------------
# AutoJS6 备用接口（预留，暂不实现）
# ---------------------------------------------------------------------------


class AutoJS6SimSwitcher(ABC):
    """
    AutoJS6 无障碍自动点击方案的抽象接口。

    本接口预留用于未来升级场景：
    - 当 Shizuku/Rish 不可用时，回退到 UI 自动化点击
    - 通过 Intent 启动 AutoJS6 脚本 → 打开设置 → 点击切换

    当前状态：接口已定义，但未实现具体逻辑。
    """

    @abstractmethod
    async def switch_to_primary(self, timeout: float = 15.0) -> SimSwitchResult:
        """通过 UI 自动化切换到主卡"""
        ...

    @abstractmethod
    async def switch_to_secondary(self, timeout: float = 15.0) -> SimSwitchResult:
        """通过 UI 自动化切换到副卡"""
        ...

    @abstractmethod
    async def get_status(self, timeout: float = 10.0) -> SimStatus:
        """通过 UI 自动化获取当前状态"""
        ...


# ---------------------------------------------------------------------------
# Shizuku/Rish SIM 管理器 — 唯一切换方案
# ---------------------------------------------------------------------------


class ShizukuSimManager:
    """
    基于 Shizuku/Rish 的双卡数据切换管理器。

    通过 Rish 代理执行 dumpsys isub 和 service call isub，
    实现无须 root 的系统级 SIM 卡数据切换。

    参数：
        rish_path:       Rish 可执行文件路径（默认 ~/.atlas_sentinel/bin/rish）
        primary_keyword: 主卡识别关键字（默认 "Vodafone"）
        preset_tx_code:  预设事务码（默认 31）
        scan_range:      自愈扫描范围（默认 20-50）
        shell_executor:  Shell 执行器
    """

    # 默认路径：与 Shell 脚本中的 $HOME/.atlas_sentinel/bin/rish 一致
    _DEFAULT_RISH_PATH = "~/.atlas_sentinel/bin/rish"

    def __init__(
        self,
        rish_path: str = "",
        primary_keyword: str = "Vodafone",
        preset_tx_code: int = 31,
        scan_range: Tuple[int, int] = (20, 50),
        shell_executor: Optional[SafeShellExecutor] = None,
    ):
        self._rish = str(Path(rish_path or self._DEFAULT_RISH_PATH).expanduser())
        self._primary_keyword = primary_keyword
        self._preset_tx_code = preset_tx_code
        self._scan_low, self._scan_high = scan_range
        self.shell = shell_executor or SafeShellExecutor()

    # ------------------------------------------------------------------
    # 公有 API
    # ------------------------------------------------------------------

    async def get_status(self, timeout: float = 5.0) -> SimStatus:
        """
        获取双卡数据状态。

        通过 Rish 执行 dumpsys isub 获取完整的 SubscriptionInfo，
        解析出主/副卡的 SubID、卡槽、运营商名称，以及当前激活的数据卡。

        返回 SimStatus，即使解析失败也不会抛出异常，
        raw_dump 始终保留原始输出供排查。
        """
        dump = await self._fetch_isub_dump(timeout)
        if not dump:
            return SimStatus(raw_dump="")

        status = self._parse_dump(dump)
        status.raw_dump = dump
        return status

    async def switch_to_primary(self, timeout: float = 8.0) -> SimSwitchResult:
        """切换到主卡（由 primary_keyword 匹配）"""
        status = await self.get_status(timeout=timeout)
        if status.primary is None:
            return SimSwitchResult(
                success=False,
                target_label="主卡",
                error=f"未检测到匹配关键字 '{self._primary_keyword}' 的 SIM 卡",
            )
        return await self._switch_to(status.primary, status, "主卡", timeout)

    async def switch_to_secondary(self, timeout: float = 8.0) -> SimSwitchResult:
        """切换到副卡（非 primary_keyword 匹配的卡）"""
        status = await self.get_status(timeout=timeout)
        if status.secondary is None:
            return SimSwitchResult(
                success=False,
                target_label="副卡",
                error="未检测到副卡，设备可能只有一张 SIM 卡",
            )
        return await self._switch_to(status.secondary, status, "副卡", timeout)

    async def toggle(self, timeout: float = 8.0) -> SimSwitchResult:
        """
        在主卡和副卡之间切换数据。

        如果当前数据在主卡 → 切换到副卡；反之亦然。
        """
        status = await self.get_status(timeout=timeout)
        if status.active_is_primary and status.secondary:
            return await self._switch_to(status.secondary, status, "副卡", timeout)
        elif not status.active_is_primary and status.primary:
            return await self._switch_to(status.primary, status, "主卡", timeout)
        elif status.primary is None:
            return SimSwitchResult(
                success=False,
                target_label="未知",
                error="没有可切换的目标卡",
            )
        else:
            # 当前在未知卡上，尝试切换到主卡
            return await self._switch_to(status.primary, status, "主卡", timeout)

    # ------------------------------------------------------------------
    # 查询接口（向后兼容旧 API）
    # ------------------------------------------------------------------

    async def switch_sim_by_id(
        self, sim_id: int, timeout: float = 8.0
    ) -> SimSwitchResult:
        """
        通过 sim_id（0=卡1, 1=卡2）切换，向后兼容旧的 switch_sim() 接口。

        注意：这是兼容性接口。推荐使用 switch_to_primary/switch_to_secondary。
        """
        status = await self.get_status(timeout=timeout)
        target = None
        label = ""
        if sim_id == 0 and status.primary:
            target = status.primary
            label = "主卡"
        elif sim_id == 1 and status.secondary:
            target = status.secondary
            label = "副卡"
        elif status.primary and status.primary.slot_index == sim_id:
            target = status.primary
            label = "主卡"
        elif status.secondary and status.secondary.slot_index == sim_id:
            target = status.secondary
            label = "副卡"

        if target is None:
            return SimSwitchResult(
                success=False,
                target_label=f"slot {sim_id}",
                error=f"未找到 sim_id={sim_id} 对应的 SIM 卡",
            )
        return await self._switch_to(target, status, label, timeout)

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    async def _fetch_isub_dump(self, timeout: float) -> str:
        """通过 Rish 执行 dumpsys isub 获取原始输出"""
        self._ensure_rish()
        cmd = f"{self._rish} -c \"dumpsys isub\""
        rc, stdout, stderr = await self.shell.run_command(cmd, timeout)
        if rc != 0:
            logger.error(f"dumpsys isub failed (rc={rc}): {stderr[:200]}")
            return ""
        return stdout

    async def _switch_to(
        self,
        target: SimInfo,
        status: SimStatus,
        label: str,
        timeout: float,
    ) -> SimSwitchResult:
        """切换到指定 SIM 卡，带预设事务码 + 自愈扫描"""
        if target.sub_id == status.active_data_sub_id:
            logger.info(f"数据已在 [{label}] {target.name} (SubID: {target.sub_id})，无需切换")
            return SimSwitchResult(
                success=True,
                method="already_active",
                target_label=label,
                active_data_sub_id=target.sub_id,
                verified=True,
            )

        self._ensure_rish()

        # 步骤 1：使用预设事务码 31 尝试切换
        logger.info(
            f"切换数据至 [{label}] {target.name} (SubID: {target.sub_id})，"
            f"使用事务码 {self._preset_tx_code}"
        )
        await self._exec_service_call(target.sub_id, self._preset_tx_code, timeout)
        await asyncio.sleep(1.2)

        # 校验
        new_sub = await self._get_active_sub_id(timeout)
        if new_sub == target.sub_id:
            logger.info(f"切换成功 [{label}] → SubID {target.sub_id}，事务码 {self._preset_tx_code}")
            return SimSwitchResult(
                success=True,
                method="rish_preset",
                target_label=label,
                transaction_code=self._preset_tx_code,
                active_data_sub_id=target.sub_id,
                verified=True,
            )

        # 步骤 2：自愈扫描（事务码 20-50）
        logger.warning(
            f"预设事务码 {self._preset_tx_code} 未生效，"
            f"启动自愈扫描 (范围 {self._scan_low}-{self._scan_high})"
        )
        return await self._scan_and_switch(target, label, timeout)

    async def _scan_and_switch(
        self,
        target: SimInfo,
        label: str,
        timeout: float,
    ) -> SimSwitchResult:
        """扫描事务码 20-50 尝试切换"""
        for code in range(self._scan_low, self._scan_high + 1):
            await self._exec_service_call(target.sub_id, code, timeout)
            await asyncio.sleep(0.4)
            check_sub = await self._get_active_sub_id(timeout)
            if check_sub == target.sub_id:
                logger.info(f"自愈成功 [{label}] → SubID {target.sub_id}，事务码 {code}")
                return SimSwitchResult(
                    success=True,
                    method="rish_scan",
                    target_label=label,
                    transaction_code=code,
                    active_data_sub_id=target.sub_id,
                    verified=True,
                )

        logger.error(
            f"自愈扫描失败 [{label}] SubID {target.sub_id}，"
            f"扫描范围 {self._scan_low}-{self._scan_high} 均未生效"
        )
        return SimSwitchResult(
            success=False,
            target_label=label,
            error=f"预设事务码 {self._preset_tx_code} 和扫描 {self._scan_low}-{self._scan_high} 均失败",
        )

    async def _exec_service_call(
        self, sub_id: int, tx_code: int, timeout: float
    ) -> None:
        """执行 service call isub <code> i32 <sub_id>"""
        cmd = f"{self._rish} -c \"service call isub {tx_code} i32 {sub_id}\""
        await self.shell.run_command(cmd, timeout)
        # 忽略返回值，因为 service call 在成功时也可能返回非 0

    async def _get_active_sub_id(self, timeout: float) -> int:
        """快速获取当前激活的数据 SubID（轻量查询）"""
        cmd = f"{self._rish} -c \"dumpsys isub\""
        rc, stdout, _ = await self.shell.run_command(cmd, timeout)
        if rc != 0 or not stdout:
            return -1
        return self._extract_active_sub_id(stdout)

    def _ensure_rish(self) -> None:
        """校验 Rish 可执行文件是否存在"""
        if not os.path.isfile(self._rish) or not os.access(self._rish, os.X_OK):
            raise FileNotFoundError(
                f"Rish 执行文件不可用: {self._rish}\n"
                f"请确认 Shizuku 已运行且 Rish 已正确安装到 ~/.atlas_sentinel/bin/rish"
            )

    # ------------------------------------------------------------------
    # dumpsys isub 解析
    # ------------------------------------------------------------------

    def _parse_dump(self, dump: str) -> SimStatus:
        """解析 dumpsys isub 输出，提取双卡信息"""
        active_sub = self._extract_active_sub_id(dump)
        primary, secondary = self._extract_sim_infos(dump)

        is_primary_active = (
            primary is not None and active_sub == primary.sub_id
        )

        return SimStatus(
            primary=primary,
            secondary=secondary,
            active_data_sub_id=active_sub,
            active_is_primary=is_primary_active,
        )

    @staticmethod
    def _extract_active_sub_id(dump: str) -> int:
        """从 dumpsys isub 中提取 activeDataSubId"""
        import re
        match = re.search(r"activeDataSubId=(\d+)", dump)
        if match:
            return int(match.group(1))
        return -1

    def _extract_sim_infos(self, dump: str) -> Tuple[Optional[SimInfo], Optional[SimInfo]]:
        """
        解析所有 SubscriptionInfo 行，按 primary_keyword 分类。

        返回 (primary, secondary) 元组。
        """
        import re
        primary: Optional[SimInfo] = None
        secondary: Optional[SimInfo] = None

        # 匹配 SubscriptionInfo 块：从 "SubscriptionInfo:" 到下一个空行或结尾
        blocks = re.split(r"\n(?=\S)", dump)
        for block in blocks:
            if "SubscriptionInfo:" not in block:
                continue

            sub_id_match = re.search(r"\bid=(\d+)", block)
            slot_match = re.search(r"simSlotIndex=(-?\d+)", block)
            display_match = re.search(r"displayName=(\S+)", block)
            carrier_match = re.search(r"carrierName=(\S+)", block)

            if not sub_id_match or not slot_match:
                continue

            sub_id = int(sub_id_match.group(1))
            slot = int(slot_match.group(1))

            # 仅处理有效卡槽 (simSlotIndex >= 0)
            if slot < 0:
                continue

            display = display_match.group(1) if display_match else ""
            carrier = carrier_match.group(1) if carrier_match else ""

            info = SimInfo(
                sub_id=sub_id,
                slot_index=slot,
                display_name=display,
                carrier_name=carrier,
            )

            # 关键字匹配：displayName 或 carrierName 包含 primary_keyword
            if self._primary_keyword.lower() in (display + carrier).lower():
                primary = info
            else:
                secondary = info

        return primary, secondary


# ---------------------------------------------------------------------------
# HighPrivilegeExecutor — 对外统一接口
# ---------------------------------------------------------------------------


class HighPrivilegeExecutor:
    """
    高权限操作执行器。

    SIM 切换使用 ShizukuSimManager（Rish 方案），不再走 settings/service call phone 回退。
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
