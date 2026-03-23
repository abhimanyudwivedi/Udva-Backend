"""JWT helpers and FastAPI authentication dependency for Udva.

Token structure
---------------
Supabase access token (frontend → backend):
    { "sub": "<supabase_user_uuid>", "email": "...", "exp": <unix_ts>, ... }
    Decoded with SUPABASE_JWT_SECRET from Supabase dashboard → Settings → API.

Legacy tokens (kept for /auth/* routes):
    Access:  { "sub": "<user_id>", "plan": "<plan>", "type": "access",  "exp": ... }
    Refresh: { "sub": "<user_id>",                   "type": "refresh", "exp": ... }
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwk, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer()

# ---------------------------------------------------------------------------
# Supabase JWKS cache (fetched once, reused for all token verifications)
# ---------------------------------------------------------------------------

_supabase_jwks: list[dict] | None = None


async def _get_supabase_jwks() -> list[dict]:
    """Fetch and cache the Supabase JWKS public keys."""
    global _supabase_jwks
    if _supabase_jwks is None:
        jwks_url = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(jwks_url)
            resp.raise_for_status()
            _supabase_jwks = resp.json()["keys"]
        logger.info("Fetched %d Supabase JWKS key(s)", len(_supabase_jwks))
    return _supabase_jwks

# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches *hashed*."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------


def create_access_token(user_id: str, plan: str) -> str:
    """Mint a signed JWT access token valid for ``ACCESS_TOKEN_EXPIRE_MINUTES``.

    Args:
        user_id: String representation of the user's UUID primary key.
        plan:    The user's current plan slug (trial | solo | indie | studio | agency).

    Returns:
        Encoded JWT string.
    """
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": user_id,
        "plan": plan,
        "type": "access",
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Mint a signed JWT refresh token valid for ``REFRESH_TOKEN_EXPIRE_DAYS``.

    Args:
        user_id: String representation of the user's UUID primary key.

    Returns:
        Encoded JWT string.
    """
    expire = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload: dict[str, Any] = {
        "sub": user_id,
        "type": "refresh",
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# Token decoding
# ---------------------------------------------------------------------------


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate *token*, returning its payload dict.

    Raises:
        HTTPException 401: If the token is expired, malformed, or has an
            invalid signature.
    """
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as exc:
        logger.warning("JWT decode failure: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency that resolves a Supabase Bearer token to a User row.

    Decodes the Supabase JWT using SUPABASE_JWT_SECRET. On first login the
    user is auto-provisioned in our database (plan = 'trial').

    Raises:
        HTTPException 401: If the token is invalid, expired, or missing sub.
    """
    try:
        keys = await _get_supabase_jwks()
        # Try each key in the JWKS until one verifies the token
        payload: dict[str, Any] | None = None
        last_exc: Exception | None = None
        for key_data in keys:
            try:
                public_key = jwk.construct(key_data)
                payload = jwt.decode(
                    credentials.credentials,
                    public_key,
                    algorithms=[key_data.get("alg", "ES256")],
                    options={"verify_aud": False},
                )
                break
            except ExpiredSignatureError:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has expired",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            except JWTError as exc:
                last_exc = exc
                continue
        if payload is None:
            logger.warning("Supabase JWT decode failure: %s", last_exc)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Supabase JWKS fetch/decode error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str | None = payload.get("sub")
    email: str | None = payload.get("email")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        # First login via Supabase — auto-provision a User row
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing email claim",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user = User(
            id=user_id,  # type: ignore[arg-type]
            email=email,
            hashed_pw="",  # Supabase manages auth — no local password
            plan="trial",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info("Auto-provisioned user %s (%s)", user_id, email)

    return user
