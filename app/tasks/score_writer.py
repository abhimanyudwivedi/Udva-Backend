"""Persist a parsed LLM response as a VisibilityScore row.

Also used by ``competitor_diff.py`` with ``is_competitor=True`` to store
competitor brand scores alongside the primary brand.
"""

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.visibility_score import VisibilityScore

logger = logging.getLogger(__name__)


async def write_score(
    query_id: str,
    brand_id: str,
    model: str,
    parsed: dict[str, Any],
    raw_response: str,
    db: AsyncSession,
    is_competitor: bool = False,
) -> None:
    """Insert a VisibilityScore row for one query × model result.

    Args:
        query_id:      UUID string of the Query that was sent to the LLM.
        brand_id:      UUID string of the Brand being tracked.
        model:         Model identifier, e.g. ``"gpt-4o"``.
        parsed:        Output of ``response_parser.parse_response`` — must
                       contain ``brand_mentioned``, ``mention_rank``,
                       ``sentiment``, and ``cited_urls``.
        raw_response:  Full text response from the LLM (stored for auditing).
        db:            Active async SQLAlchemy session.
        is_competitor: Set to ``True`` when storing a competitor brand's score.
    """
    score = VisibilityScore(
        id=uuid.uuid4(),
        query_id=uuid.UUID(query_id),
        brand_id=uuid.UUID(brand_id),
        model=model,
        brand_mentioned=bool(parsed.get("brand_mentioned", False)),
        mention_rank=parsed.get("mention_rank"),
        sentiment=parsed.get("sentiment"),
        is_competitor=is_competitor,
        raw_response=raw_response or None,
    )
    db.add(score)
    await db.flush()

    logger.info(
        "write_score: brand_id=%s model=%s mentioned=%s rank=%s",
        brand_id,
        model,
        score.brand_mentioned,
        score.mention_rank,
    )
