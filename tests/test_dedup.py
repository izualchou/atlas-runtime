"""
Unit tests for core/dedup.py — DedupFilter.

Tests cover correlation_id hashing, TTL-based dedup,
lazy expiration cleanup, capacity limits, and statistics.
"""

import time
import pytest
from unittest.mock import patch

from core.dedup import DedupFilter


# ---------------------------------------------------------------------------
# Construction & validation
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_default_values(self):
        df = DedupFilter()
        assert df.ttl == 60.0
        assert df.max_entries == 10000
        assert df.size() == 0

    def test_custom_values(self):
        df = DedupFilter(ttl=30.0, max_entries=500)
        assert df.ttl == 30.0
        assert df.max_entries == 500

    def test_invalid_ttl(self):
        with pytest.raises(ValueError):
            DedupFilter(ttl=0)
        with pytest.raises(ValueError):
            DedupFilter(ttl=-1.0)

    def test_invalid_max_entries(self):
        with pytest.raises(ValueError):
            DedupFilter(max_entries=0)
        with pytest.raises(ValueError):
            DedupFilter(max_entries=-10)


# ---------------------------------------------------------------------------
# Basic dedup (within TTL)
# ---------------------------------------------------------------------------

class TestBasicDedup:
    def test_first_occurrence_not_duplicate(self):
        df = DedupFilter()
        assert df.is_duplicate("event-001") is False

    def test_second_occurrence_is_duplicate(self):
        df = DedupFilter()
        assert df.is_duplicate("event-001") is False
        df.mark_seen("event-001")
        assert df.is_duplicate("event-001") is True

    def test_different_ids_are_not_duplicates(self):
        df = DedupFilter()
        df.mark_seen("event-001")
        assert df.is_duplicate("event-002") is False

    def test_mark_seen_then_never_marked_again(self):
        df = DedupFilter()
        df.mark_seen("event-001")
        # Calling is_duplicate again should still be True
        assert df.is_duplicate("event-001") is True
        assert df.is_duplicate("event-001") is True


# ---------------------------------------------------------------------------
# TTL expiration
# ---------------------------------------------------------------------------

class TestTTLExpiration:
    @patch('core.dedup.time')
    def test_expires_after_ttl(self, mock_time):
        df = DedupFilter(ttl=60.0)

        mock_time.time.return_value = 100.0
        assert df.is_duplicate("event-001") is False
        df.mark_seen("event-001")

        # Within TTL
        mock_time.time.return_value = 150.0
        assert df.is_duplicate("event-001") is True

        # After TTL
        mock_time.time.return_value = 160.1
        assert df.is_duplicate("event-001") is False

    @patch('core.dedup.time')
    def test_different_ttl_values(self, mock_time):
        df = DedupFilter(ttl=5.0)

        mock_time.time.return_value = 100.0
        df.mark_seen("event-001")

        mock_time.time.return_value = 104.9
        assert df.is_duplicate("event-001") is True

        mock_time.time.return_value = 105.1
        assert df.is_duplicate("event-001") is False


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

class TestCleanup:
    @patch('core.dedup.time')
    def test_cleanup_expired_removes_entries(self, mock_time):
        df = DedupFilter(ttl=10.0)

        mock_time.time.return_value = 100.0
        df.mark_seen("event-001")
        df.mark_seen("event-002")
        assert df.size() == 2

        mock_time.time.return_value = 120.0
        removed = df.cleanup_expired()
        assert removed == 2
        assert df.size() == 0

    @patch('core.dedup.time')
    def test_cleanup_keeps_valid_entries(self, mock_time):
        df = DedupFilter(ttl=10.0)

        # Insert old-event first, then advance time and insert new-event
        mock_time.time.return_value = 100.0
        df.mark_seen("old-event")

        mock_time.time.return_value = 105.0
        df.mark_seen("new-event")
        assert df.size() == 2

        # Advance past old-event TTL but within new-event TTL
        # old-event: expire at 100 + 10 = 110, now=112 → expired
        # new-event: expire at 105 + 10 = 115, now=112 → valid
        mock_time.time.return_value = 112.0
        removed = df.cleanup_expired()
        assert removed == 1  # only old-event expired
        assert df.size() == 1

    def test_clear_resets_all(self):
        df = DedupFilter()
        df.mark_seen("event-001")
        df.mark_seen("event-002")

        df.clear()
        assert df.size() == 0
        assert df._total_checks == 0
        assert df._duplicates_found == 0


# ---------------------------------------------------------------------------
# Capacity limits
# ---------------------------------------------------------------------------

class TestCapacity:
    @patch('core.dedup.time')
    def test_evicts_oldest_when_full(self, mock_time):
        df = DedupFilter(ttl=60.0, max_entries=3)

        # Fill to capacity: use same timestamp so no lazy expiration fires
        mock_time.time.return_value = 100.0
        for i in range(3):
            df.mark_seen(f"event-{i:03d}")

        assert df.size() == 3

        # Advance slightly (still within TTL) and add one more
        mock_time.time.return_value = 110.0
        df.mark_seen("event-003")
        assert df.size() == 3
        # event-000 should be evicted (oldest) by capacity limit
        assert df.is_duplicate("event-000") is False
        assert df.is_duplicate("event-003") is True


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

class TestStatistics:
    def test_counts_tracked(self):
        df = DedupFilter()
        df.mark_seen("event-001")
        assert df.is_duplicate("event-001")  # duplicate

        assert df._total_checks >= 1
        assert df._duplicates_found >= 1

    def test_size_accurate(self):
        df = DedupFilter()
        assert df.size() == 0
        df.mark_seen("a")
        df.mark_seen("b")
        df.mark_seen("c")
        assert df.size() == 3
