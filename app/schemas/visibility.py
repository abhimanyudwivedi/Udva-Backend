"""Pydantic schemas for Pillar 1 — AI Visibility Tracker API responses."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Raw score (single row)
# ---------------------------------------------------------------------------


class VisibilityScoreResponse(BaseModel):
    """One visibility score row — one query × model × run."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    query_id: uuid.UUID
    model: str
    brand_mentioned: bool
    mention_rank: int | None
    sentiment: str | None
    is_competitor: bool
    scored_at: datetime


# ---------------------------------------------------------------------------
# Trend (GET /visibility — 30-day time series)
# ---------------------------------------------------------------------------


class VisibilityTrendPoint(BaseModel):
    """Aggregated score stats for one model on one calendar day."""

    date: date
    model: str
    total_queries: int
    mentioned_count: int
    mention_rate: float = Field(
        description="Fraction of queries where brand was mentioned (0.0–1.0)"
    )
    avg_mention_rank: float | None = Field(
        description="Average mention rank across mentioned queries; None if never mentioned"
    )


class VisibilityTrendResponse(BaseModel):
    """30-day trend data for one brand, grouped by model × date."""

    brand_id: uuid.UUID
    period_days: int
    data: list[VisibilityTrendPoint]


# ---------------------------------------------------------------------------
# Citations (GET /visibility/citations)
# ---------------------------------------------------------------------------


class CitationSourceResponse(BaseModel):
    """One citation source row."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    model: str
    url: str
    domain: str
    found_at: datetime


class TopCitationDomain(BaseModel):
    """Aggregated citation count for one domain."""

    domain: str
    citation_count: int
    last_seen: datetime


class CitationsResponse(BaseModel):
    """Top cited domains for a brand over the last 30 days."""

    brand_id: uuid.UUID
    period_days: int
    domains: list[TopCitationDomain]


# ---------------------------------------------------------------------------
# Compare (GET /visibility/compare — brand vs competitors)
# ---------------------------------------------------------------------------


class CompetitorMentionRate(BaseModel):
    """Aggregated mention stats for one competitor on one model."""

    name: str
    mention_rate: float = Field(description="Fraction of queries where competitor was mentioned")
    avg_mention_rank: float | None


class CompareDataPoint(BaseModel):
    """Brand vs competitors for one LLM model."""

    model: str
    brand_mention_rate: float
    brand_avg_mention_rank: float | None
    competitors: list[CompetitorMentionRate]


class CompareResponse(BaseModel):
    """Side-by-side brand vs competitor visibility across all models."""

    brand_id: uuid.UUID
    brand_name: str
    period_days: int
    data: list[CompareDataPoint]
