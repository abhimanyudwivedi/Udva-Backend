"""Tests for app/tasks/reddit_crawler.py.

All PRAW calls are mocked — no Reddit API credentials required.
Tests operate on the in-memory SQLite session provided by the conftest
``test_db`` fixture.
"""

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mention import Mention
from app.tasks.reddit_crawler import crawl_keyword


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_KEYWORD = "testbrand"
_URL = "https://www.reddit.com/r/test/comments/abc123/testbrand_mention"


def _submission(**overrides: Any) -> dict[str, Any]:
    """Return a minimal raw submission dict that represents one Reddit post."""
    base: dict[str, Any] = {
        "url": _URL,
        "title": f"Great mention of {_KEYWORD}",  # keyword in title → +40 pts
        "content_snippet": "Some content snippet here.",
        "author": "reddituser",
        "engagement": 50,      # >20 → +10 pts
        "google_rank": None,
        "created_at": datetime.now(timezone.utc),  # <24h → +10 pts
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_new_mention_is_inserted(test_db: AsyncSession) -> None:
    """A non-duplicate submission is inserted as a Mention row."""
    brand_id = str(uuid.uuid4())

    with (
        patch(
            "app.tasks.reddit_crawler.asyncio.to_thread",
            new=AsyncMock(return_value=[_submission()]),
        ),
        patch(
            "app.tasks.reddit_crawler.is_duplicate",
            new=AsyncMock(return_value=False),
        ),
    ):
        count = await crawl_keyword(_KEYWORD, brand_id, test_db)

    assert count == 1

    result = await test_db.execute(select(Mention))
    mentions = result.scalars().all()
    assert len(mentions) == 1
    assert mentions[0].url == _URL
    assert mentions[0].platform == "reddit"


async def test_duplicate_url_is_skipped(test_db: AsyncSession) -> None:
    """A submission whose URL+brand_id is already known is not inserted."""
    brand_id = str(uuid.uuid4())

    with (
        patch(
            "app.tasks.reddit_crawler.asyncio.to_thread",
            new=AsyncMock(return_value=[_submission()]),
        ),
        patch(
            "app.tasks.reddit_crawler.is_duplicate",
            new=AsyncMock(return_value=True),
        ),
    ):
        count = await crawl_keyword(_KEYWORD, brand_id, test_db)

    assert count == 0

    result = await test_db.execute(select(Mention))
    assert result.scalars().all() == []


async def test_relevance_score_is_calculated_and_saved(test_db: AsyncSession) -> None:
    """The relevance_score on the inserted Mention reflects the scorer output.

    Base submission: keyword in title (+40), engagement=50 > 20 (+10),
    created <24h (+10) → expected score = 60.
    """
    brand_id = str(uuid.uuid4())

    with (
        patch(
            "app.tasks.reddit_crawler.asyncio.to_thread",
            new=AsyncMock(return_value=[_submission()]),
        ),
        patch(
            "app.tasks.reddit_crawler.is_duplicate",
            new=AsyncMock(return_value=False),
        ),
    ):
        await crawl_keyword(_KEYWORD, brand_id, test_db)

    result = await test_db.execute(select(Mention))
    mention = result.scalars().one()
    assert mention.relevance_score == 60


async def test_praw_error_propagates_and_inserts_nothing(test_db: AsyncSession) -> None:
    """If PRAW raises (simulated via asyncio.to_thread), no Mention is inserted.

    The exception propagates out of ``crawl_keyword``; the Celery retry
    decorator on the task wrapper handles retries at that layer.
    """
    brand_id = str(uuid.uuid4())

    with (
        patch(
            "app.tasks.reddit_crawler.asyncio.to_thread",
            new=AsyncMock(side_effect=RuntimeError("PRAW connection refused")),
        ),
        pytest.raises(RuntimeError, match="PRAW connection refused"),
    ):
        await crawl_keyword(_KEYWORD, brand_id, test_db)

    # Nothing should have been flushed to the DB
    result = await test_db.execute(select(Mention))
    assert result.scalars().all() == []
