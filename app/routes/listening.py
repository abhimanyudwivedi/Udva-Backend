"""Pillar 2 — Social Listening API routes.

Exposes the mention feed and ad-hoc keyword search produced by the Reddit
and Quora crawlers.

All routes are scoped to a brand owned by the authenticated user.
"""

import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.lib.auth import get_current_user
from app.models.mention import Mention
from app.models.user import User
from app.routes.brands import _get_brand_or_404
from app.schemas.mention import (
    AdHocSearchRequest,
    AdHocSearchResponse,
    MentionFeedResponse,
    MentionResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# GET /brands/{brand_id}/mentions
# ---------------------------------------------------------------------------


@router.get(
    "/{brand_id}/mentions",
    response_model=MentionFeedResponse,
    summary="Paginated mention feed",
)
async def list_mentions(
    brand_id: uuid.UUID,
    platform: str | None = Query(default=None, description="Filter by platform: reddit | quora"),
    min_score: int | None = Query(default=None, ge=0, le=100, description="Minimum relevance_score"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MentionFeedResponse:
    """Return a paginated feed of social mentions for a brand.

    Results are sorted by ``relevance_score`` descending, then ``found_at``
    descending — highest-relevance, most-recent mentions appear first.

    Args:
        brand_id:   Brand to load mentions for.
        platform:   Optional filter: ``"reddit"`` or ``"quora"``.
        min_score:  Optional minimum relevance_score (0–100).
        page:       1-based page number.
        limit:      Results per page (max 100).

    Raises:
        HTTPException 404: Brand not found or belongs to another user.
    """
    brand = await _get_brand_or_404(brand_id, current_user, db)

    filters = [Mention.brand_id == brand.id]
    if platform is not None:
        filters.append(Mention.platform == platform)
    if min_score is not None:
        filters.append(Mention.relevance_score >= min_score)

    offset = (page - 1) * limit

    total_result = await db.execute(
        select(func.count()).select_from(Mention).where(*filters)
    )
    total: int = total_result.scalar_one()

    mentions_result = await db.execute(
        select(Mention)
        .where(*filters)
        .order_by(Mention.relevance_score.desc(), Mention.found_at.desc())
        .offset(offset)
        .limit(limit)
    )
    mentions = mentions_result.scalars().all()

    return MentionFeedResponse(
        items=[MentionResponse.model_validate(m) for m in mentions],
        total=total,
        page=page,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# POST /brands/{brand_id}/mentions/search
# ---------------------------------------------------------------------------


@router.post(
    "/{brand_id}/mentions/search",
    response_model=AdHocSearchResponse,
    summary="Ad-hoc keyword search",
)
async def search_mentions(
    brand_id: uuid.UUID,
    body: AdHocSearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdHocSearchResponse:
    """Trigger an immediate crawl for a single keyword and return new results.

    Calls the appropriate crawler synchronously (Reddit via PRAW,
    Quora via Serper.dev), deduplicates against stored mentions, and
    persists any new results.  Returns only the newly inserted mentions
    from this request.

    Note: Reddit crawls can take a few seconds as they call the Reddit API.
    Quora crawls are faster (Serper.dev HTTP call).

    Args:
        brand_id: Brand to search for.
        body:     ``{keyword, platform}`` — keyword and platform to search.

    Raises:
        HTTPException 404: Brand not found or belongs to another user.
    """
    brand = await _get_brand_or_404(brand_id, current_user, db)
    brand_id_str = str(brand.id)

    start_time = datetime.now(timezone.utc)

    if body.platform == "reddit":
        from app.tasks.reddit_crawler import crawl_keyword

        inserted = await crawl_keyword(
            keyword=body.keyword,
            brand_id=brand_id_str,
            db=db,
        )
    else:  # quora
        from app.tasks.quora_collector import collect_quora

        inserted = await collect_quora(
            keyword=body.keyword,
            brand_id=brand_id_str,
            db=db,
        )

    await db.commit()

    # Return the mentions that were just inserted
    new_result = await db.execute(
        select(Mention)
        .where(
            Mention.brand_id == brand.id,
            Mention.found_at >= start_time,
        )
        .order_by(Mention.relevance_score.desc())
    )
    new_mentions = new_result.scalars().all()

    logger.info(
        "listening/search: brand_id=%s keyword=%r platform=%s inserted=%d",
        brand_id_str,
        body.keyword,
        body.platform,
        inserted,
    )

    return AdHocSearchResponse(
        keyword=body.keyword,
        platform=body.platform,
        inserted=inserted,
        items=[MentionResponse.model_validate(m) for m in new_mentions],
    )
