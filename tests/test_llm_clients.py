"""Tests for app/lib/llm_clients.py.

All external SDK calls are mocked — no real API keys required.
Patches target the getter functions (get_openai_client, get_anthropic_client,
get_gemini_model) so the singletons are bypassed cleanly per test.
"""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import openai
import pytest

from app.lib.llm_clients import (
    PARSER_SYSTEM_PROMPT,
    _PARSER_DEFAULT,
    call_claude,
    call_gemini,
    call_openai,
    call_parser,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _openai_response(text: str) -> MagicMock:
    """Build a fake openai ChatCompletion response object."""
    msg = MagicMock()
    msg.content = text
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _anthropic_response(text: str) -> MagicMock:
    """Build a fake anthropic Messages response object."""
    block = MagicMock()
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


def _gemini_response(text: str) -> MagicMock:
    """Build a fake google GenerateContentResponse object."""
    resp = MagicMock()
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# call_openai
# ---------------------------------------------------------------------------

class TestCallOpenai:
    async def test_returns_model_text(self) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_openai_response("ChatGPT says hello")
        )
        with patch("app.lib.llm_clients.get_openai_client", return_value=mock_client):
            result = await call_openai("What is Udva?")
        assert result == "ChatGPT says hello"

    async def test_passes_gpt4o_model(self) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_openai_response("ok")
        )
        with patch("app.lib.llm_clients.get_openai_client", return_value=mock_client):
            await call_openai("prompt")
        _, kwargs = mock_client.chat.completions.create.call_args
        assert kwargs["model"] == "gpt-4o"

    async def test_returns_empty_on_rate_limit(self) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=openai.RateLimitError(
                message="rate limited", response=MagicMock(), body={}
            )
        )
        with patch("app.lib.llm_clients.get_openai_client", return_value=mock_client):
            result = await call_openai("prompt")
        assert result == ""

    async def test_returns_empty_on_timeout(self) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=openai.APITimeoutError(request=MagicMock())
        )
        with patch("app.lib.llm_clients.get_openai_client", return_value=mock_client):
            result = await call_openai("prompt")
        assert result == ""

    async def test_returns_empty_on_connection_error(self) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=openai.APIConnectionError(request=MagicMock())
        )
        with patch("app.lib.llm_clients.get_openai_client", return_value=mock_client):
            result = await call_openai("prompt")
        assert result == ""

    async def test_returns_empty_on_api_status_error(self) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=openai.APIStatusError(
                message="server error",
                response=MagicMock(status_code=500),
                body={},
            )
        )
        with patch("app.lib.llm_clients.get_openai_client", return_value=mock_client):
            result = await call_openai("prompt")
        assert result == ""

    async def test_logs_error_on_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=openai.RateLimitError(
                message="rate limited", response=MagicMock(), body={}
            )
        )
        with patch("app.lib.llm_clients.get_openai_client", return_value=mock_client):
            with caplog.at_level("ERROR", logger="app.lib.llm_clients"):
                await call_openai("my prompt")
        assert "gpt-4o" in caplog.text
        assert "rate_limit" in caplog.text


# ---------------------------------------------------------------------------
# call_claude
# ---------------------------------------------------------------------------

