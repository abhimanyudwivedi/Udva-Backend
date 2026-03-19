"""Thin async wrappers around each LLM SDK used by Udva.

Clients are lazily initialised as module-level singletons so the SDK objects
are created once per process (important for Celery workers).  Every function
returns an empty / safe default on failure rather than propagating exceptions,
so callers can use ``asyncio.gather(return_exceptions=False)`` safely.
"""

import json
import logging
from typing import Any

import anthropic
import google.api_core.exceptions
import google.generativeai as genai
import openai

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Parser system prompt — verbatim from Architecture.md §5
# ---------------------------------------------------------------------------
PARSER_SYSTEM_PROMPT = """
You are a structured data extractor. Given an AI model's response to a brand search query,
extract the following and return ONLY valid JSON with no markdown, no preamble:
{
  "brand_mentioned": true | false,
  "mention_rank": 1 (first brand mentioned) | 2 | null (not mentioned),
  "sentiment": "positive" | "neutral" | "negative" | null,
  "cited_urls": ["https://..."]
}
""".strip()

# Safe default returned by call_parser on any failure
_PARSER_DEFAULT: dict[str, Any] = {
    "brand_mentioned": False,
    "mention_rank": None,
    "sentiment": None,
    "cited_urls": [],
}

# ---------------------------------------------------------------------------
# Lazy client singletons
# ---------------------------------------------------------------------------
_openai_client: openai.AsyncOpenAI | None = None
_anthropic_client: anthropic.AsyncAnthropic | None = None


def get_openai_client() -> openai.AsyncOpenAI:
    """Return (or create) the module-level AsyncOpenAI singleton."""
    global _openai_client
    if _openai_client is None:
        _openai_client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


def get_anthropic_client() -> anthropic.AsyncAnthropic:
    """Return (or create) the module-level AsyncAnthropic singleton."""
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _anthropic_client


def get_gemini_model() -> genai.GenerativeModel:
    """Configure the Google AI SDK and return a GenerativeModel instance.

    ``genai.configure`` is idempotent — safe to call on every request.
    """
    genai.configure(api_key=settings.GOOGLE_AI_API_KEY)
    return genai.GenerativeModel("gemini-2.5-flash")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def call_openai(prompt: str) -> str:
    """Send *prompt* to GPT-4o and return the text response.

    Returns an empty string if the API call fails for any reason, so the
    caller can treat a missing result as "no response from this model" rather
    than a hard crash.

    Args:
        prompt: The user-facing prompt to send to the model.

    Returns:
        The model's text reply, or ``""`` on error.
    """
    client = get_openai_client()
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""
    except openai.RateLimitError as exc:
        logger.error("openai rate_limit model=gpt-4o prompt_len=%d: %s", len(prompt), exc)
    except openai.APITimeoutError as exc:
        logger.error("openai timeout model=gpt-4o prompt_len=%d: %s", len(prompt), exc)
    except openai.APIConnectionError as exc:
        logger.error("openai connection_error model=gpt-4o prompt_len=%d: %s", len(prompt), exc)
    except openai.APIStatusError as exc:
        logger.error(
            "openai api_error status=%d model=gpt-4o prompt_len=%d: %s",
            exc.status_code,
            len(prompt),
            exc,
        )
    return ""


async def call_claude(prompt: str) -> str:
    """Send *prompt* to Claude Sonnet 4.6 and return the text response.

    Returns an empty string on any API failure.

    Args:
        prompt: The user-facing prompt to send to the model.

    Returns:
        The model's text reply, or ``""`` on error.
    """
    client = get_anthropic_client()
    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        # response.content is a list of ContentBlock; first block is always text
        first_block = response.content[0]
        return first_block.text if hasattr(first_block, "text") else ""
    except anthropic.RateLimitError as exc:
        logger.error(
            "anthropic rate_limit model=claude-sonnet-4-6 prompt_len=%d: %s", len(prompt), exc
        )
    except anthropic.APITimeoutError as exc:
        logger.error(
            "anthropic timeout model=claude-sonnet-4-6 prompt_len=%d: %s", len(prompt), exc
        )
    except anthropic.APIConnectionError as exc:
        logger.error(
            "anthropic connection_error model=claude-sonnet-4-6 prompt_len=%d: %s", len(prompt), exc
        )
    except anthropic.APIStatusError as exc:
        logger.error(
            "anthropic api_error status=%d model=claude-sonnet-4-6 prompt_len=%d: %s",
            exc.status_code,
            len(prompt),
            exc,
        )
    return ""


