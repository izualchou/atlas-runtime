# core/circuit_breaker.py
"""
熔断器模块（Circuit Breaker）。

实现 CLOSED → OPEN → HALF_OPEN 三态熔断模型，保护系统免受级联故障。
当连续失败次数超过阈值时自动熔断，冷却后半开探测，成功后恢复。

设计原则:
- 无锁设计：使用 Python 原子赋值操作替代显式锁，状态切换无竞态条件
- 三态模型：CLOSED（正常）→ OPEN（熔断）→ HALF_OPEN（探测）→ CLOSED/HARD_REJECT
- 移动端优化：冷却时间默认为 30 秒，适配 Android 后台限制下的恢复节奏
- 零外部依赖：纯 Python 实现，与 asyncio 兼容但无异步依赖

v9.1: 引入 HALF_OPEN 半开探测逻辑，彻底区分零失败与零请求。
"""

import time
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("Atlas.CircuitBreaker")


class CircuitState(str, Enum):
    """熔断器状态枚举"""
    CLOSED = "closed"        # 正常受理
    OPEN = "open"            # 熔断中，拒绝受理
    HALF_OPEN = "half_open"  # 半开探测，允许一个探测请求


@dataclass
class CircuitBreakerStats:
    """熔断器统计快照"""
    state: CircuitState
    failure_count: int
    total_failures: int
    total_successes: int
    last_failure_time: Optional[float]
    last_success_time: Optional[float]
    opened_at: Optional[float]
    times_opened: int


class CircuitBreaker:
    """
    三态熔断器。

    状态转换:
    CLOSED → OPEN: 连续失败达到 failure_threshold
    OPEN → HALF_OPEN: 冷却时间 recovery_timeout 到期
    HALF_OPEN → CLOSED: 探测请求成功
    HALF_OPEN → OPEN: 探测请求失败

    Attributes:
        failure_threshold: 连续失败阈值，默认 5
        recovery_timeout: 冷却时间（秒），默认 30.0
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ):
        if failure_threshold < 1:
            raise ValueError(f"failure_threshold must be >= 1, got {failure_threshold}")
        if recovery_timeout <= 0:
            raise ValueError(f"recovery_timeout must be > 0, got {recovery_timeout}")

        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        # 运行时状态（原子赋值，无需锁）
        self._state: CircuitState = CircuitState.CLOSED
        self._consecutive_failures: int = 0
        self._total_failures: int = 0
        self._total_successes: int = 0
        self._last_failure_time: Optional[float] = None
        self._last_success_time: Optional[float] = None
        self._opened_at: Optional[float] = None
        self._times_opened: int = 0
        self._half_open_in_progress: bool = False

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def record_success(self) -> None:
        """
        记录一次成功。

        在 HALF_OPEN 状态成功后关闭熔断器恢复到 CLOSED。
        在 CLOSED 状态重置连续失败计数。
        """
        now = time.time()
        self._total_successes += 1
        self._last_success_time = now

        if self._state == CircuitState.HALF_OPEN:
            logger.info(
                f"CircuitBreaker: probe succeeded, transitioning HALF_OPEN → CLOSED"
            )
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._opened_at = None
            self._half_open_in_progress = False
        elif self._state == CircuitState.CLOSED:
            # 成功后重置连续失败计数
            if self._consecutive_failures > 0:
                self._consecutive_failures = 0
                logger.debug("CircuitBreaker: consecutive failures reset after success")

    def record_failure(self) -> None:
        """
        记录一次失败。

        在 CLOSED 状态累计连续失败，达到阈值则熔断。
        在 HALF_OPEN 状态探测失败则重新熔断。
        在 OPEN 状态仅记录统计。
        """
        now = time.time()
        self._total_failures += 1
        self._last_failure_time = now

        if self._state == CircuitState.CLOSED:
            self._consecutive_failures += 1
            logger.debug(
                f"CircuitBreaker: failure {self._consecutive_failures}/"
                f"{self.failure_threshold} in CLOSED state"
            )
            if self._consecutive_failures >= self.failure_threshold:
                self._open()
        elif self._state == CircuitState.HALF_OPEN:
            logger.warning("CircuitBreaker: probe failed, re-opening circuit")
            self._consecutive_failures = 1
            self._open()

    def is_open(self) -> bool:
        """
        检查熔断器是否开启（拒绝受理）。

        在 OPEN 状态但冷却时间已到时触发 HALF_OPEN 过渡，
        允许一个探测请求通过以测试恢复情况。

        Returns:
            True 如果当前应拒绝受理，False 如果允许受理
        """
        if self._state == CircuitState.CLOSED:
            return False

        if self._state == CircuitState.OPEN:
            # 检查冷却时间是否到期
            if self._opened_at is not None:
                elapsed = time.time() - self._opened_at
                if elapsed >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_in_progress = True  # 这次调用本身即探测请求
                    logger.info(
                        f"CircuitBreaker: recovery timeout expired ({elapsed:.1f}s), "
                        f"transitioning OPEN → HALF_OPEN"
                    )
                    return False  # 允许这次探测请求
            return True

        if self._state == CircuitState.HALF_OPEN:
            if self._half_open_in_progress:
                return True  # 已有探测请求在进行中，拒绝后续请求
            self._half_open_in_progress = True
            return False  # 允许此探测请求

        return True  # 防御性：未知状态等同于 OPEN

    def get_state(self) -> str:
        """获取当前状态字符串（用于监控和日志）。"""
        return self._state.value

    def stats(self) -> CircuitBreakerStats:
        """获取熔断器统计快照。"""
        return CircuitBreakerStats(
            state=self._state,
            failure_count=self._consecutive_failures,
            total_failures=self._total_failures,
            total_successes=self._total_successes,
            last_failure_time=self._last_failure_time,
            last_success_time=self._last_success_time,
            opened_at=self._opened_at,
            times_opened=self._times_opened,
        )

    def reset(self) -> None:
        """
        强制重置熔断器到 CLOSED 状态。

        用于手动恢复或测试场景。在运维层面应谨慎使用。
        """
        logger.info("CircuitBreaker: manual reset to CLOSED")
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at = None
        self._half_open_in_progress = False

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _open(self) -> None:
        """切换到 OPEN 状态"""
        old_state = self._state
        self._state = CircuitState.OPEN
        self._opened_at = time.time()
        self._times_opened += 1
        self._half_open_in_progress = False
        logger.warning(
            f"CircuitBreaker: {old_state.value.upper()} → OPEN "
            f"(failure #{self._total_failures}, opened {self._times_opened} times)"
        )
