"""FastAPI application entry point — registers routers, middleware, and Sentry."""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings


# ---------------------------------------------------------------------------
# Sentry — initialise before app starts
# ---------------------------------------------------------------------------
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        traces_sample_rate=0.2,
        profiles_sample_rate=0.1,
    )


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown hooks)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Run startup and shutdown logic for the FastAPI application."""
    # Startup: nothing needed — SQLAlchemy engine is lazy
    yield
    # Shutdown: dispose the connection pool
    from app.database import engine
    await engine.dispose()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Udva API",
    description="AI search visibility platform — track, listen, engage.",
    version="0.1.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
ALLOWED_ORIGINS = [
    "https://udva.net",
    "https://www.udva.net",
    "https://app.udva.net",
]

if settings.ENVIRONMENT == "development":
    ALLOWED_ORIGINS += ["http://localhost:3000", "http://127.0.0.1:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
from app.routes.auth import router as auth_router
from app.routes.billing import router as billing_router
from app.routes.brands import router as brands_router
from app.routes.listening import router as listening_router
from app.routes.settings import router as settings_router
from app.routes.visibility import router as visibility_router

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(brands_router, prefix="/brands", tags=["brands"])
app.include_router(visibility_router, prefix="/brands", tags=["visibility"])
app.include_router(listening_router, prefix="/brands", tags=["listening"])
app.include_router(billing_router, prefix="/billing", tags=["billing"])
app.include_router(settings_router, prefix="/settings", tags=["settings"])

# Uncomment as each router is implemented:
# from app.routes.campaigns import router as campaigns_router
# app.include_router(campaigns_router, prefix="/brands", tags=["campaigns"])


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health", tags=["meta"])
async def health_check() -> dict[str, str]:
    """Return a simple liveness signal. Used by Railway health checks."""
    return {"status": "ok", "environment": settings.ENVIRONMENT}