class TestCallClaude:
    async def test_returns_model_text(self) -> None:
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            return_value=_anthropic_response("Claude says hello")
        )
        with patch("app.lib.llm_clients.get_anthropic_client", return_value=mock_client):
            result = await call_claude("What is Udva?")
        assert result == "Claude says hello"

    async def test_passes_correct_model(self) -> None:
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            return_value=_anthropic_response("ok")
        )
        with patch("app.lib.llm_clients.get_anthropic_client", return_value=mock_client):
            await call_claude("prompt")
        _, kwargs = mock_client.messages.create.call_args
        assert kwargs["model"] == "claude-sonnet-4-6"

    async def test_returns_empty_on_rate_limit(self) -> None:
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            side_effect=anthropic.RateLimitError(
                message="rate limited", response=MagicMock(), body={}
            )
        )
        with patch("app.lib.llm_clients.get_anthropic_client", return_value=mock_client):
            result = await call_claude("prompt")
        assert result == ""

    async def test_returns_empty_on_timeout(self) -> None:
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            side_effect=anthropic.APITimeoutError(request=MagicMock())
        )
        with patch("app.lib.llm_clients.get_anthropic_client", return_value=mock_client):
            result = await call_claude("prompt")
        assert result == ""

    async def test_returns_empty_on_connection_error(self) -> None:
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            side_effect=anthropic.APIConnectionError(request=MagicMock())
        )
        with patch("app.lib.llm_clients.get_anthropic_client", return_value=mock_client):
            result = await call_claude("prompt")
        assert result == ""

    async def test_returns_empty_on_api_status_error(self) -> None:
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            side_effect=anthropic.APIStatusError(
                message="bad request",
                response=MagicMock(status_code=400),
                body={},
            )
        )
        with patch("app.lib.llm_clients.get_anthropic_client", return_value=mock_client):
            result = await call_claude("prompt")
        assert result == ""

    async def test_logs_error_on_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            side_effect=anthropic.APITimeoutError(request=MagicMock())
        )
        with patch("app.lib.llm_clients.get_anthropic_client", return_value=mock_client):
            with caplog.at_level("ERROR", logger="app.lib.llm_clients"):
                await call_claude("my prompt")
        assert "claude-sonnet-4-6" in caplog.text
        assert "timeout" in caplog.text


# ---------------------------------------------------------------------------
# call_gemini
# ---------------------------------------------------------------------------

class TestCallGemini:
    async def test_returns_model_text(self) -> None:
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(
            return_value=_gemini_response("Gemini says hello")
        )
        with patch("app.lib.llm_clients.get_gemini_model", return_value=mock_model):
            result = await call_gemini("What is Udva?")
        assert result == "Gemini says hello"

    async def test_returns_empty_on_resource_exhausted(self) -> None:
        import google.api_core.exceptions as gexc

        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(
            side_effect=gexc.ResourceExhausted("quota exceeded")
        )
        with patch("app.lib.llm_clients.get_gemini_model", return_value=mock_model):
            result = await call_gemini("prompt")
        assert result == ""

    async def test_returns_empty_on_deadline_exceeded(self) -> None:
        import google.api_core.exceptions as gexc

        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(
            side_effect=gexc.DeadlineExceeded("deadline exceeded")
        )
        with patch("app.lib.llm_clients.get_gemini_model", return_value=mock_model):
            result = await call_gemini("prompt")
        assert result == ""

    async def test_returns_empty_on_service_unavailable(self) -> None:
        import google.api_core.exceptions as gexc

        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(
            side_effect=gexc.ServiceUnavailable("service down")
        )
        with patch("app.lib.llm_clients.get_gemini_model", return_value=mock_model):
            result = await call_gemini("prompt")
        assert result == ""

    async def test_returns_empty_on_generic_google_api_error(self) -> None:
        import google.api_core.exceptions as gexc

        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(
            side_effect=gexc.GoogleAPIError("unknown error")
        )
        with patch("app.lib.llm_clients.get_gemini_model", return_value=mock_model):
            result = await call_gemini("prompt")
        assert result == ""

    async def test_logs_error_on_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        import google.api_core.exceptions as gexc

        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(
            side_effect=gexc.ResourceExhausted("quota exceeded")
        )
        with patch("app.lib.llm_clients.get_gemini_model", return_value=mock_model):
            with caplog.at_level("ERROR", logger="app.lib.llm_clients"):
                await call_gemini("my prompt")
        assert "gemini-2.5-flash" in caplog.text
        assert "rate_limit" in caplog.text


# ---------------------------------------------------------------------------
# call_parser
# ---------------------------------------------------------------------------

