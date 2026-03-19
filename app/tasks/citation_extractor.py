"""Persist URLs that an LLM cited in its response as CitationSource rows.

Only called when the response parser finds at least one URL, so callers
should guard with ``if parsed["cited_urls"]`` before invoking.
"""

import logging
import uuid
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.citation_source import CitationSource

logger = logging.getLogger(__name__)


def _extract_domain(url: str) -> str:
    """Return the netloc of *url*, falling back to the raw string on parse failure.

    Args:
        url: A full URL string, e.g. ``"https://example.com/page"``.

    Returns:
        Domain string, e.g. ``"example.com"``.
    """
    try:
        netloc = urlparse(url).netloc
        return netloc if netloc else url
    except ValueError:
        return url


async def extract_citations(
    brand_id: str,
    model: str,
    query_id: str | None,
    urls: list[str],
    db: AsyncSession,
) -> None:
    """Insert a CitationSource row for each URL in *urls*.

    Silently skips blank URL strings.  Does not deduplicate within a single
    call — deduplication happens at query time in the visibility dashboard.

    Args:
        brand_id:  UUID string of the Brand being tracked.
        model:     Model that produced the citation, e.g. ``"gpt-4o"``.
        query_id:  UUID string of the Query, or ``None`` if not available.
        urls:      List of URLs extracted by the response parser.
        db:        Active async SQLAlchemy session.
    """
    if not urls:
        return

    brand_uuid = uuid.UUID(brand_id)
    query_uuid = uuid.UUID(query_id) if query_id else None

    inserted = 0
    for url in urls:
        url = url.strip()
        if not url:
            continue

        citation = CitationSource(
            id=uuid.uuid4(),
            brand_id=brand_uuid,
            model=model,
            url=url,
            domain=_extract_domain(url),
            query_id=query_uuid,
        )
        db.add(citation)
        inserted += 1

    if inserted:
        await db.flush()
        logger.info(
            "extract_citations: brand_id=%s model=%s inserted=%d",
            brand_id,
            model,
            inserted,
        )
