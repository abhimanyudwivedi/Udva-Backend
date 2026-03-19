"""Shared pytest fixtures for Udva test suite.

Provides:
- test_db       — isolated async SQLite session; rolls back after each test
- test_client   — AsyncClient wrapping the FastAPI app with test_db injected
- sample_user   — a committed User row for use in tests
- sample_brand  — a committed Brand row owned by sample_user
- auth_headers  — Bearer token headers for sample_user
"""

import os
import uuid

# ---------------------------------------------------------------------------
# Inject dummy env vars BEFORE importing any app module.
# app/config.py runs `settings = Settings()` at module level — all required
# fields must be present in os.environ at that point or the import fails.
# ---------------------------------------------------------------------------
_TEST_ENV: dict[str, str] = {
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/udva_test",
    "OPENAI_API_KEY": "test-openai-key",
    "ANTHROPIC_API_KEY": "test-anthropic-key",
    "GOOGLE_AI_API_KEY": "test-google-key",
    "REDDIT_CLIENT_ID": "test-reddit-id",
    "REDDIT_CLIENT_SECRET": "test-reddit-secret",
    "SERPER_API_KEY": "test-serper-key",
    "JWT_SECRET_KEY": "a" * 64,  # 64-char hex-like string
    "DODO_PAYMENTS_API_KEY": "test-dodo-key",
    "DODO_WEBHOOK_SECRET": "test-dodo-webhook-secret",
    "RESEND_API_KEY": "test-resend-key",
    "ACCOUNT_ENCRYPTION_KEY": "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXQ=",  # base64 32-bytes
}
for _key, _val in _TEST_ENV.items():
    os.environ.setdefault(_key, _val)

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.database import Base, get_db
from app.lib.auth import create_access_token, hash_password
from app.main import app
from app.models.brand import Brand
from app.models.user import User

# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def test_db() -> AsyncSession:  # type: ignore[misc]
    """Create a fresh in-memory SQLite database for a single test.

    All tables are created from the ORM metadata, a transaction is opened,
    the session is yielded to the test, and the transaction is rolled back
    on teardown — so no state leaks between tests.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        await session.begin()
        yield session
        await session.rollback()

    await engine.dispose()


# ---------------------------------------------------------------------------
# HTTP client fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def test_client(test_db: AsyncSession) -> AsyncClient:  # type: ignore[misc]
    """Return an httpx AsyncClient backed by the FastAPI app and test_db.

    Overrides the ``get_db`` dependency so that all routes execute within the
    same rolled-back SQLite transaction as the test.
    """

    async def _override_get_db():  # type: ignore[return]
        yield test_db

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)  # type: ignore[arg-type]

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Data fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def sample_user(test_db: AsyncSession) -> User:
    """Insert a test User row and return it.

    Settings: plan=solo, alert_threshold=60, slack_webhook_url=None.
    Password is "password123" (bcrypt-hashed).
    """
    user = User(
        id=uuid.uuid4(),
        email="test@udva.io",
        hashed_pw=hash_password("password123"),
        plan="solo",
        alert_threshold=60,
        slack_webhook_url=None,
    )
    test_db.add(user)
    await test_db.flush()
    return user


@pytest.fixture
async def sample_brand(test_db: AsyncSession, sample_user: User) -> Brand:
    """Insert a test Brand row owned by sample_user and return it."""
    brand = Brand(
        id=uuid.uuid4(),
        user_id=sample_user.id,
        name="AcmeCorp",
        domain="acme.com",
        is_active=True,
    )
    test_db.add(brand)
    await test_db.flush()
    return brand


@pytest.fixture
async def auth_headers(sample_user: User) -> dict[str, str]:
    """Return Authorization headers containing a valid Bearer token for sample_user."""
    token = create_access_token(str(sample_user.id), sample_user.plan)
    return {"Authorization": f"Bearer {token}"}
