"""Pillar 2 — SERP rank enrichment for stored mentions.

After a mention is inserted by ``reddit_crawler`` or ``quora_collector``,
this module checks whether the post's URL appears on Google page 1 and
updates both ``google_rank`` and ``relevance_score`` on the mention row.

The recalculated score uses the updated ``google_rank`` but omits recency
(the ``Mention`` model stores ``found_at``, not the original post's
``created_at``), which is expected — recency was already factored in at
insert time.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lib.serper_client import get_google_rank
from app.models.keyword import Keyword
from app.models.mention import Mention
from app.tasks.relevance_scorer import score_mention

logger = logging.getLogger(__name__)


async def rank_mention(mention_id: str, url: str, db: AsyncSession) -> None:
    """Fetch the Google rank for *url* and update the stored mention.

    Steps:
        1. Call ``get_google_rank(url)`` — returns 1–10 or ``None``.
        2. Load the ``Mention`` row (and its related ``Keyword`` for scoring).
        3. Update ``mention.google_rank``.
        4. Recalculate ``mention.relevance_score`` using the updated rank.
        5. Flush — caller owns the commit boundary.

    The relevance score is recalculated from the stored fields (title,
    content_snippet, engagement, google_rank).  ``created_at`` is set to
    ``None`` because the original post creation time is not stored on the
    ``Mention`` row, so no recency points are added during re-scoring.

    Args:
        mention_id: UUID string of the ``Mention`` row to update.
        url:        URL to look up in Google (must match ``mention.url``).
        db:         Active async SQLAlchemy session.
    """
    rank = await get_google_rank(url)

    # Load the mention and its keyword (for score_mention's keyword arg)
    result = await db.execute(
        select(Mention, Keyword)
        .outerjoin(Keyword, Mention.keyword_id == Keyword.id)
        .where(Mention.id == uuid.UUID(mention_id))
    )
    row = result.first()

    if row is None:
        logger.warning("serp_ranker: mention_id=%s not found — skipping", mention_id)
        return

    mention, keyword_row = row

    # Apply the new rank
    mention.google_rank = rank

    # Reconstruct the mention dict for re-scoring.
    # created_at is intentionally None — not stored on the Mention model.
    mention_dict = {
        "title": mention.title,
        "content_snippet": mention.content_snippet,
        "google_rank": rank,
        "engagement": mention.engagement,
        "created_at": None,
    }
    keyword_text = keyword_row.keyword if keyword_row is not None else ""
    new_score = score_mention(mention_dict, keyword_text)

    mention.relevance_score = new_score
    await db.flush()

    logger.info(
        "serp_ranker: mention_id=%s url=%s rank=%s new_score=%d",
        mention_id,
        url,
        rank,
        new_score,
    )
