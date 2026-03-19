"""Pydantic schemas for user registration, login, and token responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    """Payload for POST /auth/register."""

    email: EmailStr
    password: str = Field(min_length=8, description="Plain-text password; hashed server-side")


class UserLogin(BaseModel):
    """Payload for POST /auth/login."""

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Public user representation — hashed_pw is never included."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    email: EmailStr
    plan: str
    created_at: datetime


class TokenResponse(BaseModel):
    """Returned on successful register or login."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessTokenResponse(BaseModel):
    """Returned on POST /auth/refresh — only a new access token is issued."""

    access_token: str
    token_type: str = "bearer"
