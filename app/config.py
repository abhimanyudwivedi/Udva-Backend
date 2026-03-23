"""Application configuration loaded from environment variables via Pydantic Settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All Udva environment variables, sourced from .env or Railway env vars."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Database
    # -------------------------------------------------------------------------
    DATABASE_URL: str = Field(
        description="Async PostgreSQL URL: postgresql+asyncpg://user:pass@host:5432/udva"
    )

    # -------------------------------------------------------------------------
    # Redis
    # -------------------------------------------------------------------------
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis URL used as Celery broker and result backend",
    )

    # -------------------------------------------------------------------------
    # LLM APIs
    # -------------------------------------------------------------------------
    OPENAI_API_KEY: str = Field(description="OpenAI API key (sk-...)")
    ANTHROPIC_API_KEY: str = Field(description="Anthropic API key (sk-ant-...)")
    GOOGLE_AI_API_KEY: str = Field(description="Google AI / Gemini API key (AIza...)")
    PERPLEXITY_API_KEY: str = Field(
        default="",
        description="Perplexity API key — optional, required for Growth+ plans",
    )

    # -------------------------------------------------------------------------
    # Data source APIs
    # -------------------------------------------------------------------------
    REDDIT_CLIENT_ID: str = Field(description="Reddit OAuth2 client ID")
    REDDIT_CLIENT_SECRET: str = Field(description="Reddit OAuth2 client secret")
    REDDIT_USER_AGENT: str = Field(
        default="udva/1.0",
        description="Reddit user-agent string",
    )
    SERPER_API_KEY: str = Field(description="Serper.dev API key for SERP rank checks")

    # -------------------------------------------------------------------------
    # Auth / JWT
    # -------------------------------------------------------------------------
    JWT_SECRET_KEY: str = Field(description="64-char random hex secret for JWT signing")
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT signing algorithm")
    SUPABASE_URL: str = Field(
        description="Supabase project URL, e.g. https://xxxx.supabase.co"
    )
    SUPABASE_JWT_SECRET: str = Field(
        default="",
        description="Supabase JWT secret — kept for reference, verification now uses JWKS",
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30, description="Access token TTL in minutes"
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=7, description="Refresh token TTL in days"
    )

    # -------------------------------------------------------------------------
    # Payments — DodoPayments
    # -------------------------------------------------------------------------
    DODO_PAYMENTS_API_KEY: str = Field(description="DodoPayments API key")
    DODO_WEBHOOK_SECRET: str = Field(description="DodoPayments webhook signing secret (standardwebhooks)")
    DODO_PRODUCT_STARTER: str = Field(default="", description="DodoPayments product ID for Starter plan ($49/mo)")
    DODO_PRODUCT_GROWTH: str = Field(default="", description="DodoPayments product ID for Growth plan ($199/mo)")
    DODO_PRODUCT_ENTERPRISE: str = Field(default="", description="DodoPayments product ID for Enterprise plan ($299/mo)")
    DODO_ENVIRONMENT: str = Field(
        default="test_mode",
        description="DodoPayments environment: test_mode | live_mode",
    )

    # -------------------------------------------------------------------------
    # Email — Resend
    # -------------------------------------------------------------------------
    RESEND_API_KEY: str = Field(description="Resend API key (re_...)")
    EMAIL_FROM: str = Field(
        default="shipfast.pvt@gmail.com",
        description="Sender address for transactional emails",
    )

    # -------------------------------------------------------------------------
    # Encryption (Reddit account passwords stored AES-256 encrypted)
    # -------------------------------------------------------------------------
    ACCOUNT_ENCRYPTION_KEY: str = Field(
        description="32-byte AES key, base64-encoded, for encrypting Reddit account passwords"
    )

    # -------------------------------------------------------------------------
    # Error tracking — Sentry
    # -------------------------------------------------------------------------
    SENTRY_DSN: str = Field(default="", description="Sentry DSN URL (leave blank to disable)")

    # -------------------------------------------------------------------------
    # App
    # -------------------------------------------------------------------------
    ENVIRONMENT: str = Field(
        default="development",
        description="Runtime environment: development | production",
    )
    DEBUG: bool = Field(default=False, description="Enable debug mode")


settings = Settings()  # type: ignore[call-arg]
