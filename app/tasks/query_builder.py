"""Load active LLM queries for a brand from the database.

Used at the start of the Pillar 1 daily pipeline to determine what prompts
should be sent to each LLM for a given brand.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.query import Query

logger = logging.getLogger(__name__)


async def build_queries(brand_id: str, db: AsyncSession) -> list[dict[str, str]]:
    """Return all active queries for *brand_id*, enriched with the brand name.

    Each returned dict is consumed directly by ``llm_dispatch.dispatch_to_llms``
    and ``score_writer.write_score``.

    Args:
        brand_id: UUID string of the brand to load queries for.
        db:       Active async SQLAlchemy session.

    Returns:
        List of dicts with keys ``query_id``, ``brand_name``, ``prompt_text``.
        Returns an empty list if the brand does not exist or has no active queries.
    """
    brand_uuid = uuid.UUID(brand_id)

    brand_result = await db.execute(select(Brand).where(Brand.id == brand_uuid))
    brand = brand_result.scalar_one_or_none()

    if brand is None:
        logger.warning("build_queries: brand_id=%s not found", brand_id)
        return []

    query_result = await db.execute(
        select(Query).where(Query.brand_id == brand_uuid, Query.is_active.is_(True))
    )
    queries = query_result.scalars().all()

    if not queries:
        logger.info("build_queries: brand_id=%s has no active queries", brand_id)
        return []

    return [
        {
            "query_id": str(q.id),
            "brand_name": brand.name,
            "prompt_text": q.prompt_text,
        }
        for q in queries
    ]
