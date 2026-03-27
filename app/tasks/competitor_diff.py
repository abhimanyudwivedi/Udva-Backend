"""Pillar 1 — Competitor differential scoring.

Competitor scores are derived from the SAME LLM responses used for brand
visibility — no extra LLM calls are made.  For each query × model response,
``score_competitors_from_response`` is called by ``llm_dispatch`` to parse
every competitor's mention rank from the same raw text.

This ensures:
  - Fair comparison (all brands evaluated against identical LLM output).
  - Zero extra LLM API cost for competitor tracking.
  - Accurate rank positions (brand #3 in a list of 5 is correctly rank 3,
    not rank 1 because it was "the first mention of that specific brand").

The legacy ``run_competitor_diff_task`` Celery task is kept registered but
is now a no-op.  Competitor scoring happens inline inside
``run_brand_visibility``.
"""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.competitor import Competitor
from app.tasks.response_parser import parse_response
from app.tasks.score_writer import write_score

logger = logging.getLogger(__name__)


async def score_competitors_from_response(
    raw_response: str,
    model: str,
    query_id: str,
    brand_id: str,
    competitors: list[Competitor],
    db: AsyncSession,
) -> None:
    """Parse each competitor's mention rank from an already-fetched LLM response.

    Reuses the raw text that was already retrieved during brand visibility
    scoring — no additional LLM calls are made.  Each competitor is parsed
    independently so their individual ordinal positions are extracted correctly.

    Args:
        raw_response: Raw text already returned by one of the visibility LLMs.
        model:        Model identifier, e.g. ``"gpt-4o"``.
        query_id:     UUID string of the Query that produced this response.
        brand_id:     UUID string of the brand being tracked.
        competitors:  List of Competitor ORM objects for this brand.
        db:           Active async SQLAlchemy session (caller owns the commit).
    """
    for competitor in competitors:
        parsed = await parse_response(raw_response, competitor.name)

        # Encode competitor identity in the model field — matches the format
        # expected by the visibility.py compare endpoint.
        competitor_model = f"competitor:{competitor.name}:{model}"

        await write_score(
            query_id=query_id,
            brand_id=brand_id,
            model=competitor_model,
            parsed=parsed,
            raw_response=raw_response,
            db=db,
            is_competitor=True,
        )

    logger.info(
        "score_competitors_from_response: brand_id=%s model=%s scored %d competitors",
        brand_id,
        model,
        len(competitors),
    )


# ---------------------------------------------------------------------------
# Legacy Celery task — kept registered to avoid errors from any queued tasks,
# but competitor scoring now happens inline inside run_brand_visibility.
# ---------------------------------------------------------------------------
from celery_app import app as celery_app  # noqa: E402


@celery_app.task(
    name="app.tasks.competitor_diff.run_competitor_diff_task",
)
def run_competitor_diff_task(brand_id: str) -> None:  # type: ignore[override]
    """No-op. Competitor diff is now handled inline by run_brand_visibility."""
    logger.info(
        "run_competitor_diff_task: brand_id=%s — skipped (inline scoring active)",
        brand_id,
    )
