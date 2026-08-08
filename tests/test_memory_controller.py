"""
Unit tests for core/memory_controller.py — MemoryController.

Tests cover three-tier probing, two-level gating, debouncing,
and graceful degradation when psutil is unavailable.
"""

import pytest
from unittest.mock import patch, MagicMock

from core.memory_controller import MemoryController, GateState, MemoryGate, MemoryStats


# ---------------------------------------------------------------------------
# Construction & validation
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_default_limits(self):
        mc = MemoryController()
        assert mc.soft_limit_mb == 150
        assert mc.hard_limit_mb == 200
        assert mc.debounce_count == 3
        assert mc.state == GateState.ACCEPT

    def test_custom_limits(self):
        mc = MemoryController(soft_limit_mb=100, hard_limit_mb=180, debounce_count=5)
        assert mc.soft_limit_mb == 100
        assert mc.hard_limit_mb == 180
        assert mc.debounce_count == 5

    def test_soft_must_be_less_than_hard(self):
        with pytest.raises(ValueError, match="soft_limit_mb"):
            MemoryController(soft_limit_mb=200, hard_limit_mb=200)
        with pytest.raises(ValueError, match="soft_limit_mb"):
            MemoryController(soft_limit_mb=250, hard_limit_mb=200)


# ---------------------------------------------------------------------------
# Gate evaluation (unit-level, no I/O)
# ---------------------------------------------------------------------------

class TestGateEvaluation:
    """Tests for _evaluate which is synchronous and deterministic"""

    def test_accept_when_below_soft(self):
        mc = MemoryController(soft_limit_mb=150, hard_limit_mb=200)
        gate = mc._evaluate(rss_mb=100)
        assert gate.state == GateState.ACCEPT
        assert gate.rss_mb == 100

    def test_soft_throttle_when_above_soft(self):
        mc = MemoryController(soft_limit_mb=150, hard_limit_mb=200)
        gate = mc._evaluate(rss_mb=170)
        assert gate.state == GateState.SOFT_THROTTLE
        assert "exceeds soft limit" in gate.reason

    def test_hard_reject_when_above_hard(self):
        mc = MemoryController(soft_limit_mb=150, hard_limit_mb=200)
        gate = mc._evaluate(rss_mb=220)
        assert gate.state == GateState.HARD_REJECT
        assert "exceeds hard limit" in gate.reason

    def test_boundary_exactly_at_soft(self):
        mc = MemoryController(soft_limit_mb=150, hard_limit_mb=200)
        gate = mc._evaluate(rss_mb=150)
        assert gate.state == GateState.SOFT_THROTTLE

    def test_boundary_exactly_at_hard(self):
        mc = MemoryController(soft_limit_mb=150, hard_limit_mb=200)
        gate = mc._evaluate(rss_mb=200)
        assert gate.state == GateState.HARD_REJECT


# ---------------------------------------------------------------------------
# Debouncing
# ---------------------------------------------------------------------------

class TestDebouncing:
    def test_no_flip_on_single_spike(self):
        mc = MemoryController(soft_limit_mb=150, hard_limit_mb=200, debounce_count=3)
        # Spike once to hard, should not change state
        mc._update_state(GateState.HARD_REJECT)
        assert mc.state == GateState.ACCEPT  # still ACCEPT after first spike

    def test_flip_after_consecutive(self):
        mc = MemoryController(soft_limit_mb=150, hard_limit_mb=200, debounce_count=3)
        for _ in range(3):
            mc._update_state(GateState.SOFT_THROTTLE)
        assert mc.state == GateState.SOFT_THROTTLE

    def test_counter_resets_on_different_state(self):
        mc = MemoryController(soft_limit_mb=150, hard_limit_mb=200, debounce_count=3)
        mc._update_state(GateState.SOFT_THROTTLE)  # count=1
        mc._update_state(GateState.SOFT_THROTTLE)  # count=2
        mc._update_state(GateState.ACCEPT)          # resets
        assert mc.state == GateState.ACCEPT  # hasn't flipped
        mc._update_state(GateState.SOFT_THROTTLE)  # fresh count=1
        assert mc.state == GateState.ACCEPT


