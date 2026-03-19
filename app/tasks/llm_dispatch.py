"""Pillar 1 — LLM fan-out, full pipeline orchestration, and Celery task entry points.

Public async API
----------------
``dispatch_to_llms``    — fan-out one prompt to all requested models in parallel.

Celery tasks
------------
``run_brand_visibility``  — full pipeline for a single brand (beat-scheduled daily).
``run_all_active_brands`` — fan-out entry point; fires one task per active brand.
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.lib.llm_clients import call_claude, call_gemini, call_openai
from app.tasks.citation_extractor import extract_citations
from app.tasks.query_builder import build_queries
from app.tasks.response_parser import parse_response
from app.tasks.score_writer import write_score

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported models
# ---------------------------------------------------------------------------
# Intentionally NOT a module-level dict of {name: function_ref} — keeping the
# mapping as strings lets test patches on the module-level names take effect
# (a module-level dict captures the original reference at import time and is
# immune to later patch() calls on the individual names).
DEFAULT_MODELS: list[str] = ["gpt-4o", "claude-sonnet-4-6", "gemini-2.5-flash"]

_MODEL_ATTR: dict[str, str] = {
    "gpt-4o": "call_openai",
    "claude-sonnet-4-6": "call_claude",
    "gemini-2.5-flash": "call_gemini",
}


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------


async def dispatch_to_llms(
    prompt: str,
    models: list[str] | None = None,
) -> list[dict[str, str]]:
    """Fan-out *prompt* to all *models* in parallel and return their responses.

    Uses ``asyncio.gather(return_exceptions=True)`` so a failure in one model
    never cancels the others.  Models that return an empty string (indicating
    an error inside ``llm_clients``) are filtered out of the result — callers
    always receive only non-empty responses.

    Args:
        prompt: The user-facing prompt to send to each LLM.
        models: List of model identifier strings to call.  Defaults to all
                three: ``["gpt-4o", "claude-sonnet-4-6", "gemini-2.5-flash"]``.

    Returns:
        List of dicts: ``[{"model": "<name>", "raw_response": "<text>"}, ...]``.
        May be empty if all models fail.
    """
    if models is None:
        models = DEFAULT_MODELS

    # Look up callers from the module namespace at call time (not at import
    # time) so that unittest.mock.patch() on the individual names takes effect.
    import sys as _sys
    _mod = _sys.modules[__name__]

    valid: list[tuple[str, Callable[[str], Coroutine[Any, Any, str]]]] = []
    for name in models:
        attr = _MODEL_ATTR.get(name)
        if attr is None:
            logger.warning("dispatch_to_llms: unknown model %r — skipping", name)
        else:
            valid.append((name, getattr(_mod, attr)))

    if not valid:
        logger.error("dispatch_to_llms: no valid models in %r", models)
        return []

    model_names, callers = zip(*valid)

    raw_results: tuple[str | BaseException, ...] = await asyncio.gather(
        *[caller(prompt) for caller in callers],
        return_exceptions=True,
    )

    output: list[dict[str, str]] = []
    for model_name, result in zip(model_names, raw_results):
        if isinstance(result, BaseException):
            # llm_clients already catches SDK errors and returns ""; this
            # guard handles any unexpected exception that slips through.
            logger.error(
                "dispatch_to_llms: unhandled exception from model=%s: %s",
                model_name,
                result,
            )
            continue
        if not result:
            logger.warning("dispatch_to_llms: model=%s returned empty response", model_name)
            continue
        output.append({"model": model_name, "raw_response": result})

    logger.info(
        "dispatch_to_llms: prompt_len=%d requested=%d succeeded=%d",
        len(prompt),
        len(valid),
        len(output),
    )
    return output


async def _run_brand_visibility_async(brand_id: str) -> None:
    """Execute the full Pillar 1 pipeline for a single brand.

    Opens its own DB session (independent of FastAPI's ``get_db``) so it can
    run inside a Celery worker process.  One session covers the entire brand
    run and is committed once at the end.

    Pipeline per active query:
        build_queries → dispatch_to_llms → parse_response
            → write_score + extract_citations

    Args:
        brand_id: UUID string of the brand to process.
    """
    async with AsyncSessionLocal() as db:
        queries = await build_queries(brand_id, db)

        if not queries:
            logger.info("run_brand_visibility: brand_id=%s — no queries, nothing to do", brand_id)
            return

        logger.info(
            "run_brand_visibility: brand_id=%s processing %d queries",
            brand_id,
            len(queries),
        )

        for query in queries:
            query_id: str = query["query_id"]
            brand_name: str = query["brand_name"]
            prompt: str = query["prompt_text"]

            dispatches = await dispatch_to_llms(prompt)

            for dispatch in dispatches:
                model: str = dispatch["model"]
                raw: str = dispatch["raw_response"]

                parsed = await parse_response(raw, brand_name)

                await write_score(
                    query_id=query_id,
                    brand_id=brand_id,
                    model=model,
                    parsed=parsed,
                    raw_response=raw,
                    db=db,
                )

                cited_urls: list[str] = parsed.get("cited_urls") or []
                if cited_urls:
                    await extract_citations(
                        brand_id=brand_id,
                        model=model,
                        query_id=query_id,
                        urls=cited_urls,
                        db=db,
                    )

        await db.commit()
        logger.info("run_brand_visibility: brand_id=%s — committed", brand_id)


async def _run_all_active_brands_async() -> None:
    """Query all active brands and enqueue a ``run_brand_visibility`` task for each.

    Runs inside the beat-scheduled Celery task.  Uses a short-lived DB session
    only to fetch brand IDs — the actual work is done by individual tasks.
    """
    from app.models.brand import Brand  # local import avoids circular imports at module load

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Brand.id).where(Brand.is_active.is_(True)))
        brand_ids: list[str] = [str(row) for row in result.scalars().all()]

    logger.info("run_all_active_brands: dispatching %d brands", len(brand_ids))

    for brand_id in brand_ids:
        run_brand_visibility.delay(brand_id)
        # Competitor diff runs after visibility so both sets of scores land on
        # the same day.  Uses send_task to avoid a circular import.
        celery_app.send_task(
            "app.tasks.competitor_diff.run_competitor_diff_task",
            args=[brand_id],
        )


# ---------------------------------------------------------------------------
# Celery tasks
# ---------------------------------------------------------------------------
# Import here (after async helpers are defined) to avoid circular imports.
from celery_app import app as celery_app  # noqa: E402


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    name="app.tasks.llm_dispatch.run_brand_visibility",
)
def run_brand_visibility(self: Any, brand_id: str) -> None:
    """Celery task — run the full Pillar 1 visibility pipeline for one brand.

    Entry point for per-brand daily LLM querying.  Fired individually by
    ``run_all_active_brands``.  Retries up to 3 times with exponential backoff
    on any unhandled exception.

    Args:
        brand_id: UUID string of the brand to process.
    """
    logger.info("run_brand_visibility[celery]: starting brand_id=%s", brand_id)
    asyncio.run(_run_brand_visibility_async(brand_id))


@celery_app.task(
    name="app.tasks.llm_dispatch.run_all_active_brands",
)
def run_all_active_brands() -> None:
    """Celery task — fan-out entry point called by Celery Beat at 6AM UTC.

    Queries all active brands and fires one ``run_brand_visibility`` task per
    brand.  Intentionally lightweight — no LLM calls happen here.
    """
    logger.info("run_all_active_brands[celery]: enqueuing brand visibility tasks")
    asyncio.run(_run_all_active_brands_async())
