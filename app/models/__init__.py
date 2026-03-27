"""Import all ORM models so Alembic autogenerate detects every table."""

from app.models.brand import Brand
from app.models.campaign import Campaign
from app.models.citation_source import CitationSource
from app.models.competitor import Competitor
from app.models.credit_ledger import CreditLedger
from app.models.keyword import Keyword
from app.models.mention import Mention
from app.models.onboarding_scan import OnboardingScan
from app.models.query import Query
from app.models.reddit_account import RedditAccount
from app.models.user import User
from app.models.visibility_score import VisibilityScore
from app.models.visibility_weekly import VisibilityWeekly

__all__ = [
    "Brand",
    "Campaign",
    "CitationSource",
    "Competitor",
    "CreditLedger",
    "Keyword",
    "Mention",
    "OnboardingScan",
    "Query",
    "RedditAccount",
    "User",
    "VisibilityScore",
    "VisibilityWeekly",
]
