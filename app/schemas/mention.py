"""Pydantic schemas for Pillar 2 — Social Listening API responses."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MentionResponse(BaseModel):
    """Public representation of one social mention."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    platform: str = Field(description="reddit | quora | facebook")
    url: str
    title: str | None
    content_snippet: str | None
    author: str | None
    engagement: int = Field(description="Upvotes / score")
    google_rank: int | None = Field(description="1–10 if on Google page 1, else None")
    relevance_score: int = Field(description="0–100 relevance score")
    found_at: datetime


class MentionFeedResponse(BaseModel):
    """Paginated list of mentions."""

    items: list[MentionResponse]
    total: int
    page: int
    limit: int


class AdHocSearchRequest(BaseModel):
    """Body for POST /brands/{id}/mentions/search."""

    keyword: str = Field(min_length=1, max_length=120)
    platform: Literal["reddit", "quora"] = "reddit"


class AdHocSearchResponse(BaseModel):
    """Results of an immediate ad-hoc mention search."""

    keyword: str
    platform: str
    inserted: int = Field(description="Number of new mentions found and stored")
    items: list[MentionResponse]