async def call_gemini(prompt: str) -> str:
    """Send *prompt* to Gemini 2.5 Flash and return the text response.

    Returns an empty string on any API failure.

    Args:
        prompt: The user-facing prompt to send to the model.

    Returns:
        The model's text reply, or ``""`` on error.
    """
    model = get_gemini_model()
    try:
        response = await model.generate_content_async(prompt)
        return response.text
    except google.api_core.exceptions.ResourceExhausted as exc:
        logger.error(
            "gemini rate_limit model=gemini-2.5-flash prompt_len=%d: %s", len(prompt), exc
        )
    except google.api_core.exceptions.DeadlineExceeded as exc:
        logger.error(
            "gemini timeout model=gemini-2.5-flash prompt_len=%d: %s", len(prompt), exc
        )
    except google.api_core.exceptions.ServiceUnavailable as exc:
        logger.error(
            "gemini unavailable model=gemini-2.5-flash prompt_len=%d: %s", len(prompt), exc
        )
    except google.api_core.exceptions.GoogleAPIError as exc:
        logger.error(
            "gemini api_error model=gemini-2.5-flash prompt_len=%d: %s", len(prompt), exc
        )
    return ""


async def call_parser(content: str) -> dict[str, Any]:
    """Extract structured brand-mention data from a raw LLM response.

    Sends *content* (the raw text from one of the visibility-tracking models)
    to GPT-4o-mini with the ``PARSER_SYSTEM_PROMPT``.  The model is instructed
    to return only valid JSON matching the schema below.

    Schema:
        ``brand_mentioned`` (bool): Whether the brand appeared in the response.
        ``mention_rank`` (int | None): 1-based position of first mention, or None.
        ``sentiment`` (str | None): "positive" | "neutral" | "negative" | None.
        ``cited_urls`` (list[str]): URLs the model cited.

    Returns ``_PARSER_DEFAULT`` on any error (API failure *or* malformed JSON)
    so the caller always receives a well-typed dict.

    Args:
        content: The raw LLM response text to parse.

    Returns:
        Parsed dict with keys brand_mentioned, mention_rank, sentiment, cited_urls.
    """
    client = get_openai_client()
    raw: str = "{}"
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": PARSER_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        parsed: dict[str, Any] = json.loads(raw)
        # Ensure all expected keys are present; fill missing ones with defaults
        return {**_PARSER_DEFAULT, **parsed}
    except json.JSONDecodeError as exc:
        logger.error(
            "parser json_decode_error model=gpt-4o-mini content_len=%d raw=%.200r: %s",
            len(content),
            raw,
            exc,
        )
    except openai.RateLimitError as exc:
        logger.error("parser rate_limit model=gpt-4o-mini content_len=%d: %s", len(content), exc)
    except openai.APITimeoutError as exc:
        logger.error("parser timeout model=gpt-4o-mini content_len=%d: %s", len(content), exc)
    except openai.APIConnectionError as exc:
        logger.error(
            "parser connection_error model=gpt-4o-mini content_len=%d: %s", len(content), exc
        )
    except openai.APIStatusError as exc:
        logger.error(
            "parser api_error status=%d model=gpt-4o-mini content_len=%d: %s",
            exc.status_code,
            len(content),
            exc,
        )
    return _PARSER_DEFAULT.copy()
