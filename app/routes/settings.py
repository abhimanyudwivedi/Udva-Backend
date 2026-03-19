"""Settings routes — read and update per-user alert preferences.

GET /settings   — return current user's settings
PUT /settings   — update alert_threshold and/or slack_webhook_url
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.lib.auth import get_current_user
from app.models.user import User
from app.schemas.settings import SettingsResponse, SettingsUpdate

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# GET /settings
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=SettingsResponse,
    summary="Get current user settings",
)
async def get_settings(
    current_user: User = Depends(get_current_user),
) -> SettingsResponse:
    """Return the authenticated user's plan and alert settings.

    No database round-trip needed — the user object is already loaded by
    ``get_current_user``.
    """
    return SettingsResponse.model_validate(current_user)


# ---------------------------------------------------------------------------
# PUT /settings
# ---------------------------------------------------------------------------


@router.put(
    "",
    response_model=SettingsResponse,
    summary="Update user settings",
)
async def update_settings(
    body: SettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SettingsResponse:
    """Update alert_threshold and/or slack_webhook_url for the authenticated user.

    Only fields present in the request body are updated; omitted fields are
    left unchanged.

    Args:
        body: ``{alert_threshold?, slack_webhook_url?}``

    Raises:
        HTTPException 422: ``alert_threshold`` outside 0–100 range, or
                           ``slack_webhook_url`` is not an https:// URL.
    """
    if body.alert_threshold is not None:
        current_user.alert_threshold = body.alert_threshold

    # Allow explicit null to clear the webhook URL
    if "slack_webhook_url" in body.model_fields_set:
        current_user.slack_webhook_url = body.slack_webhook_url

    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)

    logger.info(
        "settings: updated user=%s threshold=%d slack=%s",
        current_user.email,
        current_user.alert_threshold,
        bool(current_user.slack_webhook_url),
    )

    return SettingsResponse.model_validate(current_user)
