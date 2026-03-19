"""Pydantic schemas for GET /settings and PUT /settings."""

from pydantic import BaseModel, Field, field_validator


class SettingsResponse(BaseModel):
    """Current user settings returned by GET /settings."""

    model_config = {"from_attributes": True}

    email: str
    plan: str
    alert_threshold: int
    slack_webhook_url: str | None


class SettingsUpdate(BaseModel):
    """Body for PUT /settings — all fields optional."""

    alert_threshold: int | None = Field(None, ge=0, le=100)
    slack_webhook_url: str | None = None

    @field_validator("slack_webhook_url")
    @classmethod
    def validate_slack_url(cls, v: str | None) -> str | None:
        if v is not None and v != "" and not v.startswith("https://"):
            raise ValueError("slack_webhook_url must be an https:// URL")
        return v or None
