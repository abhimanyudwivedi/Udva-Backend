"""Auth endpoints: register, login, refresh.

All three routes are public (no Bearer token required).
Successful register and login both return a full TokenResponse.
Refresh returns only a new access token — the refresh token itself
is long-lived and not rotated here.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.lib.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.user import AccessTokenResponse, TokenResponse, UserCreate, UserLogin, UserResponse

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Create a new user, hash their password, and return a token pair.

    Args:
        body: ``UserCreate`` payload with ``email`` and ``password``.
        db:   Injected async database session.

    Returns:
        ``TokenResponse`` containing ``access_token``, ``refresh_token``,
        and ``token_type``.

    Raises:
        HTTPException 409: Email already registered.
        HTTPException 400: Unexpected database constraint violation.
    """
    user = User(
        email=body.email.lower(),
        hashed_pw=hash_password(body.password),
        plan="trial",
    )
    db.add(user)
    try:
        await db.flush()  # surface constraint errors before commit
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    await db.commit()
    await db.refresh(user)

    user_id = str(user.id)
    return TokenResponse(
        access_token=create_access_token(user_id, user.plan),
        refresh_token=create_refresh_token(user_id),
    )


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in with email and password",
)
async def login(
    body: UserLogin,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Verify credentials and return a token pair.

    Args:
        body: ``UserLogin`` payload with ``email`` and ``password``.
        db:   Injected async database session.

    Returns:
        ``TokenResponse`` containing ``access_token``, ``refresh_token``,
        and ``token_type``.

    Raises:
        HTTPException 401: Email not found or password incorrect.
            (Deliberately identical messages to prevent user enumeration.)
    """
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()

    # Constant-time check: always call verify_password to prevent timing attacks
    # even when the user doesn't exist.
    dummy_hash = "$2b$12$placeholderfortimingattackpreventiononlyxxxxxxxxxxxxxx"
    password_ok = verify_password(body.password, user.hashed_pw if user else dummy_hash)

    if not user or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = str(user.id)
    return TokenResponse(
        access_token=create_access_token(user_id, user.plan),
        refresh_token=create_refresh_token(user_id),
    )


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    summary="Exchange a refresh token for a new access token",
)
async def refresh(
    body: dict[str, str],
    db: AsyncSession = Depends(get_db),
) -> AccessTokenResponse:
    """Validate a refresh token and issue a new access token.

    The request body must contain ``{"refresh_token": "<token>"}``.

    Args:
        body: Dict with key ``refresh_token``.
        db:   Injected async database session.

    Returns:
        ``AccessTokenResponse`` with a fresh ``access_token``.

    Raises:
        HTTPException 400: ``refresh_token`` key missing from body.
        HTTPException 401: Token expired, invalid, wrong type, or user gone.
    """
    token = body.get("refresh_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="refresh_token is required",
        )

    payload = decode_token(token)  # raises 401 if expired / invalid

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AccessTokenResponse(
        access_token=create_access_token(str(user.id), user.plan),
    )
