# core/memory_controller.py
"""
内存守护控制器（Memory Controller）。

在关键决策点通过被动探测评估内存压力，实施两级门控策略。
专为 Samsung One UI 8.5 + Termux 移动环境设计，零 CPU 持续开销。

设计原则:
- 被动门控：不启动后台循环，仅在 submit/trigger 时同步探测
- 三级探测：psutil → /proc/self/status → 兜底估算，优雅降级
- 两级限流：软限暂停新任务受理 + 日志告警，硬限拒绝写入 + 强制 GC
- 防抖机制：连续 N 次相同状态才切换，避免因瞬时 GC 导致的状态抖动

v9.1: 使用 asyncio.to_thread() 将同步探测委托给线程池，避免阻塞事件循环。
"""

import logging
import os
import gc
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, List, Optional

logger = logging.getLogger("Atlas.MemoryController")


class GateState(Enum):
    """门控状态枚举"""
    ACCEPT = auto()          # 正常受理
    SOFT_THROTTLE = auto()   # 软限：暂停新任务受理，日志告警
    HARD_REJECT = auto()     # 硬限：拒绝所有写入，触发 GC


@dataclass
class MemoryGate:
    """门控决策结果"""
    state: GateState
    rss_mb: int
    soft_limit_mb: int
    hard_limit_mb: int
    reason: str


@dataclass
class MemoryStats:
    """内存统计快照"""
    current_rss_mb: int
    peak_rss_mb: int
    state_history: List[str] = field(default_factory=list)
    rejection_count: int = 0
    probe_method: str = "unknown"
    gc_collections: int = 0


