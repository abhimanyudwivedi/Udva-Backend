"""PRAW Reddit client — lazy singleton for Pillar 2 and Pillar 3.

A single read-only ``praw.Reddit`` instance is created on first call and
reused for the lifetime of the process.  Pillar 3 (post_executor) creates
its own per-account PRAW instances directly — this singleton is for
read-only crawling only.
"""

import logging

import praw

from app.config import settings

logger = logging.getLogger(__name__)

_reddit: praw.Reddit | None = None


def get_reddit_client() -> praw.Reddit:
    """Return the shared read-only PRAW client, creating it on first call.

    Uses ``read_only=True`` because all crawling is unauthenticated.  Pillar 3
    posting tasks authenticate per-account and never use this singleton.

    Raises:
        RuntimeError: If ``REDDIT_CLIENT_ID`` or ``REDDIT_CLIENT_SECRET`` is
                      not set in the environment.

    Returns:
        A configured, reusable ``praw.Reddit`` instance.
    """
    global _reddit

    if _reddit is not None:
        return _reddit

    if not settings.REDDIT_CLIENT_ID:
        raise RuntimeError(
            "REDDIT_CLIENT_ID is not set. "
            "Add it to your .env file or Railway environment variables."
        )
    if not settings.REDDIT_CLIENT_SECRET:
        raise RuntimeError(
            "REDDIT_CLIENT_SECRET is not set. "
            "Add it to your .env file or Railway environment variables."
        )

    _reddit = praw.Reddit(
        client_id=settings.REDDIT_CLIENT_ID,
        client_secret=settings.REDDIT_CLIENT_SECRET,
        user_agent=settings.REDDIT_USER_AGENT,
        read_only=True,
    )

    logger.info(
        "reddit_client: initialised (user_agent=%s, read_only=True)",
        settings.REDDIT_USER_AGENT,
    )
    return _reddit
