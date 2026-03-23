"""DodoPayments client — checkout sessions and webhook handling.

Checkout flow
-------------
Both subscription and one-time topup checkouts create a hosted checkout
page via the DodoPayments API.  The returned ``payment_link`` URL is sent
to the frontend which redirects the user there.

Webhook flow
------------
DodoPayments signs webhook payloads with the Standard Webhooks spec.
``handle_webhook`` verifies the signature, then dispatches on event type:

  subscription.active    → update user.plan in DB
  subscription.cancelled → revert user.plan to "trial"
  payment.succeeded      → insert CreditLedger row (reason="plan_credit")
  payment.failed         → send alert email to the user
"""

import logging
import uuid

from dodopayments import AsyncDodoPayments
from standardwebhooks import Webhook as StandardWebhook
from standardwebhooks.webhooks import WebhookVerificationError
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.lib.email import send_alert_email
from app.models.brand import Brand
from app.models.credit_ledger import CreditLedger
from app.models.user import User

logger = logging.getLogger(__name__)

_RETURN_URL = "https://udva.net/dashboard"

# Monthly credits granted per plan on payment.succeeded
_PLAN_CREDITS: dict[str, int] = {
    "starter": 50,
    "growth": 200,
    "enterprise": 300,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_client() -> AsyncDodoPayments:
    """Return a configured AsyncDodoPayments instance."""
    return AsyncDodoPayments(
        bearer_token=settings.DODO_PAYMENTS_API_KEY,
        environment=settings.DODO_ENVIRONMENT,
    )


def _product_plan_map() -> dict[str, str]:
    """Return a mapping of DodoPayments product IDs → plan slugs.

    Built at call-time so settings are always current (relevant for tests).
    """
    return {
        settings.DODO_PRODUCT_STARTER: "starter",
        settings.DODO_PRODUCT_GROWTH: "growth",
        settings.DODO_PRODUCT_ENTERPRISE: "enterprise",
    }


def _plan_product_map() -> dict[str, str]:
    """Return a mapping of plan slugs → DodoPayments product IDs.

    Built at call-time so settings are always current (relevant for tests).
    """
    return {
        "starter": settings.DODO_PRODUCT_STARTER,
        "growth": settings.DODO_PRODUCT_GROWTH,
        "enterprise": settings.DODO_PRODUCT_ENTERPRISE,
    }


def _verify_webhook(payload: bytes, headers: dict[str, str]) -> dict:
    """Verify a DodoPayments webhook signature and return the parsed event.

    Uses the Standard Webhooks spec.  Required headers:
      ``webhook-id``, ``webhook-signature``, ``webhook-timestamp``

    Args:
        payload: Raw request body bytes.
        headers: Request headers dict (lowercase key names).

    Returns:
        Parsed event dict.

    Raises:
        WebhookVerificationError: Signature is invalid or headers are missing.
    """
    wh = StandardWebhook(settings.DODO_WEBHOOK_SECRET)
    # standardwebhooks accepts the body as str or bytes
    event: dict = wh.verify(
        payload,
        {
            "webhook-id": headers.get("webhook-id", ""),
            "webhook-signature": headers.get("webhook-signature", ""),
            "webhook-timestamp": headers.get("webhook-timestamp", ""),
        },
    )
    return event


# ---------------------------------------------------------------------------
# Public API — checkout
# ---------------------------------------------------------------------------


async def create_checkout_session(user: User, plan: str) -> str:
    """Create a DodoPayments subscription checkout and return the checkout URL.

    Uses ``checkout_sessions.create()`` with ``subscription_data`` so the
    hosted checkout page handles payment collection and subscription creation.

    Args:
        user: The authenticated user initiating the checkout.
        plan: Plan slug — ``"starter"``, ``"growth"``, or ``"enterprise"``.

    Returns:
        Hosted checkout URL to redirect the user to.

    Raises:
        ValueError: Unknown plan slug or product ID not configured.
        Exception: Propagates any DodoPayments SDK errors to the caller.
    """
    product_id = _plan_product_map().get(plan)
    if not product_id:
        raise ValueError(f"Unknown plan slug or product ID not configured: {plan!r}")

    client = _get_client()

    result = await client.checkout_sessions.create(
        product_cart=[{"product_id": product_id, "quantity": 1}],
        customer={"email": user.email},
        return_url=_RETURN_URL,
    )

    logger.info(
        "dodo_client: subscription checkout created user=%s plan=%s product_id=%s",
        user.email,
        plan,
        product_id,
    )
    return result.checkout_url  # type: ignore[no-any-return]


async def create_topup_checkout(user: User, product_id: str) -> str:
    """Create a one-time DodoPayments checkout for a credit top-up.

    Args:
        user:       The authenticated user purchasing credits.
        product_id: DodoPayments product ID for the credit top-up package.

    Returns:
        Hosted checkout URL to redirect the user to.

    Raises:
        Exception: Propagates any DodoPayments SDK errors to the caller.
    """
    client = _get_client()

    result = await client.checkout_sessions.create(
        product_cart=[{"product_id": product_id, "quantity": 1}],
        customer={"email": user.email},
        return_url=_RETURN_URL,
    )

    logger.info(
        "dodo_client: topup checkout created user=%s product_id=%s",
        user.email,
        product_id,
    )
    return result.checkout_url  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Public API — webhook handler
# ---------------------------------------------------------------------------


async def handle_webhook(payload: bytes, headers: dict[str, str]) -> None:
    """Verify a DodoPayments webhook and process the event.

    Opens its own DB session.  All errors inside event handlers are caught
    and logged — a bad handler must never cause a non-200 response (that
    would trigger DodoPayments to retry indefinitely).

    Signature verification failures propagate as ``WebhookVerificationError``
    so the route can return 400.

    Args:
        payload: Raw request body bytes (must not be parsed first).
        headers: Lowercase request headers dict.

    Raises:
        WebhookVerificationError: Signature is invalid.
    """
    event = _verify_webhook(payload, headers)

    event_type: str = event.get("type", "")
    data: dict = event.get("data", {})

    customer: dict = data.get("customer", {})
    customer_email: str = customer.get("email", "")
    product_id: str = data.get("product_id", "")
    subscription_id: str = data.get("subscription_id", "")

    logger.info("dodo_client: received event type=%s email=%s", event_type, customer_email)

    if not customer_email:
        logger.warning("dodo_client: event %s has no customer email — skipping", event_type)
        return

    if event_type == "subscription.active":
        await _handle_subscription_active(customer_email, product_id, subscription_id)

    elif event_type == "subscription.cancelled":
        await _handle_subscription_cancelled(customer_email)

    elif event_type == "payment.succeeded":
        await _handle_payment_succeeded(customer_email, product_id)

    elif event_type == "payment.failed":
        await _handle_payment_failed(customer_email)

    else:
        logger.debug("dodo_client: unhandled event type=%s — ignoring", event_type)


# ---------------------------------------------------------------------------
# Event handlers (each opens its own session)
# ---------------------------------------------------------------------------


async def _handle_subscription_active(
    email: str, product_id: str, subscription_id: str
) -> None:
    """Set user.plan and dodo_sub_id to the plan corresponding to product_id."""
    plan = _product_plan_map().get(product_id)
    if plan is None:
        logger.warning(
            "dodo_client: subscription.active — unknown product_id=%s for email=%s",
            product_id,
            email,
        )
        return

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            if user is None:
                logger.warning("dodo_client: subscription.active — user not found email=%s", email)
                return

            user.plan = plan
            if subscription_id:
                user.dodo_sub_id = subscription_id
            await db.commit()
            logger.info(
                "dodo_client: subscription.active — updated email=%s plan=%s sub_id=%s",
                email,
                plan,
                subscription_id,
            )
    except Exception as exc:  # noqa: BLE001
        logger.error("dodo_client: subscription.active handler error — %s", exc)


async def _handle_subscription_cancelled(email: str) -> None:
    """Revert user.plan to 'trial' and clear dodo_sub_id."""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            if user is None:
                logger.warning(
                    "dodo_client: subscription.cancelled — user not found email=%s", email
                )
                return

            user.plan = "trial"
            user.dodo_sub_id = None
            await db.commit()
            logger.info("dodo_client: subscription.cancelled — reverted email=%s to trial", email)
    except Exception as exc:  # noqa: BLE001
        logger.error("dodo_client: subscription.cancelled handler error — %s", exc)


async def cancel_subscription(user: User) -> None:
    """Cancel the user's active DodoPayments subscription immediately.

    Args:
        user: The authenticated user requesting cancellation.

    Raises:
        ValueError: User has no active subscription ID on record.
        Exception: Propagates any DodoPayments SDK errors to the caller.
    """
    if not user.dodo_sub_id:
        raise ValueError("No active subscription found.")

    client = _get_client()
    await client.subscriptions.update(
        user.dodo_sub_id,
        cancel_at_next_billing_date=True,
    )
    logger.info("dodo_client: cancel_subscription — cancelled sub_id=%s email=%s", user.dodo_sub_id, user.email)


async def _handle_payment_succeeded(email: str, product_id: str) -> None:
    """Insert a CreditLedger row for each of the user's active brands."""
    plan = _product_plan_map().get(product_id)
    credits = _PLAN_CREDITS.get(plan or "", 0) if plan else 0

    if credits == 0:
        logger.debug(
            "dodo_client: payment.succeeded — unknown product_id=%s, granting 0 credits",
            product_id,
        )

    try:
        async with AsyncSessionLocal() as db:
            user_result = await db.execute(select(User).where(User.email == email))
            user = user_result.scalar_one_or_none()
            if user is None:
                logger.warning(
                    "dodo_client: payment.succeeded — user not found email=%s", email
                )
                return

            brands_result = await db.execute(
                select(Brand).where(
                    Brand.user_id == user.id,
                    Brand.is_active.is_(True),
                )
            )
            brands = brands_result.scalars().all()

            for brand in brands:
                db.add(
                    CreditLedger(
                        id=uuid.uuid4(),
                        brand_id=brand.id,
                        delta=credits,
                        reason="plan_credit",
                    )
                )

            await db.commit()
            logger.info(
                "dodo_client: payment.succeeded — granted %d credits to %d brand(s) for email=%s",
                credits,
                len(brands),
                email,
            )
    except Exception as exc:  # noqa: BLE001
        logger.error("dodo_client: payment.succeeded handler error — %s", exc)


async def _handle_payment_failed(email: str) -> None:
    """Send a payment failure alert email to the user."""
    try:
        await send_alert_email(
            to=email,
            brand_name="your Udva account",
            mention_title="Payment failed — please update your billing details",
            mention_url="https://app.udva.net/settings",
            relevance_score=0,
        )
        logger.info("dodo_client: payment.failed — alert sent to email=%s", email)
    except Exception as exc:  # noqa: BLE001
        logger.error("dodo_client: payment.failed handler error — %s", exc)
