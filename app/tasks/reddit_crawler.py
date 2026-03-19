"""Pillar 2 — Reddit keyword crawler.

Searches Reddit for keyword mentions, deduplicates against stored mentions,
scores each result, and persists new mentions to the database.

Public async API
----------------
``crawl_keyword``       — search r/all for one keyword and persist new mentions.

Celery tasks
------------
``crawl_brand_keywords``  — load active Reddit keywords for a brand and crawl each.
``crawl_active_brands``   — beat entry point; fans out to ``crawl_brand_keywords``
                            for all active brands on the requested plan tiers.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import praw.models
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.lib.reddit_client import get_reddit_client
from app.models.keyword import Keyword
from app.models.mention import Mention
from app.tasks.deduplicator import is_duplicate, make_url_hash
from app.tasks.relevance_scorer import score_mention

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PRAW helpers (sync — run in thread pool via asyncio.to_thread)
# ---------------------------------------------------------------------------

_SEARCH_LIMIT = 25
_TIME_FILTER = "week"


def _fetch_submissions(keyword: str) -> list[dict[str, Any]]:
    """Search r/all for *keyword* and return raw mention dicts.

    Runs synchronously (PRAW is not async).  Call via ``asyncio.to_thread``.

    Returns:
        List of mention dicts with keys: url, title, content_snippet, author,
        engagement, google_rank (always None — filled later by serp_ranker),
        created_at.
    """
    reddit = get_reddit_client()
    submissions = reddit.subreddit("all").search(
        keyword,
        sort="new",
        time_filter=_TIME_FILTER,
        limit=_SEARCH_LIMIT,
    )

    results: list[dict[str, Any]] = []
    for s in submissions:
        author_name: str | None = None
        try:
            author_name = s.author.name if s.author else None
        except Exception:
            pass  # deleted / suspended accounts raise AttributeError

        results.append(
            {
                "url": f"https://www.reddit.com{s.permalink}",
                "title": s.title,
                "content_snippet": s.selftext[:500] if s.selftext else None,
                "author": author_name,
                "engagement": s.score,
                "google_rank": None,  # serp_ranker fills this in a later step
                "created_at": datetime.fromtimestamp(s.created_utc, tz=timezone.utc),
            }
        )

    logger.info(
        "reddit_crawler: keyword=%r fetched %d submissions from PRAW",
        keyword,
        len(results),
    )
    return results


# ---------------------------------------------------------------------------
# Async pipeline
# ---------------------------------------------------------------------------


async def crawl_keyword(
    keyword: str,
    brand_id: str,
    db: AsyncSession,
    keyword_id: str | None = None,
) -> int:
    """Search Reddit for *keyword* and insert new, non-duplicate mentions.

    Args:
        keyword:    The keyword string to search for.
        brand_id:   UUID string of the brand being tracked.
        db:         Active async SQLAlchemy session (caller owns the commit).
        keyword_id: Optional UUID string of the ``Keyword`` row; stored on the
                    ``Mention`` for backlink to the triggering keyword.

    Returns:
        Number of new mentions inserted in this call.
    """
    # Fetch submissions in a thread to avoid blocking the event loop
    submissions = await asyncio.to_thread(_fetch_submissions, keyword)

    inserted = 0

    for item in submissions:
        url: str = item["url"]

        # Skip if we already have this URL × brand combination
        if await is_duplicate(url, brand_id, db):
            continue

        relevance = score_mention(item, keyword)

        mention = Mention(
            id=uuid.uuid4(),
            brand_id=uuid.UUID(brand_id),
            keyword_id=uuid.UUID(keyword_id) if keyword_id else None,
            platform="reddit",
            url=url,
            title=item["title"],
            content_snippet=item["content_snippet"],
            author=item["author"],
            engagement=item["engagement"],
            google_rank=item["google_rank"],
            relevance_score=relevance,
            url_hash=make_url_hash(url, brand_id),
        )
        db.add(mention)
        await db.flush()  # write to DB; caller commits after all keywords

        inserted += 1
        logger.debug(
            "reddit_crawler: inserted mention url=%s relevance=%d",
            url,
            relevance,
        )

    logger.info(
        "reddit_crawler: keyword=%r brand_id=%s inserted=%d / fetched=%d",
        keyword,
        brand_id,
        inserted,
        len(submissions),
    )
    return inserted


# ---------------------------------------------------------------------------
# Async wrappers (own session + commit boundary)
# ---------------------------------------------------------------------------


async def _crawl_brand_keywords_async(brand_id: str) -> None:
    """Load active Reddit keywords for *brand_id* and crawl each one.

    Opens its own ``AsyncSessionLocal`` session, commits once when all
    keywords have been processed.

    Args:
        brand_id: UUID string of the brand to crawl.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Keyword).where(
                Keyword.brand_id == brand_id,
                Keyword.platform == "reddit",
                Keyword.is_active.is_(True),
            )
        )
        keywords = result.scalars().all()

        if not keywords:
            logger.info(
                "crawl_brand_keywords: brand_id=%s — no active Reddit keywords, skipping",
                brand_id,
            )
            return

        logger.info(
            "crawl_brand_keywords: brand_id=%s — crawling %d keyword(s)",
            brand_id,
            len(keywords),
        )

        total_inserted = 0
        for kw in keywords:
            count = await crawl_keyword(
                keyword=kw.keyword,
                brand_id=brand_id,
                db=db,
                keyword_id=str(kw.id),
            )
            total_inserted += count

        await db.commit()
        logger.info(
            "crawl_brand_keywords: brand_id=%s — committed %d new mention(s)",
            brand_id,
            total_inserted,
        )


