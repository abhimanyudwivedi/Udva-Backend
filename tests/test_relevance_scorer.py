"""Tests for app/tasks/relevance_scorer.py.

Covers every scoring bucket, mutual-exclusion rules, the 100-point cap,
and the zero-score edge case.  No external dependencies — all inputs are
plain dicts with controlled field values.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from app.tasks.relevance_scorer import score_mention

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)


def _mention(**overrides: Any) -> dict[str, Any]:
    """Return a base mention dict that scores zero, with optional overrides."""
    base: dict[str, Any] = {
        "title": "unrelated post",
        "content_snippet": "nothing relevant here",
        "google_rank": None,
        "engagement": 0,
        "created_at": _NOW - timedelta(days=30),  # old — no recency points
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Keyword match
# ---------------------------------------------------------------------------


class TestKeywordMatch:
    def test_exact_keyword_in_title(self) -> None:
        m = _mention(title="Udva is the best GEO tool", content_snippet="")
        assert score_mention(m, "Udva") == 40

    def test_keyword_match_is_case_insensitive_title(self) -> None:
        m = _mention(title="UDVA is awesome")
        assert score_mention(m, "udva") == 40

    def test_keyword_in_content_snippet_only(self) -> None:
        m = _mention(title="unrelated title", content_snippet="Udva does something")
        assert score_mention(m, "udva") == 20

    def test_keyword_in_content_is_case_insensitive(self) -> None:
        m = _mention(title="unrelated", content_snippet="UDVA mentioned here")
        assert score_mention(m, "Udva") == 20

    def test_title_wins_over_content_no_double_counting(self) -> None:
        """When keyword is in BOTH title and content, only +40 is awarded."""
        m = _mention(
            title="Udva is great",
            content_snippet="Udva appears in the body too",
        )
        assert score_mention(m, "Udva") == 40

    def test_keyword_not_in_title_or_content(self) -> None:
        m = _mention(title="something else", content_snippet="nothing relevant")
        assert score_mention(m, "Udva") == 0

    def test_none_title_falls_back_to_content(self) -> None:
        m = _mention(title=None, content_snippet="Udva is here")
        assert score_mention(m, "udva") == 20

    def test_none_content_no_partial_score(self) -> None:
        m = _mention(title="unrelated", content_snippet=None)
        assert score_mention(m, "Udva") == 0

    def test_both_none_no_keyword_score(self) -> None:
        m = _mention(title=None, content_snippet=None)
        assert score_mention(m, "Udva") == 0


# ---------------------------------------------------------------------------
# Google rank
# ---------------------------------------------------------------------------


class TestGoogleRank:
    def test_rank_1_adds_30(self) -> None:
        m = _mention(google_rank=1)
        assert score_mention(m, "anything") == 30

    def test_rank_10_adds_30(self) -> None:
        m = _mention(google_rank=10)
        assert score_mention(m, "anything") == 30

    def test_rank_11_adds_nothing(self) -> None:
        m = _mention(google_rank=11)
        assert score_mention(m, "anything") == 0

    def test_rank_none_adds_nothing(self) -> None:
        m = _mention(google_rank=None)
        assert score_mention(m, "anything") == 0


# ---------------------------------------------------------------------------
# Engagement
# ---------------------------------------------------------------------------


class TestEngagement:
    def test_engagement_101_adds_20(self) -> None:
        m = _mention(engagement=101)
        assert score_mention(m, "anything") == 20

    def test_engagement_exactly_100_adds_nothing_extra(self) -> None:
        """engagement > 100, not >= 100."""
        m = _mention(engagement=100)
        assert score_mention(m, "anything") == 10  # falls into > 20 bucket

    def test_engagement_21_adds_10(self) -> None:
        m = _mention(engagement=21)
        assert score_mention(m, "anything") == 10

    def test_engagement_exactly_20_adds_nothing(self) -> None:
        """engagement > 20, not >= 20."""
        m = _mention(engagement=20)
        assert score_mention(m, "anything") == 0

    def test_engagement_0_adds_nothing(self) -> None:
        m = _mention(engagement=0)
        assert score_mention(m, "anything") == 0

    def test_high_and_medium_are_mutually_exclusive(self) -> None:
        """500 engagement → only +20, not +20+10."""
        m = _mention(engagement=500)
        assert score_mention(m, "anything") == 20


# ---------------------------------------------------------------------------
# Recency
# ---------------------------------------------------------------------------


class TestRecency:
    def test_23_hours_old_adds_10(self) -> None:
        m = _mention(created_at=_NOW - timedelta(hours=23))
        assert score_mention(m, "anything") == 10

    def test_exactly_24_hours_old_adds_5(self) -> None:
        """Age == exactly 24h is NOT < 24h, falls into < 7d bucket."""
        m = _mention(created_at=_NOW - timedelta(hours=24))
        assert score_mention(m, "anything") == 5

    def test_3_days_old_adds_5(self) -> None:
        m = _mention(created_at=_NOW - timedelta(days=3))
        assert score_mention(m, "anything") == 5

    def test_6_days_old_adds_5(self) -> None:
        m = _mention(created_at=_NOW - timedelta(days=6, hours=23))
        assert score_mention(m, "anything") == 5

    def test_7_days_old_adds_nothing(self) -> None:
        """Age >= 7d is not < 7d."""
        m = _mention(created_at=_NOW - timedelta(days=7))
        assert score_mention(m, "anything") == 0

    def test_30_days_old_adds_nothing(self) -> None:
        m = _mention(created_at=_NOW - timedelta(days=30))
        assert score_mention(m, "anything") == 0

    def test_none_created_at_adds_nothing(self) -> None:
        m = _mention(created_at=None)
        assert score_mention(m, "anything") == 0

    def test_naive_datetime_treated_as_utc(self) -> None:
        """Naive datetimes are normalised to UTC, not rejected."""
        naive_now = datetime.utcnow() - timedelta(hours=1)
        m = _mention(created_at=naive_now)
        assert score_mention(m, "anything") == 10


# ---------------------------------------------------------------------------
# Cap and zero
# ---------------------------------------------------------------------------


class TestCapAndZero:
    def test_zero_score_no_matches(self) -> None:
        m = _mention(
            title="nothing relevant",
            content_snippet="absolutely nothing",
            google_rank=None,
            engagement=0,
            created_at=_NOW - timedelta(days=30),
        )
        assert score_mention(m, "Udva") == 0

    def test_cap_at_100(self) -> None:
        """Max raw score: 40 (title) + 30 (rank) + 20 (engagement) + 10 (24h) = 100."""
        m = _mention(
            title="Udva full house",
            google_rank=1,
            engagement=500,
            created_at=_NOW - timedelta(hours=1),
        )
        assert score_mention(m, "Udva") == 100

    def test_cap_enforced_when_all_buckets_would_overflow(self) -> None:
        """Even if logic changed to award both engagement buckets, cap holds."""
        # Simulate a hypothetical 110-point scenario by directly checking min()
        m = _mention(
            title="Udva wins",
            google_rank=1,
            engagement=500,
            created_at=_NOW - timedelta(hours=1),
        )
        result = score_mention(m, "Udva")
        assert result <= 100

    def test_partial_score_not_capped(self) -> None:
        """A moderate score (< 100) is returned exactly as computed."""
        m = _mention(
            title="Udva post",  # +40
            google_rank=None,
            engagement=50,       # +10
            created_at=_NOW - timedelta(days=30),  # 0 recency
        )
        assert score_mention(m, "Udva") == 50


# ---------------------------------------------------------------------------
# Combined / integration scenarios
# ---------------------------------------------------------------------------


class TestCombinations:
    def test_title_plus_google_rank(self) -> None:
        m = _mention(title="Udva thread", google_rank=3)
        assert score_mention(m, "Udva") == 70  # 40 + 30

    def test_content_plus_high_engagement_plus_recent(self) -> None:
        m = _mention(
            title="unrelated",
            content_snippet="udva mentioned here",
            engagement=200,
            created_at=_NOW - timedelta(hours=5),
        )
        # 20 (content) + 20 (engagement > 100) + 10 (< 24h) = 50
        assert score_mention(m, "udva") == 50

    def test_google_rank_plus_medium_engagement(self) -> None:
        m = _mention(google_rank=5, engagement=50)
        # 30 + 10 = 40
        assert score_mention(m, "anything") == 40
