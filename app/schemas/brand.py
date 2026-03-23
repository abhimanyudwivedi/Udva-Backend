"""Pydantic schemas for brands, tracked queries, and keywords."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Brand
# ---------------------------------------------------------------------------


class BrandCreate(BaseModel):
    """Payload for POST /brands."""

    name: str = Field(min_length=1, max_length=120)
    domain: str | None = Field(default=None, max_length=253)


class BrandUpdate(BaseModel):
    """Payload for PUT /brands/{id} — all fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    domain: str | None = Field(default=None, max_length=253)


class BrandResponse(BaseModel):
    """Public brand representation returned by list and detail endpoints."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    domain: str | None
    is_active: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Query (tracked LLM prompt)
# ---------------------------------------------------------------------------


class QueryCreate(BaseModel):
    """Payload for POST /brands/{id}/queries."""

    prompt_text: str = Field(min_length=10, max_length=500)


class QueryResponse(BaseModel):
    """Public query representation."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    prompt_text: str
    is_active: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Keyword
# ---------------------------------------------------------------------------

_VALID_PLATFORMS = Literal["reddit", "quora", "facebook"]


class KeywordCreate(BaseModel):
    """Payload for POST /brands/{id}/keywords."""

    keyword: str = Field(min_length=1, max_length=120)
    platform: _VALID_PLATFORMS = "reddit"


class KeywordResponse(BaseModel):
    """Public keyword representation."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    keyword: str
    platform: str
    is_active: bool


# ---------------------------------------------------------------------------
# Paginated wrappers
# ---------------------------------------------------------------------------


class PaginatedBrands(BaseModel):
    """Paginated list of brands."""

    items: list[BrandResponse]
    total: int
    page: int
    limit: int


class PaginatedQueries(BaseModel):
    """Paginated list of tracked prompts."""

    items: list[QueryResponse]
    total: int
    page: int
    limit: int


class PaginatedKeywords(BaseModel):
    """Paginated list of keywords."""

    items: list[KeywordResponse]
    total: int
    page: int
    limit: int


# ---------------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------------


class SuggestionsResponse(BaseModel):
    """LLM-generated query and keyword suggestions for a brand."""

    queries: list[str]
    keywords: list[str]
