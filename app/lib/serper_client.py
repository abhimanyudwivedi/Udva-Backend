"""Serper.dev HTTP client — Google Search API wrapper.

Used by Pillar 2 for:
  - ``search_google``    : generic Google SERP queries (Quora collection, etc.)
  - ``get_google_rank``  : check whether a specific URL appears on Google page 1

Cost reference: ~$0.30 per 1,000 queries (extremely cheap at this scale).
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_SERPER_URL = "https://google.serper.dev/search"
_TIMEOUT = 10.0  # seconds


async def search_google(query: str, num: int = 10) -> list[dict]:
    """POST a search query to Serper.dev and return the organic results.

    Args:
        query: The search query string (e.g. ``"site:quora.com udva"``).
        num:   Number of results to request (max 10 for page-1 checks).

    Returns:
        List of dicts, each containing:
          - ``title``    (str)
          - ``link``     (str)  — the result URL
          - ``snippet``  (str)  — the meta-description / excerpt
          - ``position`` (int)  — 1-based rank in the results page

        Returns an empty list on any network or API error so callers never
        need to handle exceptions from this function.
    """
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                _SERPER_URL,
                headers={"X-API-KEY": settings.SERPER_API_KEY},
                json={"q": query, "num": num},
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "serper_client: HTTP %d for query=%r — %s",
            exc.response.status_code,
            query,
            exc,
        )
        return []
    except httpx.RequestError as exc:
        logger.error("serper_client: request error for query=%r — %s", query, exc)
        return []

    raw_results: list[dict] = response.json().get("organic", [])

    results = [
        {
            "title": r.get("title", ""),
            "link": r.get("link", ""),
            "snippet": r.get("snippet", ""),
            "position": r.get("position", idx + 1),
        }
        for idx, r in enumerate(raw_results)
    ]

    logger.info(
        "serper_client: query=%r returned %d organic result(s)",
        query,
        len(results),
    )
    return results


async def get_google_rank(url: str) -> int | None:
    """Return the Google page-1 rank (1–10) for *url*, or ``None`` if not found.

    Submits *url* itself as the search query — Serper returns results that
    contain or reference the URL.  If the URL appears in a result's ``link``
    field it is considered ranked at that position.

    Args:
        url: The canonical URL to look up (e.g. a Reddit thread permalink).

    Returns:
        Integer 1–10 if the URL appears on Google page 1, else ``None``.
    """
    results = await search_google(url, num=10)

    for result in results:
        if url in result["link"]:
            rank: int = result["position"]
            logger.info("serper_client: url=%s found at rank=%d", url, rank)
            return rank

    logger.info("serper_client: url=%s not found on page 1", url)
    return None
