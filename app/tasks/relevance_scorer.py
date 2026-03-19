"""Pillar 2 — Relevance scoring for social mentions.

Scores a social post on a 0–100 scale based on keyword match quality,
Google page-1 ranking, engagement, and recency.  Higher scores surface
in the dashboard and trigger alerts.

Scoring weights
---------------
+40  keyword found in title (case-insensitive, exact substring match)
+20  keyword found in content_snippet only (case-insensitive partial match)
+30  google_rank is not None and <= 10 (thread is on Google page 1)
+20  engagement (upvotes/score) > 100
+10  engagement > 20  (mutually exclusive with the > 100 bucket)
+10  post created within the last 24 hours
 +5  post created within the last 7 days  (mutually exclusive with 24h bucket)

Maximum possible raw score: 40 + 30 + 20 + 10 = 100 — cap is a safety net.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_24H = timedelta(hours=24)
_7D = timedelta(days=7)


def score_mention(mention: dict[str, Any], keyword: str) -> int:
    """Compute a 0–100 relevance score for a social mention.

    Args:
        mention: Dict with keys: ``title`` (str|None), ``content_snippet``
                 (str|None), ``google_rank`` (int|None), ``engagement`` (int),
                 ``created_at`` (datetime, UTC-aware or naive).
        keyword: The keyword being tracked (compared case-insensitively).

    Returns:
        Integer score in the range [0, 100].
    """
    score = 0
    kw = keyword.lower()

    # ------------------------------------------------------------------
    # Keyword match — title wins; content is the fallback
    # ------------------------------------------------------------------
    title = (mention.get("title") or "").lower()
    snippet = (mention.get("content_snippet") or "").lower()

    if kw in title:
        score += 40
        logger.debug("score_mention: +40 keyword in title")
    elif kw in snippet:
        score += 20
        logger.debug("score_mention: +20 keyword in content_snippet")

    # ------------------------------------------------------------------
    # Google ranking (page 1 = high citation potential)
    # ------------------------------------------------------------------
    google_rank = mention.get("google_rank")
    if google_rank is not None and google_rank <= 10:
        score += 30
        logger.debug("score_mention: +30 google_rank=%d", google_rank)

    # ------------------------------------------------------------------
    # Engagement (Reddit upvotes / score)
    # ------------------------------------------------------------------
    engagement = mention.get("engagement") or 0
    if engagement > 100:
        score += 20
        logger.debug("score_mention: +20 engagement=%d", engagement)
    elif engagement > 20:
        score += 10
        logger.debug("score_mention: +10 engagement=%d", engagement)

    # ------------------------------------------------------------------
    # Recency
    # ------------------------------------------------------------------
    created_at: datetime | None = mention.get("created_at")
    if created_at is not None:
        # Normalise naive datetimes to UTC so subtraction is safe
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        age = datetime.now(timezone.utc) - created_at

        if age < _24H:
            score += 10
            logger.debug("score_mention: +10 recency < 24h")
        elif age < _7D:
            score += 5
            logger.debug("score_mention: +5 recency < 7d")

    final = min(score, 100)
    logger.debug("score_mention: keyword=%r final_score=%d", keyword, final)
    return final