# ---------------------------------------------------------------------------
# State change callbacks
# ---------------------------------------------------------------------------

class TestCallbacks:
    def test_callback_fired_on_state_change(self):
        mc = MemoryController(soft_limit_mb=150, hard_limit_mb=200, debounce_count=1)
        transitions = []

        mc.on_state_change(lambda old, new: transitions.append((old, new)))
        mc._update_state(GateState.HARD_REJECT)

        assert len(transitions) == 1
        assert transitions[0] == (GateState.ACCEPT, GateState.HARD_REJECT)

    def test_callback_not_fired_when_no_change(self):
        mc = MemoryController(soft_limit_mb=150, hard_limit_mb=200, debounce_count=1)
        transitions = []

        mc.on_state_change(lambda old, new: transitions.append((old, new)))
        mc._update_state(GateState.ACCEPT)  # same as current

        assert len(transitions) == 0

    def test_callback_exception_does_not_crash(self):
        mc = MemoryController(soft_limit_mb=150, hard_limit_mb=200, debounce_count=1)

        def bad_callback(old, new):
            raise RuntimeError("callback boom")

        mc.on_state_change(bad_callback)
        # Should not raise
        mc._update_state(GateState.HARD_REJECT)
        assert mc.state == GateState.HARD_REJECT


# ---------------------------------------------------------------------------
# Probe fallback (without I/O - mock the probe chain)
# ---------------------------------------------------------------------------

class TestProbeFallback:
    def test_try_psutil_when_unavailable(self):
        mc = MemoryController()
        mc._psutil_available = False
        result = mc._try_psutil()
        assert result is None

    def test_try_proc_status_when_unavailable(self):
        mc = MemoryController()
        mc._proc_status_available = False
        result = mc._try_proc_status()
        assert result is None

    def test_fallback_estimate_returns_int(self):
        mc = MemoryController()
        result = mc._fallback_estimate()
        assert isinstance(result, int)
        assert result > 0

    def test_active_probe_method_reports_correctly(self):
        mc = MemoryController()
        mc._psutil_available = True
        assert mc._active_probe_method() == "psutil"
        mc._psutil_available = False
        mc._proc_status_available = True
        assert mc._active_probe_method() == "/proc/self/status"
        mc._proc_status_available = False
        assert mc._active_probe_method() == "fallback"


# ---------------------------------------------------------------------------
# can_accept integration (mock probe)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCanAcceptAsync:
    async def test_accept_within_limits(self):
        mc = MemoryController(soft_limit_mb=150, hard_limit_mb=200, debounce_count=1)
        with patch.object(mc, '_probe_rss_mb', return_value=80):
            gate = await mc.can_accept()
            assert gate.state == GateState.ACCEPT

    async def test_hard_reject_over_limit(self):
        mc = MemoryController(soft_limit_mb=150, hard_limit_mb=200, debounce_count=1)
        with patch.object(mc, '_probe_rss_mb', return_value=250):
            gate = await mc.can_accept()
            assert gate.state == GateState.HARD_REJECT

    async def test_soft_throttle(self):
        mc = MemoryController(soft_limit_mb=150, hard_limit_mb=200, debounce_count=1)
        with patch.object(mc, '_probe_rss_mb', return_value=160):
            gate = await mc.can_accept()
            assert gate.state == GateState.SOFT_THROTTLE


# ---------------------------------------------------------------------------
# stats & force_gc
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestStatsAndGC:
    async def test_stats_returns_snapshot(self):
        mc = MemoryController()
        with patch.object(mc, '_probe_rss_mb', return_value=100):
            stats = await mc.stats()
            assert isinstance(stats, MemoryStats)
            assert stats.current_rss_mb == 100
            assert stats.probe_method is not None

    async def test_force_gc_does_not_crash(self):
        mc = MemoryController()
        with patch.object(mc, '_probe_rss_mb', return_value=100):
            await mc.force_gc()  # Should not raise
            assert mc._gc_collections >= 1
