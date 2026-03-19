"""Pillar 1 — AI Visibility Tracker API routes.

Exposes the time-series scores, brand vs competitor comparison, and top
cited domains produced by the daily LLM pipeline.

All routes are scoped to a brand owned by the authenticated user.
Ownership is verified via ``_get_brand_or_404`` (returns 404 for both
"not found" and "belongs to another user").
"""

import uuid
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.lib.auth import get_current_user
from app.models.citation_source import CitationSource
from app.models.user import User
from app.models.visibility_score import VisibilityScore
from app.routes.brands import _get_brand_or_404
from app.schemas.visibility import (
    CitationsResponse,
    CompareDataPoint,
    CompareResponse,
    CompetitorMentionRate,
    TopCitationDomain,
    VisibilityTrendPoint,
    VisibilityTrendResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_PERIOD_DAYS = 30


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _thirty_days_ago() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=_PERIOD_DAYS)


def _parse_competitor_model(model: str) -> tuple[str, str] | None:
    """Extract (competitor_name, base_model) from ``"competitor:{name}:{model}"``.

    Returns ``None`` if the string does not follow the expected format.
    """
    parts = model.split(":", 2)
    if len(parts) == 3 and parts[0] == "competitor":
        return parts[1], parts[2]
    return None


def _aggregate_scores(
    scores: list[VisibilityScore],
) -> dict[tuple[Any, str], dict[str, Any]]:
    """Group scores by (date, model) and compute mention rate + avg rank."""
    grouped: dict[tuple[Any, str], dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "mentioned": 0, "ranks": []}
    )
    for s in scores:
        key = (s.scored_at.date(), s.model)
        grouped[key]["total"] += 1
        if s.brand_mentioned:
            grouped[key]["mentioned"] += 1
        if s.mention_rank is not None:
            grouped[key]["ranks"].append(s.mention_rank)
    return grouped


# ---------------------------------------------------------------------------
# GET /brands/{brand_id}/visibility
# ---------------------------------------------------------------------------


