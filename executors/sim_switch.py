# executors/sim_switch.py
"""
双卡数据切换 — Shizuku/Rish 方案（唯一方案）

职责：SIM 卡 SubID 解析、主/副卡识别、数据卡切换与自愈扫描。

此模块从 executors/high_privilege.py 拆分而来（v9.0 架构优化），
包含 AutoJS6SimSwitcher 抽象接口和 ShizukuSimManager 核心实现。
"""

import asyncio
import logging
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Tuple

from models.sim import SimInfo, SimStatus, SimSwitchResult
from .shell_executor import SafeShellExecutor

logger = logging.getLogger("Atlas.SimSwitch")


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
        match = re.search(r"activeDataSubId=(\d+)", dump)
        if match:
            return int(match.group(1))
        return -1

    def _extract_sim_infos(self, dump: str) -> Tuple[Optional[SimInfo], Optional[SimInfo]]:
        """
        解析所有 SubscriptionInfo 行，按 primary_keyword 分类。

        返回 (primary, secondary) 元组。
        """
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