class TestCallParser:
    async def test_returns_parsed_json(self) -> None:
        payload: dict[str, Any] = {
            "brand_mentioned": True,
            "mention_rank": 1,
            "sentiment": "positive",
            "cited_urls": ["https://example.com"],
        }
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_openai_response(json.dumps(payload))
        )
        with patch("app.lib.llm_clients.get_openai_client", return_value=mock_client):
            result = await call_parser("Some raw LLM text mentioning Udva at rank 1.")
        assert result["brand_mentioned"] is True
        assert result["mention_rank"] == 1
        assert result["sentiment"] == "positive"
        assert result["cited_urls"] == ["https://example.com"]

    async def test_uses_gpt4o_mini_model(self) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_openai_response(json.dumps(_PARSER_DEFAULT))
        )
        with patch("app.lib.llm_clients.get_openai_client", return_value=mock_client):
            await call_parser("content")
        _, kwargs = mock_client.chat.completions.create.call_args
        assert kwargs["model"] == "gpt-4o-mini"

    async def test_sends_parser_system_prompt(self) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_openai_response(json.dumps(_PARSER_DEFAULT))
        )
        with patch("app.lib.llm_clients.get_openai_client", return_value=mock_client):
            await call_parser("content")
        _, kwargs = mock_client.chat.completions.create.call_args
        messages = kwargs["messages"]
        system_msgs = [m for m in messages if m["role"] == "system"]
        assert len(system_msgs) == 1
        assert system_msgs[0]["content"] == PARSER_SYSTEM_PROMPT

    async def test_fills_missing_keys_with_defaults(self) -> None:
        """Partial JSON from the model should be merged with defaults."""
        partial: dict[str, Any] = {"brand_mentioned": True}
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_openai_response(json.dumps(partial))
        )
        with patch("app.lib.llm_clients.get_openai_client", return_value=mock_client):
            result = await call_parser("content")
        assert result["brand_mentioned"] is True
        assert result["mention_rank"] is None
        assert result["sentiment"] is None
        assert result["cited_urls"] == []

    async def test_returns_default_on_json_decode_error(self) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_openai_response("not valid json {{{{")
        )
        with patch("app.lib.llm_clients.get_openai_client", return_value=mock_client):
            result = await call_parser("content")
        assert result == _PARSER_DEFAULT

    async def test_returns_default_on_rate_limit(self) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=openai.RateLimitError(
                message="rate limited", response=MagicMock(), body={}
            )
        )
        with patch("app.lib.llm_clients.get_openai_client", return_value=mock_client):
            result = await call_parser("content")
        assert result == _PARSER_DEFAULT

    async def test_returns_default_on_timeout(self) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=openai.APITimeoutError(request=MagicMock())
        )
        with patch("app.lib.llm_clients.get_openai_client", return_value=mock_client):
            result = await call_parser("content")
        assert result == _PARSER_DEFAULT

    async def test_returns_default_on_api_status_error(self) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=openai.APIStatusError(
                message="internal server error",
                response=MagicMock(status_code=500),
                body={},
            )
        )
        with patch("app.lib.llm_clients.get_openai_client", return_value=mock_client):
            result = await call_parser("content")
        assert result == _PARSER_DEFAULT

    async def test_logs_json_decode_error(self, caplog: pytest.LogCaptureFixture) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_openai_response("definitely not json")
        )
        with patch("app.lib.llm_clients.get_openai_client", return_value=mock_client):
            with caplog.at_level("ERROR", logger="app.lib.llm_clients"):
                await call_parser("content")
        assert "json_decode_error" in caplog.text
        assert "gpt-4o-mini" in caplog.text

    async def test_not_mentioned_brand(self) -> None:
        payload: dict[str, Any] = {
            "brand_mentioned": False,
            "mention_rank": None,
            "sentiment": None,
            "cited_urls": [],
        }
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_openai_response(json.dumps(payload))
        )
        with patch("app.lib.llm_clients.get_openai_client", return_value=mock_client):
            result = await call_parser("Response that does not mention the brand at all.")
        assert result["brand_mentioned"] is False
        assert result["mention_rank"] is None


# ---------------------------------------------------------------------------
# PARSER_SYSTEM_PROMPT content check
# ---------------------------------------------------------------------------

class TestParserSystemPrompt:
    def test_contains_required_json_keys(self) -> None:
        for key in ("brand_mentioned", "mention_rank", "sentiment", "cited_urls"):
            assert key in PARSER_SYSTEM_PROMPT

    def test_instructs_json_only_output(self) -> None:
        prompt_lower = PARSER_SYSTEM_PROMPT.lower()
        assert "valid json" in prompt_lower
        assert "no markdown" in prompt_lower or "no preamble" in prompt_lower