class MemoryController:
    """
    内存守护控制器。

    Attributes:
        soft_limit_mb: 软内存限制（MB），超限后告警并暂停新任务受理
        hard_limit_mb: 硬内存限制（MB），超限后拒绝写入并强制 GC
        debounce_count: 防抖阈值，连续 N 次相同状态才切换（默认 3）
    """

    def __init__(
        self,
        soft_limit_mb: int = 150,
        hard_limit_mb: int = 200,
        debounce_count: int = 3,
    ):
        if soft_limit_mb >= hard_limit_mb:
            raise ValueError(
                f"soft_limit_mb ({soft_limit_mb}) must be less than "
                f"hard_limit_mb ({hard_limit_mb})"
            )

        self.soft_limit_mb = soft_limit_mb
        self.hard_limit_mb = hard_limit_mb
        self.debounce_count = debounce_count

        # 运行时状态
        self._current_state: GateState = GateState.ACCEPT
        self._consecutive_state_count: int = 0
        self._last_desired_state: Optional[GateState] = None
        self._rejection_count: int = 0
        self._peak_rss_mb: int = 0
        self._gc_collections: int = 0
        self._state_history: List[str] = []

        # 状态变更回调
        self._on_state_change_callbacks: List[Callable] = []

        # psutil 可用性标记（延迟探测）
        self._psutil_available: Optional[bool] = None
        self._proc_status_available: Optional[bool] = None

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    async def can_accept(self) -> MemoryGate:
        """
        门控检查：当前是否可以受理新任务。

        通过 asyncio.to_thread() 委托同步探测到线程池，
        避免阻塞事件循环。在 Android 低配设备上尤为重要。

        Returns:
            MemoryGate: 门控决策结果
        """
        import asyncio
        rss_mb = await asyncio.to_thread(self._probe_rss_mb)
        gate = self._evaluate(rss_mb)
        self._record_peak(rss_mb)
        self._update_state(gate.state)
        return gate

    async def current_rss_mb(self) -> int:
        """获取当前进程 RSS（MB），委托到线程池。"""
        import asyncio
        return await asyncio.to_thread(self._probe_rss_mb)

    async def stats(self) -> MemoryStats:
        """获取内存统计快照。"""
        import asyncio
        rss_mb = await asyncio.to_thread(self._probe_rss_mb)
        return MemoryStats(
            current_rss_mb=rss_mb,
            peak_rss_mb=self._peak_rss_mb,
            state_history=list(self._state_history),
            rejection_count=self._rejection_count,
            probe_method=self._active_probe_method(),
            gc_collections=self._gc_collections,
        )

    async def force_gc(self) -> None:
        """强制执行垃圾回收并在日志中报告效果。"""
        import asyncio
        before_mb = await asyncio.to_thread(self._probe_rss_mb)
        collected = gc.collect()
        after_mb = await asyncio.to_thread(self._probe_rss_mb)
        self._gc_collections += 1
        delta = before_mb - after_mb
        logger.info(
            f"Manual GC: collected {collected} objects, "
            f"RSS {before_mb}MB → {after_mb}MB (delta={delta}MB)"
        )

    @property
    def state(self) -> GateState:
        """当前门控状态"""
        return self._current_state

    def on_state_change(self, callback: Callable[[GateState, GateState], None]) -> None:
        """
        注册状态变更回调。

        Args:
            callback: Callable[[old_state, new_state], None]
        """
        self._on_state_change_callbacks.append(callback)

    # ------------------------------------------------------------------
    # 内部探测逻辑
    # ------------------------------------------------------------------

    def _probe_rss_mb(self) -> int:
        """
        三级探测：获取当前进程 RSS（MB）。

        探测顺序:
        1. psutil.Process().memory_info().rss（最精确）
        2. /proc/self/status VmRSS 字段（无需额外依赖）
        3. 兜底估算：platform.total_ram_mb / 2（粗粒度保护）
        """
        rss = self._try_psutil()
        if rss is not None:
            return rss
        rss = self._try_proc_status()
        if rss is not None:
            return rss
        return self._fallback_estimate()

    def _try_psutil(self) -> Optional[int]:
        """尝试通过 psutil 获取 RSS（MB）。"""
        if self._psutil_available is False:
            return None
        try:
            import psutil
            self._psutil_available = True
            proc = psutil.Process(os.getpid())
            mem = proc.memory_info()
            return mem.rss // (1024 * 1024)
        except ImportError:
            self._psutil_available = False
            logger.debug("psutil not available; falling back to /proc/self/status")
            return None
        except Exception as e:
            logger.debug(f"psutil probe failed: {e}")
            return None

    def _try_proc_status(self) -> Optional[int]:
        """尝试从 /proc/self/status 读取 VmRSS（MB）。"""
        if self._proc_status_available is False:
            return None
        try:
            with open("/proc/self/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        self._proc_status_available = True
                        # 格式: "VmRSS:    12345 kB"
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            kb = int(parts[1])
                            return kb // 1024
            logger.debug("/proc/self/status exists but VmRSS not found")
            self._proc_status_available = False
            return None
        except FileNotFoundError:
            self._proc_status_available = False
            logger.debug("/proc/self/status not available (non-Linux platform)")
            return None
        except Exception as e:
            logger.debug(f"/proc/self/status probe failed: {e}")
            return None

    def _fallback_estimate(self) -> int:
        """兜底估算：使用系统总内存的 50% 作为进程 RSS 估算。"""
        try:
            import sys
            # 尝试获取总内存
            try:
                import os as _os
                total_kb = _os.sysconf('SC_PAGE_SIZE') * _os.sysconf('SC_PHYS_PAGES')
            except (AttributeError, ValueError):
                # Windows/非 POSIX 兜底
                return 100  # 保守估算

            total_mb = total_kb // 1024
            # 在移动设备上，进程通常占用总内存的 30-50%
            estimated = total_mb // 2
            logger.debug(f"Fallback RSS estimate: {estimated}MB (total={total_mb}MB)")
            return estimated
        except Exception:
            logger.warning("All memory probes failed; returning safe default of 100MB")
            return 100

    def _active_probe_method(self) -> str:
        """返回当前激活的探测方法名称。"""
        if self._psutil_available:
            return "psutil"
        if self._proc_status_available:
            return "/proc/self/status"
        return "fallback"

    # ------------------------------------------------------------------
    # 门控评估与防抖
    # ------------------------------------------------------------------

    def _evaluate(self, rss_mb: int) -> MemoryGate:
        """
        评估当前内存压力并返回门控决策。

        两级门控:
        - rss_mb >= hard_limit_mb → HARD_REJECT
        - rss_mb >= soft_limit_mb → SOFT_THROTTLE
        - otherwise → ACCEPT
        """
        if rss_mb >= self.hard_limit_mb:
            return MemoryGate(
                state=GateState.HARD_REJECT,
                rss_mb=rss_mb,
                soft_limit_mb=self.soft_limit_mb,
                hard_limit_mb=self.hard_limit_mb,
                reason=f"RSS {rss_mb}MB exceeds hard limit {self.hard_limit_mb}MB",
            )
        if rss_mb >= self.soft_limit_mb:
            return MemoryGate(
                state=GateState.SOFT_THROTTLE,
                rss_mb=rss_mb,
                soft_limit_mb=self.soft_limit_mb,
                hard_limit_mb=self.hard_limit_mb,
                reason=f"RSS {rss_mb}MB exceeds soft limit {self.soft_limit_mb}MB",
            )
        return MemoryGate(
            state=GateState.ACCEPT,
            rss_mb=rss_mb,
            soft_limit_mb=self.soft_limit_mb,
            hard_limit_mb=self.hard_limit_mb,
            reason="Memory usage within limits",
        )

    def _update_state(self, desired_state: GateState) -> None:
        """
        带防抖的状态更新。

        连续 debounce_count 次相同的期望状态才执行实际切换，
        避免因瞬时 GC 或内存尖峰导致的状态抖动。
        """

        # 防抖逻辑
        if self._last_desired_state == desired_state:
            self._consecutive_state_count += 1
        else:
            self._consecutive_state_count = 1
            self._last_desired_state = desired_state

        if self._consecutive_state_count >= self.debounce_count:
            if self._current_state != desired_state:
                old_state = self._current_state
                self._current_state = desired_state
                self._state_history.append(
                    f"{old_state.name} → {desired_state.name}"
                    f" (count={self._consecutive_state_count})"
                )
                # 裁剪历史到最近 10 条
                if len(self._state_history) > 10:
                    self._state_history = self._state_history[-10:]

                if desired_state == GateState.HARD_REJECT:
                    self._rejection_count += 1
                    logger.warning(
                        f"MemoryController: {old_state.name} → {desired_state.name}. "
                        f"Rejection count: {self._rejection_count}"
                    )
                else:
                    logger.info(
                        f"MemoryController: {old_state.name} → {desired_state.name}"
                    )

                # 触发回调
                for cb in self._on_state_change_callbacks:
                    try:
                        cb(old_state, desired_state)
                    except Exception as e:
                        logger.error(
                            f"MemoryController state change callback failed: {e}",
                            exc_info=True,
                        )

    def _record_peak(self, rss_mb: int) -> None:
        """记录峰值 RSS。"""
        if rss_mb > self._peak_rss_mb:
            self._peak_rss_mb = rss_mb
