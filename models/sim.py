# models/sim.py
"""
SIM 卡数据模型。

定义 SIM 信息、状态快照和切换结果的纯数据结构。
从 executors/high_privilege.py 提取，供所有模块安全引用。
"""

from dataclasses import dataclass
from typing import Optional


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
