"""Pillar 1 — Competitor differential scoring.

For each brand, runs the same tracked prompts against every competitor brand
name and stores the results as VisibilityScore rows with ``is_competitor=True``.
The ``model`` field encodes competitor identity as
``f"competitor:{competitor.name}:{model}"`` so the dashboard can filter and
compare scores without any schema changes.

Public async API
----------------
``run_competitor_diff``      — process all competitors for one brand.

Celery task
-----------
``run_competitor_diff_task`` — thin sync wrapper; called after
                               ``run_brand_visibility`` in the daily beat run.
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.competitor import Competitor
from app.models.query import Query as QueryModel
from app.tasks.llm_dispatch import dispatch_to_llms
from app.tasks.response_parser import parse_response
from app.tasks.score_writer import write_score

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Async pipeline
# ---------------------------------------------------------------------------


async def run_competitor_diff(brand_id: str, db: AsyncSession) -> None:
    """Run visibility tracking for every competitor of *brand_id*.

    For each competitor × active-query pair:
        1. Replace brand name in the prompt with the competitor name.
        2. Fan-out to all three LLMs via ``dispatch_to_llms``.
        3. Parse each response with ``parse_response``.
        4. Persist via ``write_score`` with ``is_competitor=True`` and the
           model field set to ``f"competitor:{competitor.name}:{base_model}"``.

    The caller is responsible for committing the session after this function
    returns (following the same pattern as the main visibility pipeline).

    Args:
        brand_id: UUID string of the brand whose competitors should be scored.
        db:       Active async SQLAlchemy session (caller owns the commit).
    """
    # Load competitors
    competitors_result = await db.execute(
        select(Competitor).where(Competitor.brand_id == brand_id)
    )
    competitors = competitors_result.scalars().all()

    if not competitors:
        logger.info(
            "run_competitor_diff: brand_id=%s — no competitors configured, skipping",
            brand_id,
        )
        return

    # Load active queries
    queries_result = await db.execute(
        select(QueryModel).where(
            QueryModel.brand_id == brand_id,
            QueryModel.is_active.is_(True),
        )
    )
    queries = queries_result.scalars().all()

    if not queries:
        logger.info(
            "run_competitor_diff: brand_id=%s — no active queries, skipping",
            brand_id,
        )
        return

    logger.info(
        "run_competitor_diff: brand_id=%s — %d competitors × %d queries",
        brand_id,
        len(competitors),
        len(queries),
    )

    for competitor in competitors:
        for query in queries:
            # Substitute competitor name into the prompt so the LLM evaluates
            # that brand instead of the user's brand.
            competitor_prompt = query.prompt_text.replace(
                query.prompt_text,  # replace full prompt (competitor context sent as-is)
                f"Evaluate the following as if the brand being assessed is "
                f'"{competitor.name}": {query.prompt_text}',
            )

            dispatches = await dispatch_to_llms(competitor_prompt)

            for dispatch in dispatches:
                base_model: str = dispatch["model"]
                raw: str = dispatch["raw_response"]

                parsed = await parse_response(raw, competitor.name)

                # Encode competitor identity in the model field so dashboard
                # queries can filter by competitor without schema changes.
                competitor_model = f"competitor:{competitor.name}:{base_model}"

                await write_score(
                    query_id=str(query.id),
                    brand_id=brand_id,
                    model=competitor_model,
                    parsed=parsed,
                    raw_response=raw,
                    db=db,
                    is_competitor=True,
                )

    logger.info(
        "run_competitor_diff: brand_id=%s — all competitor scores written (pending commit)",
        brand_id,
    )


async def _run_competitor_diff_async(brand_id: str) -> None:
    """Open a DB session, run the competitor diff pipeline, and commit.

    Mirrors ``_run_brand_visibility_async`` from ``llm_dispatch``: manages its
    own ``AsyncSessionLocal`` so it can run inside a Celery worker process.

    Args:
        brand_id: UUID string of the brand to process.
    """
    async with AsyncSessionLocal() as db:
        await run_competitor_diff(brand_id, db)
        await db.commit()
        logger.info("run_competitor_diff_task: brand_id=%s — committed", brand_id)


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------
# Import after async helpers to avoid circular imports.
from celery_app import app as celery_app  # noqa: E402


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    name="app.tasks.competitor_diff.run_competitor_diff_task",
)
def run_competitor_diff_task(self, brand_id: str) -> None:  # type: ignore[override]
    """Celery task — run competitor differential scoring for one brand.

    Wraps ``_run_competitor_diff_async`` with ``asyncio.run()`` so it can
    execute inside a synchronous Celery worker.  Called by
    ``run_all_active_brands`` immediately after ``run_brand_visibility``.

    Args:
        brand_id: UUID string of the brand to process.
    """
    logger.info("run_competitor_diff_task[celery]: starting brand_id=%s", brand_id)
    asyncio.run(_run_competitor_diff_async(brand_id))
