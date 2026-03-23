"""Billing routes — DodoPayments checkout and webhook receiver.

POST /billing/checkout   — create a subscription checkout (auth required)
POST /billing/topup      — create a one-time credit top-up checkout (auth required)
POST /billing/webhook    — DodoPayments webhook receiver (no auth, signature-verified)
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from standardwebhooks.webhooks import WebhookVerificationError

from app.database import get_db  # noqa: F401  (kept for potential future use)
from app.lib.auth import get_current_user
from app.lib.dodo_client import create_checkout_session, create_topup_checkout, handle_webhook
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CheckoutRequest(BaseModel):
    """Body for POST /billing/checkout."""

    plan: str  # "starter" | "growth" | "enterprise"


class TopupRequest(BaseModel):
    """Body for POST /billing/topup."""

    product_id: str  # raw DodoPayments product ID for the credit package


class CheckoutResponse(BaseModel):
    """Checkout URL returned after creating a DodoPayments session."""

    checkout_url: str


# ---------------------------------------------------------------------------
# POST /billing/checkout
# ---------------------------------------------------------------------------


@router.post(
    "/checkout",
    response_model=CheckoutResponse,
    summary="Create subscription checkout",
)
async def billing_checkout(
    body: CheckoutRequest,
    current_user: User = Depends(get_current_user),
) -> CheckoutResponse:
    """Create a DodoPayments subscription checkout session.

    The frontend should redirect the user to the returned ``checkout_url``.
    After payment, DodoPayments fires a ``subscription.active`` webhook which
    updates ``user.plan`` in the database.

    Args:
        body: ``{plan}`` — plan slug: ``"starter"``, ``"growth"``, or ``"enterprise"``.

    Raises:
        HTTPException 400: Unknown plan slug.
        HTTPException 502: DodoPayments API call failed.
    """
    try:
        checkout_url = await create_checkout_session(
            user=current_user,
            plan=body.plan,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error(
            "billing/checkout: DodoPayments error user=%s — %s", current_user.email, exc
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment provider error — please try again.",
        ) from exc

    return CheckoutResponse(checkout_url=checkout_url)


# ---------------------------------------------------------------------------
# POST /billing/topup
# ---------------------------------------------------------------------------


@router.post(
    "/topup",
    response_model=CheckoutResponse,
    summary="Create credit top-up checkout",
)
async def billing_topup(
    body: TopupRequest,
    current_user: User = Depends(get_current_user),
) -> CheckoutResponse:
    """Create a one-time DodoPayments checkout for purchasing additional credits.

    Args:
        body: ``{product_id}`` — DodoPayments product ID for the credit package.

    Raises:
        HTTPException 502: DodoPayments API call failed.
    """
    try:
        checkout_url = await create_topup_checkout(
            user=current_user,
            product_id=body.product_id,
        )
    except Exception as exc:
        logger.error(
            "billing/topup: DodoPayments error user=%s — %s", current_user.email, exc
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment provider error — please try again.",
        ) from exc

    return CheckoutResponse(checkout_url=checkout_url)


# ---------------------------------------------------------------------------
# POST /billing/webhook
# ---------------------------------------------------------------------------


@router.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
    summary="DodoPayments webhook receiver",
    include_in_schema=False,  # hide from public docs
)
async def billing_webhook(request: Request) -> dict[str, str]:
    """Receive and process DodoPayments webhook events.

    No JWT auth — instead the signature is verified using the Standard
    Webhooks spec (``webhook-id``, ``webhook-signature``,
    ``webhook-timestamp`` headers).

    The raw request body is read before any parsing to ensure the signature
    remains valid.  Returns 200 immediately after dispatching — all DB work
    happens inside ``handle_webhook`` which manages its own session.

    Raises:
        HTTPException 400: Webhook signature verification failed.
    """
    payload = await request.body()
    headers = dict(request.headers)

    try:
        await handle_webhook(payload, headers)
    except WebhookVerificationError as exc:
        logger.warning("billing/webhook: signature verification failed — %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature.",
        ) from exc

    return {"status": "ok"}
