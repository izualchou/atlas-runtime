"""
Unit tests for core/circuit_breaker.py — CircuitBreaker.

Tests cover the CLOSED→OPEN→HALF_OPEN three-state model,
failure counting, recovery timeout, and statistics.
"""

import time
import pytest
from unittest.mock import patch

from core.circuit_breaker import CircuitBreaker, CircuitState, CircuitBreakerStats


# ---------------------------------------------------------------------------
# Construction & validation
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_default_values(self):
        cb = CircuitBreaker()
        assert cb.failure_threshold == 5
        assert cb.recovery_timeout == 30.0
        assert cb.get_state() == "closed"

    def test_custom_values(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10.0)
        assert cb.failure_threshold == 3
        assert cb.recovery_timeout == 10.0

    def test_invalid_threshold(self):
        with pytest.raises(ValueError):
            CircuitBreaker(failure_threshold=0)
        with pytest.raises(ValueError):
            CircuitBreaker(failure_threshold=-1)

    def test_invalid_timeout(self):
        with pytest.raises(ValueError):
            CircuitBreaker(recovery_timeout=0)
        with pytest.raises(ValueError):
            CircuitBreaker(recovery_timeout=-1.0)


# ---------------------------------------------------------------------------
# CLOSED state behavior
# ---------------------------------------------------------------------------

class TestClosedState:
    def test_not_open_initially(self):
        cb = CircuitBreaker()
        assert cb.is_open() is False

    def test_does_not_open_below_threshold(self):
        cb = CircuitBreaker(failure_threshold=5)
        for _ in range(4):
            cb.record_failure()
        assert cb.is_open() is False
        assert cb.get_state() == "closed"

    def test_opens_at_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.get_state() == "closed"
        cb.record_failure()  # 3rd failure
        assert cb.is_open() is True
        assert cb.get_state() == "open"

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=5)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.get_state() == "closed"
        # Need 5 more failures (fresh count)
        for _ in range(4):
            cb.record_failure()
        assert cb.get_state() == "closed"


# ---------------------------------------------------------------------------
# OPEN → HALF_OPEN transition
# ---------------------------------------------------------------------------

class TestHalfOpenTransition:
    @patch('core.circuit_breaker.time')
    def test_transitions_to_half_open_after_timeout(self, mock_time):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=30.0)

        # Open the circuit
        mock_time.time.return_value = 100.0
        cb.record_failure()
        assert cb.get_state() == "open"

        # Still open just before timeout
        mock_time.time.return_value = 129.9
        assert cb.is_open() is True

        # Half-open after timeout
        mock_time.time.return_value = 130.0
        assert cb.is_open() is False
        assert cb.get_state() == "half_open"

    @patch('core.circuit_breaker.time')
    def test_only_one_probe_in_half_open(self, mock_time):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=30.0)

        mock_time.time.return_value = 0.0
        cb.record_failure()  # OPEN

        mock_time.time.return_value = 31.0
        # First call: allows probe
        assert cb.is_open() is False
        # Second call: rejects (probe in progress)
        assert cb.is_open() is True

    @patch('core.circuit_breaker.time')
    def test_success_in_half_open_closes(self, mock_time):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=30.0)

        mock_time.time.return_value = 0.0
        cb.record_failure()  # OPEN

        mock_time.time.return_value = 31.0
        cb.is_open()  # transition to HALF_OPEN + allow probe

        cb.record_success()  # close
        assert cb.get_state() == "closed"

    @patch('core.circuit_breaker.time')
    def test_failure_in_half_open_reopens(self, mock_time):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=30.0)

        mock_time.time.return_value = 0.0
        cb.record_failure()  # OPEN

        mock_time.time.return_value = 31.0
        cb.is_open()  # transition to HALF_OPEN

        cb.record_failure()  # re-open
        assert cb.get_state() == "open"


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

class TestStatistics:
    def test_stats_after_operations(self):
        cb = CircuitBreaker(failure_threshold=5)
        cb.record_success()
        cb.record_failure()
        cb.record_failure()

        stats = cb.stats()
        assert isinstance(stats, CircuitBreakerStats)
        assert stats.state == CircuitState.CLOSED
        assert stats.failure_count == 2
        assert stats.total_successes == 1
        assert stats.total_failures == 2

    def test_stats_after_opening(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()

        stats = cb.stats()
        assert stats.times_opened == 1
        assert stats.opened_at is not None


# ---------------------------------------------------------------------------
# Manual reset
# ---------------------------------------------------------------------------

class TestReset:
    def test_reset_from_open(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.get_state() == "open"

        cb.reset()
        assert cb.get_state() == "closed"
        assert cb.is_open() is False

    def test_reset_clears_counters(self):
        cb = CircuitBreaker(failure_threshold=5)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()

        cb.reset()
        stats = cb.stats()
        assert stats.failure_count == 0
        assert stats.opened_at is None
