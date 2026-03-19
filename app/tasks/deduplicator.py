"""Mention deduplication — prevent storing the same URL × brand pair twice.

The ``url_hash`` column on ``mentions`` has a UNIQUE constraint, but we check
before inserting to avoid wasted work (scoring, DB round-trip) on duplicates.
"""

import hashlib
import logging

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mention import Mention

logger = logging.getLogger(__name__)


def make_url_hash(url: str, brand_id: str) -> str:
    """Return the MD5 hex digest of ``"{url}:{brand_id}"``.

    The hash is stored in ``mentions.url_hash`` and used as a fast dedup key.
    MD5 is intentionally used here — this is a dedup fingerprint, not a
    security hash, so speed matters more than collision-resistance.

    Args:
        url:      The canonical URL of the social post.
        brand_id: UUID string of the brand being tracked.

    Returns:
        32-character lowercase hexadecimal MD5 digest.
    """
    raw = f"{url}:{brand_id}".encode()
    return hashlib.md5(raw).hexdigest()


async def is_duplicate(url: str, brand_id: str, db: AsyncSession) -> bool:
    """Return ``True`` if a mention with this URL × brand combination already exists.

    Queries the ``mentions`` table by ``url_hash`` rather than the full URL,
    matching how rows are inserted.

    Args:
        url:      The URL to check.
        brand_id: UUID string of the brand being tracked.
        db:       Active async SQLAlchemy session.

    Returns:
        ``True`` if the mention already exists in the database.
    """
    url_hash = make_url_hash(url, brand_id)
    result = await db.scalar(
        select(exists().where(Mention.url_hash == url_hash))
    )
    is_dupe = bool(result)

    if is_dupe:
        logger.debug("deduplicator: duplicate url_hash=%s brand_id=%s", url_hash, brand_id)

    return is_dupe
