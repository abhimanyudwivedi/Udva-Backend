"""Pillar 2 — Alert dispatcher for high-relevance social mentions.

After each crawl run, ``dispatch_alerts`` is called per brand to notify the
owner of any new high-relevance mentions discovered in the last 6 hours.

Delivery channels
-----------------
- Email  : always, via Resend (``app/lib/email.py``)
- Slack  : optional; fired when the user has set ``slack_webhook_url`` in
           their account settings (``GET/PUT /settings``).

Alert threshold
---------------
Per-user; defaults to 60 if not explicitly set.  Configured via ``PUT /settings``.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lib.email import send_alert_email
from app.models.brand import Brand
from app.models.mention import Mention
from app.models.user import User

logger = logging.getLogger(__name__)

_LOOKBACK_HOURS = 6  # "new" means found in the last N hours
_SLACK_TIMEOUT = 5.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _fire_slack_webhook(
    webhook_url: str,
    brand_name: str,
    mention_title: str,
    mention_url: str,
    relevance_score: int,
) -> None:
    """POST a Slack Block Kit message to *webhook_url*.

    Swallows all errors — Slack alerts are best-effort.

    Args:
        webhook_url:     Incoming webhook URL from the user's Slack workspace.
        brand_name:      Brand being tracked.
        mention_title:   Title or URL of the mention.
        mention_url:     Direct link to the mention.
        relevance_score: Computed relevance score (0–100).
    """
    payload = {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f":bell: *New mention of {brand_name}* — score *{relevance_score}/100*\n"
                        f"<{mention_url}|{mention_title}>"
                    ),
                },
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=_SLACK_TIMEOUT) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()

        logger.info(
            "alert_dispatcher: Slack webhook fired brand=%s score=%d",
            brand_name,
            relevance_score,
        )

    except httpx.HTTPStatusError as exc:
        logger.error(
            "alert_dispatcher: Slack HTTP %d for brand=%s — %s",
            exc.response.status_code,
            brand_name,
            exc,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("alert_dispatcher: Slack error for brand=%s — %s", brand_name, exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def dispatch_alerts(brand_id: str, db: AsyncSession) -> None:
    """Send alerts for high-relevance mentions found in the last 6 hours.

    Loads the brand and its owner from the database.  Uses the owner's
    ``alert_threshold`` and ``slack_webhook_url`` settings to filter mentions
    and determine delivery channels.

    Args:
        brand_id: UUID string of the brand to check.
        db:       Active async SQLAlchemy session.
    """
    # Convert to uuid.UUID so SQLAlchemy's UUID bind processor works correctly
    # on both PostgreSQL and SQLite (the latter requires a uuid.UUID object,
    # not a plain string, because its bind processor calls value.hex).
    brand_uuid = uuid.UUID(brand_id) if isinstance(brand_id, str) else brand_id

    # Load brand + owner in one query
    brand_result = await db.execute(
        select(Brand, User)
        .join(User, Brand.user_id == User.id)
        .where(Brand.id == brand_uuid)
    )
    row = brand_result.first()

    if row is None:
        logger.warning("alert_dispatcher: brand_id=%s not found — skipping", brand_id)
        return

    brand, user = row
    alert_threshold: int = user.alert_threshold
    slack_webhook_url: str | None = user.slack_webhook_url

    # Query new high-relevance mentions
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_LOOKBACK_HOURS)
    mentions_result = await db.execute(
        select(Mention)
        .where(
            Mention.brand_id == brand_uuid,
            Mention.relevance_score >= alert_threshold,
            Mention.found_at >= cutoff,
        )
        .order_by(Mention.relevance_score.desc())
    )
    mentions = mentions_result.scalars().all()

    if not mentions:
        logger.info(
            "alert_dispatcher: brand_id=%s — no new mentions above threshold=%d in last %dh",
            brand_id,
            alert_threshold,
            _LOOKBACK_HOURS,
        )
        return

    logger.info(
        "alert_dispatcher: brand_id=%s — dispatching %d alert(s) to %s",
        brand_id,
        len(mentions),
        user.email,
    )

    for mention in mentions:
        title = mention.title or mention.url

        await send_alert_email(
            to=user.email,
            brand_name=brand.name,
            mention_title=title,
            mention_url=mention.url,
            relevance_score=mention.relevance_score,
        )

        if slack_webhook_url:
            await _fire_slack_webhook(
                webhook_url=slack_webhook_url,
                brand_name=brand.name,
                mention_title=title,
                mention_url=mention.url,
                relevance_score=mention.relevance_score,
            )
