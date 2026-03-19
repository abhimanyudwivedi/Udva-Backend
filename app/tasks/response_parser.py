"""Parse a raw LLM response into structured brand-mention data.

Thin orchestration layer around ``llm_clients.call_parser``.  The brand name
is injected into the content so the parser model has explicit context for what
it should be looking for.
"""

import logging
from typing import Any

from app.lib.llm_clients import call_parser

logger = logging.getLogger(__name__)


async def parse_response(raw_response: str, brand_name: str) -> dict[str, Any]:
    """Extract structured brand-mention data from a raw LLM response.

    Prepends the brand name to the content so the cheap parser model has
    unambiguous context.  Falls back to safe defaults (brand_mentioned=False,
    everything else None / empty) if the parser fails — the pipeline continues
    and a partial result is still written to the database.

    Args:
        raw_response: The full text response returned by one of the visibility-
            tracking LLMs (GPT-4o, Claude, Gemini).
        brand_name:   The brand being tracked, e.g. ``"Udva"``.

    Returns:
        Dict with keys:
            ``brand_mentioned`` (bool),
            ``mention_rank``    (int | None),
            ``sentiment``       (str | None),
            ``cited_urls``      (list[str]).
    """
    if not raw_response:
        logger.info("parse_response: empty raw_response for brand=%s, skipping parser", brand_name)
        return {
            "brand_mentioned": False,
            "mention_rank": None,
            "sentiment": None,
            "cited_urls": [],
        }

    # Give the parser explicit context so it knows which brand to look for.
    content = f"Brand to track: {brand_name}\n\nLLM Response:\n{raw_response}"

    parsed = await call_parser(content)

    logger.debug(
        "parse_response: brand=%s mentioned=%s rank=%s sentiment=%s urls=%d",
        brand_name,
        parsed.get("brand_mentioned"),
        parsed.get("mention_rank"),
        parsed.get("sentiment"),
        len(parsed.get("cited_urls", [])),
    )

    return parsed
