"""Pillar 1 — Weekly score rollup.

Aggregates raw ``visibility_scores`` rows into the ``visibility_weekly`` table
once per week (Monday 3AM UTC Celery beat task).

One output row per brand × model × week_start (Monday).  Metrics:
- ``total_queries``   — total rows in the week for that brand × model
- ``mentioned_count`` — rows where brand_mentioned = true
- ``mention_rate``    — mentioned_count / total_queries × 100
- ``avg_rank``        — mean of mention_rank values (NULLs excluded)

Competitor rows (``is_competitor=True``) are excluded — they are tracked
separately and have their own model name encoding.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Date, Float, case, cast, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.visibility_score import VisibilityScore
from app.models.visibility_weekly import VisibilityWeekly

logger = logging.getLogger(__name__)

_LOOKBACK_DAYS = 7  # aggregate the rolling last-7-days window


# ---------------------------------------------------------------------------
# Core async function
# ---------------------------------------------------------------------------


async def compute_weekly(db: AsyncSession) -> None:
    """Aggregate the last 7 days of visibility_scores into visibility_weekly.

    Queries ``visibility_scores`` for non-competitor rows in the last
    ``_LOOKBACK_DAYS`` days, groups by brand × model × ISO week start (Monday),
    computes aggregates, then upserts each row into ``visibility_weekly``.

    Args:
        db: Active async SQLAlchemy session (caller is responsible for commit).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=_LOOKBACK_DAYS)

    # ------------------------------------------------------------------
    # Aggregation query — all computed in PostgreSQL
    # ------------------------------------------------------------------
    week_start_expr = func.date_trunc("week", VisibilityScore.scored_at).cast(Date)

    rows = (
        await db.execute(
            select(
                VisibilityScore.brand_id,
                VisibilityScore.model,
                week_start_expr.label("week_start"),
                func.count().label("total_queries"),
                func.sum(
                    case((VisibilityScore.brand_mentioned.is_(True), 1), else_=0)
                ).label("mentioned_count"),
                cast(
                    func.avg(VisibilityScore.mention_rank),
                    Float,
                ).label("avg_rank"),
            )
            .where(
                VisibilityScore.scored_at >= cutoff,
                VisibilityScore.is_competitor.is_(False),
            )
            .group_by(
                VisibilityScore.brand_id,
                VisibilityScore.model,
                week_start_expr,
            )
        )
    ).all()

    if not rows:
        logger.info("rollup: no visibility_scores found in the last %d days — skipping", _LOOKBACK_DAYS)
        return

    logger.info("rollup: upserting %d brand×model×week aggregates", len(rows))

    # ------------------------------------------------------------------
    # Upsert each aggregated row
    # ------------------------------------------------------------------
    for row in rows:
        total: int = row.total_queries
        mentioned: int = row.mentioned_count
        mention_rate: float = (mentioned / total * 100) if total > 0 else 0.0

        stmt = (
            pg_insert(VisibilityWeekly)
            .values(
                id=uuid.uuid4(),
                brand_id=row.brand_id,
                model=row.model,
                week_start=row.week_start,
                total_queries=total,
                mentioned_count=mentioned,
                mention_rate=mention_rate,
                avg_rank=row.avg_rank,
            )
            .on_conflict_do_update(
                constraint="uq_visibility_weekly_brand_model_week",
                set_={
                    "total_queries": total,
                    "mentioned_count": mentioned,
                    "mention_rate": mention_rate,
                    "avg_rank": row.avg_rank,
                },
            )
        )
        await db.execute(stmt)

    await db.commit()
    logger.info("rollup: committed %d rows to visibility_weekly", len(rows))


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

from celery_app import app as celery_app  # noqa: E402


@celery_app.task(
    name="app.tasks.rollup.compute_weekly_task",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def compute_weekly_task(self) -> None:  # type: ignore[override]
    """Celery task entry point — called by the Monday 3AM UTC beat schedule.

    Opens its own database session (Celery workers are sync) and bridges to
    the async ``compute_weekly`` pipeline via ``asyncio.run``.
    """
    async def _run() -> None:
        async with AsyncSessionLocal() as db:
            await compute_weekly(db)

    asyncio.run(_run())
