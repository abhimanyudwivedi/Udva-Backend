"""Tests for app/tasks/alert_dispatcher.py.

send_alert_email and the Slack httpx call are mocked — no real Resend API
key or Slack workspace required.  Tests use the in-memory SQLite session
provided by the conftest ``test_db`` fixture.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.mention import Mention
from app.models.user import User
from app.tasks.alert_dispatcher import dispatch_alerts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _recent_mention(brand_id: uuid.UUID, relevance_score: int, **kwargs) -> Mention:  # type: ignore[type-arg]
    """Build a Mention row with a recent found_at so it falls in the 6h window."""
    return Mention(
        id=uuid.uuid4(),
        brand_id=brand_id,
        platform="reddit",
        url=f"https://reddit.com/r/test/{uuid.uuid4()}",
        title="Test mention",
        content_snippet="Some content.",
        relevance_score=relevance_score,
        url_hash=str(uuid.uuid4()),           # unique per mention to avoid constraint errors
        found_at=datetime.now(timezone.utc),  # within the 6h lookback window
        engagement=0,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_mention_above_threshold_triggers_email(
    test_db: AsyncSession, sample_brand: Brand, sample_user: User
) -> None:
    """A mention whose relevance_score >= user.alert_threshold fires an email."""
    mention = _recent_mention(sample_brand.id, relevance_score=80)  # 80 >= 60
    test_db.add(mention)
    await test_db.flush()

    with patch(
        "app.tasks.alert_dispatcher.send_alert_email",
        new_callable=AsyncMock,
    ) as mock_email:
        await dispatch_alerts(str(sample_brand.id), test_db)

    mock_email.assert_called_once()
    call_kwargs = mock_email.call_args.kwargs
    assert call_kwargs["to"] == sample_user.email
    assert call_kwargs["brand_name"] == sample_brand.name
    assert call_kwargs["relevance_score"] == 80


async def test_mention_below_threshold_is_skipped(
    test_db: AsyncSession, sample_brand: Brand
) -> None:
    """A mention whose relevance_score < user.alert_threshold sends no email."""
    mention = _recent_mention(sample_brand.id, relevance_score=40)  # 40 < 60
    test_db.add(mention)
    await test_db.flush()

    with patch(
        "app.tasks.alert_dispatcher.send_alert_email",
        new_callable=AsyncMock,
    ) as mock_email:
        await dispatch_alerts(str(sample_brand.id), test_db)

    mock_email.assert_not_called()


async def test_slack_webhook_fires_when_url_is_set(
    test_db: AsyncSession, sample_brand: Brand, sample_user: User
) -> None:
    """When user.slack_webhook_url is set, a Slack POST is made for each alert."""
    # Give the user a Slack webhook URL
    sample_user.slack_webhook_url = "https://hooks.slack.com/services/T000/B000/test"
    await test_db.flush()

    mention = _recent_mention(sample_brand.id, relevance_score=90)
    test_db.add(mention)
    await test_db.flush()

    # Mock both email and the httpx POST inside _fire_slack_webhook
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_http_client = AsyncMock()
    mock_http_client.post.return_value = mock_response

    with (
        patch(
            "app.tasks.alert_dispatcher.send_alert_email",
            new_callable=AsyncMock,
        ),
        patch("app.tasks.alert_dispatcher.httpx.AsyncClient") as mock_httpx,
    ):
        mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_httpx.return_value.__aexit__ = AsyncMock(return_value=None)

        await dispatch_alerts(str(sample_brand.id), test_db)

    mock_http_client.post.assert_called_once()
    call_args = mock_http_client.post.call_args
    assert call_args.args[0] == sample_user.slack_webhook_url


async def test_slack_webhook_skipped_when_url_is_none(
    test_db: AsyncSession, sample_brand: Brand, sample_user: User
) -> None:
    """When user.slack_webhook_url is None, no Slack POST is made."""
    assert sample_user.slack_webhook_url is None  # default from fixture

    mention = _recent_mention(sample_brand.id, relevance_score=90)
    test_db.add(mention)
    await test_db.flush()

    mock_http_client = AsyncMock()

    with (
        patch(
            "app.tasks.alert_dispatcher.send_alert_email",
            new_callable=AsyncMock,
        ),
        patch("app.tasks.alert_dispatcher.httpx.AsyncClient") as mock_httpx,
    ):
        mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_httpx.return_value.__aexit__ = AsyncMock(return_value=None)

        await dispatch_alerts(str(sample_brand.id), test_db)

    mock_http_client.post.assert_not_called()
