"""Tests for app/tasks/response_parser.py.

``call_parser`` (the network call) is mocked throughout — these tests verify
the orchestration logic in ``parse_response``, not the parser model itself.
"""

from unittest.mock import AsyncMock, patch
from typing import Any

import pytest

from app.tasks.response_parser import parse_response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FULL_PARSED: dict[str, Any] = {
    "brand_mentioned": True,
    "mention_rank": 1,
    "sentiment": "positive",
    "cited_urls": ["https://udva.io"],
}

_NOT_MENTIONED: dict[str, Any] = {
    "brand_mentioned": False,
    "mention_rank": None,
    "sentiment": None,
    "cited_urls": [],
}


# ---------------------------------------------------------------------------
# parse_response
# ---------------------------------------------------------------------------


class TestParseResponse:
    async def test_returns_parsed_result(self) -> None:
        with patch(
            "app.tasks.response_parser.call_parser", AsyncMock(return_value=_FULL_PARSED)
        ):
            result = await parse_response("Udva is the best GEO tool", "Udva")

        assert result["brand_mentioned"] is True
        assert result["mention_rank"] == 1
        assert result["sentiment"] == "positive"
        assert result["cited_urls"] == ["https://udva.io"]

    async def test_brand_name_injected_into_content(self) -> None:
        """call_parser should receive the brand name prepended to the content."""
        mock_parser = AsyncMock(return_value=_FULL_PARSED)
        with patch("app.tasks.response_parser.call_parser", mock_parser):
            await parse_response("some raw response", "MyBrand")

        call_args = mock_parser.call_args[0][0]  # first positional arg
        assert "MyBrand" in call_args
        assert "some raw response" in call_args

    async def test_empty_raw_response_skips_parser(self) -> None:
        """Empty string short-circuits before calling call_parser."""
        mock_parser = AsyncMock(return_value=_FULL_PARSED)
        with patch("app.tasks.response_parser.call_parser", mock_parser):
            result = await parse_response("", "Udva")

        mock_parser.assert_not_awaited()
        assert result["brand_mentioned"] is False
        assert result["mention_rank"] is None
        assert result["sentiment"] is None
        assert result["cited_urls"] == []

    async def test_not_mentioned_brand(self) -> None:
        with patch(
            "app.tasks.response_parser.call_parser", AsyncMock(return_value=_NOT_MENTIONED)
        ):
            result = await parse_response("Response about something else entirely.", "Udva")

        assert result["brand_mentioned"] is False
        assert result["mention_rank"] is None
        assert result["cited_urls"] == []

    async def test_parser_default_on_failure(self) -> None:
        """call_parser already returns defaults on failure — parse_response passes them through."""
        default = {
            "brand_mentioned": False,
            "mention_rank": None,
            "sentiment": None,
            "cited_urls": [],
        }
        with patch("app.tasks.response_parser.call_parser", AsyncMock(return_value=default)):
            result = await parse_response("some response", "Udva")

        assert result == default

    async def test_multiple_cited_urls(self) -> None:
        parsed = {
            "brand_mentioned": True,
            "mention_rank": 2,
            "sentiment": "neutral",
            "cited_urls": ["https://a.com", "https://b.com", "https://c.com"],
        }
        with patch("app.tasks.response_parser.call_parser", AsyncMock(return_value=parsed)):
            result = await parse_response("response with links", "Udva")

        assert len(result["cited_urls"]) == 3

    async def test_negative_sentiment(self) -> None:
        parsed = {
            "brand_mentioned": True,
            "mention_rank": 3,
            "sentiment": "negative",
            "cited_urls": [],
        }
        with patch("app.tasks.response_parser.call_parser", AsyncMock(return_value=parsed)):
            result = await parse_response("They said Udva is bad", "Udva")

        assert result["sentiment"] == "negative"
        assert result["mention_rank"] == 3

    async def test_brand_name_label_in_content(self) -> None:
        """Content passed to parser uses the 'Brand to track:' label format."""
        mock_parser = AsyncMock(return_value=_NOT_MENTIONED)
        with patch("app.tasks.response_parser.call_parser", mock_parser):
            await parse_response("some text", "Acme Corp")

        content = mock_parser.call_args[0][0]
        assert content.startswith("Brand to track: Acme Corp")

    async def test_llm_response_section_present(self) -> None:
        """Content passed to parser contains the 'LLM Response:' section."""
        mock_parser = AsyncMock(return_value=_NOT_MENTIONED)
        with patch("app.tasks.response_parser.call_parser", mock_parser):
            await parse_response("the actual llm output here", "BrandX")

        content = mock_parser.call_args[0][0]
        assert "LLM Response:" in content
        assert "the actual llm output here" in content

    async def test_logs_debug_on_success(self, caplog: pytest.LogCaptureFixture) -> None:
        with patch(
            "app.tasks.response_parser.call_parser", AsyncMock(return_value=_FULL_PARSED)
        ):
            with caplog.at_level("DEBUG", logger="app.tasks.response_parser"):
                await parse_response("response text", "Udva")

        assert "Udva" in caplog.text

    async def test_logs_info_on_empty_response(self, caplog: pytest.LogCaptureFixture) -> None:
        with patch("app.tasks.response_parser.call_parser", AsyncMock()) as mock_parser:
            with caplog.at_level("INFO", logger="app.tasks.response_parser"):
                await parse_response("", "Udva")

        mock_parser.assert_not_awaited()
        assert "empty" in caplog.text.lower()
