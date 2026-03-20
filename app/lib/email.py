"""Resend transactional email helper — alert emails for Pillar 2.

All functions swallow exceptions and log instead of raising, because email
alerts are non-critical.  A failed alert should never break the crawl pipeline.
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"
_TIMEOUT = 10.0


def _build_alert_html(
    brand_name: str,
    mention_title: str,
    mention_url: str,
    relevance_score: int,
) -> str:
    """Return a minimal HTML email body for a new mention alert."""
    score_color = "#16a34a" if relevance_score >= 80 else "#ca8a04" if relevance_score >= 60 else "#dc2626"
    return f"""
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"></head>
<body style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; color: #1f2937;">
  <h1 style="font-size: 20px; margin-bottom: 4px;">New mention detected</h1>
  <p style="color: #6b7280; margin-top: 0;">Brand: <strong style="color: #1f2937;">{brand_name}</strong></p>

  <div style="border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; margin: 24px 0;">
    <p style="font-weight: 600; margin: 0 0 8px;">{mention_title}</p>
    <a href="{mention_url}" style="color: #4f46e5; word-break: break-all;">{mention_url}</a>
  </div>

  <p style="margin: 0;">
    Relevance score:
    <strong style="color: {score_color}; font-size: 18px;">{relevance_score}/100</strong>
  </p>

  <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;">
  <p style="color: #9ca3af; font-size: 12px;">
    You're receiving this because you have mention alerts enabled on
    <a href="https://app.udva.net" style="color: #9ca3af;">Udva</a>.
  </p>
</body>
</html>
""".strip()


async def send_alert_email(
    to: str,
    brand_name: str,
    mention_title: str,
    mention_url: str,
    relevance_score: int,
) -> None:
    """Send a mention alert email via the Resend API.

    Never raises — all errors are logged and swallowed so that a transient
    email failure does not interrupt the crawl pipeline.

    Args:
        to:              Recipient email address (the brand owner).
        brand_name:      Display name of the brand for the email body.
        mention_title:   Title of the social post (or URL as fallback).
        mention_url:     Direct link to the mention.
        relevance_score: 0–100 score for the mention.
    """
    subject = f"[Udva] New mention of {brand_name} — score {relevance_score}/100"
    html = _build_alert_html(brand_name, mention_title, mention_url, relevance_score)

    payload = {
        "from": settings.EMAIL_FROM,
        "to": [to],
        "subject": subject,
        "html": html,
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                _RESEND_URL,
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json=payload,
            )
            response.raise_for_status()

        logger.info(
            "email: sent alert to=%s brand=%s score=%d",
            to,
            brand_name,
            relevance_score,
        )

    except httpx.HTTPStatusError as exc:
        logger.error(
            "email: HTTP %d from Resend for to=%s — %s",
            exc.response.status_code,
            to,
            exc,
        )
    except httpx.RequestError as exc:
        logger.error("email: network error sending to=%s — %s", to, exc)
    except Exception as exc:  # noqa: BLE001
        logger.error("email: unexpected error sending to=%s — %s", to, exc)