async def _crawl_active_brands_async(plan_tier: list[str] | None = None) -> None:
    """Query all active brands (optionally filtered by plan) and enqueue crawls.

    Args:
        plan_tier: If provided, only dispatch brands whose user plan is in
                   this list (e.g. ``["studio", "agency"]``).
    """
    from app.models.brand import Brand  # local import avoids circular imports
    from app.models.user import User

    async with AsyncSessionLocal() as db:
        query = select(Brand.id).join(User, Brand.user_id == User.id).where(
            Brand.is_active.is_(True)
        )
        if plan_tier:
            query = query.where(User.plan.in_(plan_tier))

        result = await db.execute(query)
        brand_ids: list[str] = [str(row) for row in result.scalars().all()]

    logger.info(
        "crawl_active_brands: plan_tier=%r dispatching %d brand(s)",
        plan_tier,
        len(brand_ids),
    )

    for brand_id in brand_ids:
        crawl_brand_keywords.delay(brand_id)


# ---------------------------------------------------------------------------
# Celery tasks
# ---------------------------------------------------------------------------
from celery_app import app as celery_app  # noqa: E402


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    name="app.tasks.reddit_crawler.crawl_brand_keywords",
)
def crawl_brand_keywords(self: Any, brand_id: str) -> None:  # type: ignore[override]
    """Celery task — crawl all active Reddit keywords for one brand.

    Loads active ``Keyword`` rows for the brand (platform=reddit), calls
    ``crawl_keyword`` for each, and commits the results in a single
    transaction.  Retries up to 3 times with exponential backoff.

    Args:
        brand_id: UUID string of the brand to process.
    """
    logger.info("crawl_brand_keywords[celery]: starting brand_id=%s", brand_id)
    asyncio.run(_crawl_brand_keywords_async(brand_id))


@celery_app.task(
    name="app.tasks.reddit_crawler.crawl_active_brands",
)
def crawl_active_brands(plan_tier: list[str] | None = None) -> None:
    """Celery task — beat entry point; fans out one crawl task per active brand.

    Called by Celery Beat on the 6-hour schedule (Studio/Agency) and 24-hour
    schedule (Solo/Indie).  The ``plan_tier`` kwarg is injected by the beat
    schedule definition in ``celery_app.py``.

    Args:
        plan_tier: List of plan slugs to include, e.g. ``["studio", "agency"]``.
                   If ``None``, all active brands are crawled.
    """
    logger.info(
        "crawl_active_brands[celery]: plan_tier=%r enqueuing brand crawl tasks",
        plan_tier,
    )
    asyncio.run(_crawl_active_brands_async(plan_tier))
