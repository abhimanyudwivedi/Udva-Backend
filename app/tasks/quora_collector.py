"""Pillar 2 — Quora mention collector via Google SERP.

Quora does not expose a public API, so we find Quora threads through Google
using Serper.dev with the ``site:quora.com`` operator.  Each result is
treated as a potential mention — it already has a Google rank, which feeds
directly into the relevance score without a separate SERP round-trip.

Public async API
----------------
``collect_quora``          — search for one keyword and persist new mentions.

Celery tasks
------------
``collect_quora_keywords`` — load active Quora keywords for a brand and
                             call ``collect_quora`` for each.
"""

import asyncio
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.lib.serper_client import search_google
from app.models.keyword import Keyword
from app.models.mention import Mention
from app.tasks.deduplicator import is_duplicate, make_url_hash
from app.tasks.relevance_scorer import score_mention

logger = logging.getLogger(__name__)


async def collect_quora(
    keyword: str,
    brand_id: str,
    db: AsyncSession,
    keyword_id: str | None = None,
) -> int:
    """Search Google for Quora threads matching *keyword* and persist new ones.

    Uses ``site:quora.com <keyword>`` as the search query.  Quora results
    from Serper already carry a ``position`` (Google rank), so no separate
    SERP round-trip is needed — the rank is set at insert time.

    ``engagement`` is 0 for Quora results because Serper does not expose
    Quora's upvote counts.  ``created_at`` is ``None`` for the same reason,
    so recency points are not awarded.

    Args:
        keyword:    The keyword string to search for.
        brand_id:   UUID string of the brand being tracked.
        db:         Active async SQLAlchemy session (caller owns the commit).
        keyword_id: Optional UUID string of the ``Keyword`` row; stored on the
                    ``Mention`` for backlink to the triggering keyword.

    Returns:
        Number of new mentions inserted in this call.
    """
    quora_query = f"site:quora.com {keyword}"
    results = await search_google(quora_query, num=10)

    if not results:
        logger.info(
            "quora_collector: keyword=%r brand_id=%s — no Serper results",
            keyword,
            brand_id,
        )
        return 0

    inserted = 0

    for result in results:
        url: str = result["link"]

        if not url:
            continue

        # Skip URLs that don't point to quora.com (defensive — Serper may
        # occasionally include non-Quora results with a site: query)
        if "quora.com" not in url:
            logger.debug("quora_collector: skipping non-Quora URL %s", url)
            continue

        if await is_duplicate(url, brand_id, db):
            continue

        mention_dict: dict[str, Any] = {
            "title": result["title"],
            "content_snippet": result["snippet"],
            "google_rank": result["position"],
            "engagement": 0,    # not available from Google SERP
            "created_at": None,  # not available from Google SERP
        }

        relevance = score_mention(mention_dict, keyword)

        mention = Mention(
            id=uuid.uuid4(),
            brand_id=uuid.UUID(brand_id),
            keyword_id=uuid.UUID(keyword_id) if keyword_id else None,
            platform="quora",
            url=url,
            title=result["title"],
            content_snippet=result["snippet"],
            author=None,  # not available from Google SERP
            engagement=0,
            google_rank=result["position"],
            relevance_score=relevance,
            url_hash=make_url_hash(url, brand_id),
        )
        db.add(mention)
        await db.flush()

        inserted += 1
        logger.debug(
            "quora_collector: inserted mention url=%s relevance=%d",
            url,
            relevance,
        )

    logger.info(
        "quora_collector: keyword=%r brand_id=%s inserted=%d / fetched=%d",
        keyword,
        brand_id,
        inserted,
        len(results),
    )
    return inserted


# ---------------------------------------------------------------------------
# Async wrapper (own session + commit boundary)
# ---------------------------------------------------------------------------


async def _collect_quora_keywords_async(brand_id: str) -> None:
    """Load active Quora keywords for *brand_id* and collect each one.

    Opens its own ``AsyncSessionLocal`` session, commits once when all
    keywords have been processed.

    Args:
        brand_id: UUID string of the brand to collect for.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Keyword).where(
                Keyword.brand_id == brand_id,
                Keyword.platform == "quora",
                Keyword.is_active.is_(True),
            )
        )
        keywords = result.scalars().all()

        if not keywords:
            logger.info(
                "collect_quora_keywords: brand_id=%s — no active Quora keywords, skipping",
                brand_id,
            )
            return

        logger.info(
            "collect_quora_keywords: brand_id=%s — collecting %d keyword(s)",
            brand_id,
            len(keywords),
        )

        total_inserted = 0
        for kw in keywords:
            count = await collect_quora(
                keyword=kw.keyword,
                brand_id=brand_id,
                db=db,
                keyword_id=str(kw.id),
            )
            total_inserted += count

        await db.commit()
        logger.info(
            "collect_quora_keywords: brand_id=%s — committed %d new mention(s)",
            brand_id,
            total_inserted,
        )


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------
from celery_app import app as celery_app  # noqa: E402


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    name="app.tasks.quora_collector.collect_quora_keywords",
)
def collect_quora_keywords(self: Any, brand_id: str) -> None:  # type: ignore[override]
    """Celery task — collect Quora mentions for all active keywords of one brand.

    Loads active ``Keyword`` rows (platform=quora), calls ``collect_quora``
    for each, and commits the results in a single transaction.  Retries up
    to 3 times with exponential backoff.

    Args:
        brand_id: UUID string of the brand to process.
    """
    logger.info("collect_quora_keywords[celery]: starting brand_id=%s", brand_id)
    asyncio.run(_collect_quora_keywords_async(brand_id))