@router.get(
    "/{brand_id}/visibility",
    response_model=VisibilityTrendResponse,
    summary="30-day visibility trend",
)
async def get_visibility_trend(
    brand_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VisibilityTrendResponse:
    """Return last 30 days of AI visibility scores grouped by model and date.

    Only includes primary brand scores (``is_competitor=False``).

    Raises:
        HTTPException 404: Brand not found or belongs to another user.
    """
    brand = await _get_brand_or_404(brand_id, current_user, db)

    result = await db.execute(
        select(VisibilityScore)
        .where(
            VisibilityScore.brand_id == brand.id,
            VisibilityScore.is_competitor.is_(False),
            VisibilityScore.scored_at >= _thirty_days_ago(),
        )
        .order_by(VisibilityScore.scored_at.desc())
    )
    scores = result.scalars().all()

    grouped = _aggregate_scores(scores)

    data: list[VisibilityTrendPoint] = []
    for (score_date, model), agg in sorted(grouped.items(), key=lambda x: x[0][0], reverse=True):
        mention_rate = agg["mentioned"] / agg["total"] if agg["total"] > 0 else 0.0
        avg_rank = sum(agg["ranks"]) / len(agg["ranks"]) if agg["ranks"] else None
        data.append(
            VisibilityTrendPoint(
                date=score_date,
                model=model,
                total_queries=agg["total"],
                mentioned_count=agg["mentioned"],
                mention_rate=round(mention_rate, 4),
                avg_mention_rank=round(avg_rank, 2) if avg_rank is not None else None,
            )
        )

    return VisibilityTrendResponse(
        brand_id=brand.id,
        period_days=_PERIOD_DAYS,
        data=data,
    )


# ---------------------------------------------------------------------------
# GET /brands/{brand_id}/visibility/compare
# ---------------------------------------------------------------------------


@router.get(
    "/{brand_id}/visibility/compare",
    response_model=CompareResponse,
    summary="Brand vs competitors visibility",
)
async def get_visibility_compare(
    brand_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CompareResponse:
    """Return brand mention rates alongside each competitor's for the last 30 days.

    Brand scores are aggregated by ``model``.  Competitor scores are stored
    with ``model = "competitor:{name}:{base_model}"`` and are parsed here to
    reconstruct per-model comparisons.

    Raises:
        HTTPException 404: Brand not found or belongs to another user.
    """
    brand = await _get_brand_or_404(brand_id, current_user, db)
    cutoff = _thirty_days_ago()

    # Load all scores (brand + competitors) in one query
    result = await db.execute(
        select(VisibilityScore)
        .where(
            VisibilityScore.brand_id == brand.id,
            VisibilityScore.scored_at >= cutoff,
        )
    )
    all_scores = result.scalars().all()

    # Separate and aggregate brand scores by base model
    brand_agg: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "mentioned": 0, "ranks": []}
    )
    # competitor_agg[base_model][competitor_name] = {total, mentioned, ranks}
    competitor_agg: dict[str, dict[str, dict[str, Any]]] = defaultdict(
        lambda: defaultdict(lambda: {"total": 0, "mentioned": 0, "ranks": []})
    )

    for s in all_scores:
        if not s.is_competitor:
            agg = brand_agg[s.model]
            agg["total"] += 1
            if s.brand_mentioned:
                agg["mentioned"] += 1
            if s.mention_rank is not None:
                agg["ranks"].append(s.mention_rank)
        else:
            parsed = _parse_competitor_model(s.model)
            if parsed is None:
                logger.warning("visibility/compare: unrecognised model format %r", s.model)
                continue
            competitor_name, base_model = parsed
            agg = competitor_agg[base_model][competitor_name]
            agg["total"] += 1
            if s.brand_mentioned:
                agg["mentioned"] += 1
            if s.mention_rank is not None:
                agg["ranks"].append(s.mention_rank)

    # Build response — one CompareDataPoint per base model
    all_models = sorted(set(brand_agg.keys()) | set(competitor_agg.keys()))
    data: list[CompareDataPoint] = []

    for model in all_models:
        b = brand_agg.get(model, {"total": 0, "mentioned": 0, "ranks": []})
        b_rate = b["mentioned"] / b["total"] if b["total"] > 0 else 0.0
        b_avg_rank = sum(b["ranks"]) / len(b["ranks"]) if b["ranks"] else None

        competitors: list[CompetitorMentionRate] = []
        for comp_name, c in sorted(competitor_agg.get(model, {}).items()):
            c_rate = c["mentioned"] / c["total"] if c["total"] > 0 else 0.0
            c_avg_rank = sum(c["ranks"]) / len(c["ranks"]) if c["ranks"] else None
            competitors.append(
                CompetitorMentionRate(
                    name=comp_name,
                    mention_rate=round(c_rate, 4),
                    avg_mention_rank=round(c_avg_rank, 2) if c_avg_rank is not None else None,
                )
            )

        data.append(
            CompareDataPoint(
                model=model,
                brand_mention_rate=round(b_rate, 4),
                brand_avg_mention_rank=round(b_avg_rank, 2) if b_avg_rank is not None else None,
                competitors=competitors,
            )
        )

    return CompareResponse(
        brand_id=brand.id,
        brand_name=brand.name,
        period_days=_PERIOD_DAYS,
        data=data,
    )


# ---------------------------------------------------------------------------
# GET /brands/{brand_id}/visibility/citations
# ---------------------------------------------------------------------------


@router.get(
    "/{brand_id}/visibility/citations",
    response_model=CitationsResponse,
    summary="Top cited domains",
)
async def get_visibility_citations(
    brand_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CitationsResponse:
    """Return the top domains cited by LLMs for this brand in the last 30 days.

    Results are aggregated by domain and sorted by citation frequency
    (most-cited first), limited to 20 domains.

    Raises:
        HTTPException 404: Brand not found or belongs to another user.
    """
    brand = await _get_brand_or_404(brand_id, current_user, db)

    result = await db.execute(
        select(
            CitationSource.domain,
            func.count().label("citation_count"),
            func.max(CitationSource.found_at).label("last_seen"),
        )
        .where(
            CitationSource.brand_id == brand.id,
            CitationSource.found_at >= _thirty_days_ago(),
        )
        .group_by(CitationSource.domain)
        .order_by(func.count().desc())
        .limit(20)
    )
    rows = result.all()

    domains = [
        TopCitationDomain(
            domain=row.domain,
            citation_count=row.citation_count,
            last_seen=row.last_seen,
        )
        for row in rows
    ]

    return CitationsResponse(
        brand_id=brand.id,
        period_days=_PERIOD_DAYS,
        domains=domains,
    )
