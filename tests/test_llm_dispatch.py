"""Tests for app/tasks/llm_dispatch.py — dispatch_to_llms and Celery tasks.

All LLM SDK calls are mocked.  The Celery tasks are tested by patching the
async pipeline helpers so no real DB or network I/O occurs.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks.llm_dispatch import DEFAULT_MODELS, dispatch_to_llms


# ---------------------------------------------------------------------------
# dispatch_to_llms
# ---------------------------------------------------------------------------


class TestDispatchToLlms:
    async def test_all_models_succeed(self) -> None:
        """All three callers return text → three dicts returned."""
        with (
            patch("app.tasks.llm_dispatch.call_openai", AsyncMock(return_value="openai resp")),
            patch("app.tasks.llm_dispatch.call_claude", AsyncMock(return_value="claude resp")),
            patch("app.tasks.llm_dispatch.call_gemini", AsyncMock(return_value="gemini resp")),
        ):
            results = await dispatch_to_llms("What is Udva?")

        assert len(results) == 3
        models = {r["model"] for r in results}
        assert models == {"gpt-4o", "claude-sonnet-4-6", "gemini-2.5-flash"}
        responses = {r["raw_response"] for r in results}
        assert responses == {"openai resp", "claude resp", "gemini resp"}

    async def test_partial_failure_one_empty(self) -> None:
        """One model returns '' (failure) → only two results returned."""
        with (
            patch("app.tasks.llm_dispatch.call_openai", AsyncMock(return_value="openai resp")),
            patch("app.tasks.llm_dispatch.call_claude", AsyncMock(return_value="")),
            patch("app.tasks.llm_dispatch.call_gemini", AsyncMock(return_value="gemini resp")),
        ):
            results = await dispatch_to_llms("prompt")

        assert len(results) == 2
        models = {r["model"] for r in results}
        assert "claude-sonnet-4-6" not in models
        assert "gpt-4o" in models
        assert "gemini-2.5-flash" in models

    async def test_partial_failure_exception_swallowed(self) -> None:
        """Unexpected exception from a caller is caught → still returns others."""
        with (
            patch("app.tasks.llm_dispatch.call_openai", AsyncMock(return_value="openai resp")),
            patch(
                "app.tasks.llm_dispatch.call_claude",
                AsyncMock(side_effect=RuntimeError("unexpected")),
            ),
            patch("app.tasks.llm_dispatch.call_gemini", AsyncMock(return_value="gemini resp")),
        ):
            results = await dispatch_to_llms("prompt")

        assert len(results) == 2
        models = {r["model"] for r in results}
        assert "claude-sonnet-4-6" not in models

    async def test_all_models_fail_returns_empty_list(self) -> None:
        with (
            patch("app.tasks.llm_dispatch.call_openai", AsyncMock(return_value="")),
            patch("app.tasks.llm_dispatch.call_claude", AsyncMock(return_value="")),
            patch("app.tasks.llm_dispatch.call_gemini", AsyncMock(return_value="")),
        ):
            results = await dispatch_to_llms("prompt")

        assert results == []

    async def test_custom_model_subset(self) -> None:
        """Caller can restrict to a subset of models."""
        with (
            patch("app.tasks.llm_dispatch.call_openai", AsyncMock(return_value="openai resp")),
            patch("app.tasks.llm_dispatch.call_claude", AsyncMock(return_value="claude resp")),
        ):
            results = await dispatch_to_llms("prompt", models=["gpt-4o", "claude-sonnet-4-6"])

        assert len(results) == 2
        assert {r["model"] for r in results} == {"gpt-4o", "claude-sonnet-4-6"}

    async def test_unknown_model_skipped(self) -> None:
        """Unknown model name is logged and skipped; valid models still run."""
        with patch("app.tasks.llm_dispatch.call_openai", AsyncMock(return_value="openai resp")):
            results = await dispatch_to_llms("prompt", models=["gpt-4o", "does-not-exist"])

        assert len(results) == 1
        assert results[0]["model"] == "gpt-4o"

    async def test_all_unknown_models_returns_empty(self) -> None:
        results = await dispatch_to_llms("prompt", models=["fake-model-1", "fake-model-2"])
        assert results == []

    async def test_result_structure(self) -> None:
        """Each result dict has exactly 'model' and 'raw_response' keys."""
        with (
            patch("app.tasks.llm_dispatch.call_openai", AsyncMock(return_value="resp")),
            patch("app.tasks.llm_dispatch.call_claude", AsyncMock(return_value="")),
            patch("app.tasks.llm_dispatch.call_gemini", AsyncMock(return_value="")),
        ):
            results = await dispatch_to_llms("prompt")

        assert len(results) == 1
        assert set(results[0].keys()) == {"model", "raw_response"}

    async def test_default_models_constant(self) -> None:
        """DEFAULT_MODELS contains exactly the three expected identifiers."""
        assert set(DEFAULT_MODELS) == {"gpt-4o", "claude-sonnet-4-6", "gemini-2.5-flash"}

    async def test_logs_warning_on_empty_response(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with (
            patch("app.tasks.llm_dispatch.call_openai", AsyncMock(return_value="")),
            patch("app.tasks.llm_dispatch.call_claude", AsyncMock(return_value="ok")),
            patch("app.tasks.llm_dispatch.call_gemini", AsyncMock(return_value="")),
        ):
            with caplog.at_level("WARNING", logger="app.tasks.llm_dispatch"):
                await dispatch_to_llms("prompt")

        assert "empty response" in caplog.text


# ---------------------------------------------------------------------------
# run_brand_visibility (Celery task — sync wrapper)
# ---------------------------------------------------------------------------


class TestRunBrandVisibility:
    def test_calls_async_pipeline(self) -> None:
        """The Celery task drives _run_brand_visibility_async via asyncio.run."""
        from app.tasks.llm_dispatch import run_brand_visibility

        with patch(
            "app.tasks.llm_dispatch._run_brand_visibility_async",
            return_value=None,
        ) as mock_async:
            with patch("asyncio.run") as mock_run:
                run_brand_visibility("test-brand-id")

            mock_run.assert_called_once()
            # Verify the coroutine passed to asyncio.run is from our helper
            args = mock_run.call_args[0]
            assert args  # a coroutine was passed

    def test_no_exception_on_empty_brand_id(self) -> None:
        """Task should not raise even if the pipeline finds nothing to do."""
        from app.tasks.llm_dispatch import run_brand_visibility

        async def _noop(_: str) -> None:
            return None

        with patch("app.tasks.llm_dispatch._run_brand_visibility_async", side_effect=_noop):
            with patch("asyncio.run"):
                # Should not raise
                run_brand_visibility("00000000-0000-0000-0000-000000000000")


# ---------------------------------------------------------------------------
# run_all_active_brands (Celery task — sync wrapper)
# ---------------------------------------------------------------------------


class TestRunAllActiveBrands:
    def test_calls_async_fan_out(self) -> None:
        from app.tasks.llm_dispatch import run_all_active_brands

        with patch("asyncio.run") as mock_run:
            run_all_active_brands()

        mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# _run_brand_visibility_async — integration-style unit test
# ---------------------------------------------------------------------------


class TestRunBrandVisibilityAsync:
    async def test_full_pipeline_one_query_one_model(self) -> None:
        """Single query + single model response → write_score and no citations."""
        from app.tasks.llm_dispatch import _run_brand_visibility_async

        mock_queries = [
            {"query_id": "qid-1", "brand_name": "Udva", "prompt_text": "What is Udva?"}
        ]
        mock_dispatches = [{"model": "gpt-4o", "raw_response": "Udva is great"}]
        mock_parsed = {
            "brand_mentioned": True,
            "mention_rank": 1,
            "sentiment": "positive",
            "cited_urls": [],
        }

        mock_db = MagicMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)
        mock_db.commit = AsyncMock()

        with (
            patch("app.tasks.llm_dispatch.AsyncSessionLocal", return_value=mock_db),
            patch("app.tasks.llm_dispatch.build_queries", AsyncMock(return_value=mock_queries)),
            patch(
                "app.tasks.llm_dispatch.dispatch_to_llms", AsyncMock(return_value=mock_dispatches)
            ),
            patch(
                "app.tasks.llm_dispatch.parse_response", AsyncMock(return_value=mock_parsed)
            ),
            patch("app.tasks.llm_dispatch.write_score", AsyncMock()) as mock_write,
            patch(
                "app.tasks.llm_dispatch.extract_citations", AsyncMock()
            ) as mock_citations,
        ):
            await _run_brand_visibility_async("brand-1")

        mock_write.assert_awaited_once()
        mock_citations.assert_not_awaited()  # cited_urls was empty
        mock_db.commit.assert_awaited_once()

    async def test_citations_called_when_urls_present(self) -> None:
        from app.tasks.llm_dispatch import _run_brand_visibility_async

        mock_queries = [
            {"query_id": "qid-1", "brand_name": "Udva", "prompt_text": "prompt"}
        ]
        mock_dispatches = [{"model": "gpt-4o", "raw_response": "resp"}]
        mock_parsed = {
            "brand_mentioned": True,
            "mention_rank": 1,
            "sentiment": "positive",
            "cited_urls": ["https://udva.net", "https://example.com"],
        }

        mock_db = MagicMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)
        mock_db.commit = AsyncMock()

        with (
            patch("app.tasks.llm_dispatch.AsyncSessionLocal", return_value=mock_db),
            patch("app.tasks.llm_dispatch.build_queries", AsyncMock(return_value=mock_queries)),
            patch(
                "app.tasks.llm_dispatch.dispatch_to_llms", AsyncMock(return_value=mock_dispatches)
            ),
            patch(
                "app.tasks.llm_dispatch.parse_response", AsyncMock(return_value=mock_parsed)
            ),
            patch("app.tasks.llm_dispatch.write_score", AsyncMock()),
            patch(
                "app.tasks.llm_dispatch.extract_citations", AsyncMock()
            ) as mock_citations,
        ):
            await _run_brand_visibility_async("brand-1")

        mock_citations.assert_awaited_once()
        call_kwargs = mock_citations.call_args.kwargs
        assert call_kwargs["urls"] == ["https://udva.net", "https://example.com"]

    async def test_no_queries_skips_pipeline(self) -> None:
        from app.tasks.llm_dispatch import _run_brand_visibility_async

        mock_db = MagicMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)
        mock_db.commit = AsyncMock()

        with (
            patch("app.tasks.llm_dispatch.AsyncSessionLocal", return_value=mock_db),
            patch("app.tasks.llm_dispatch.build_queries", AsyncMock(return_value=[])),
            patch(
                "app.tasks.llm_dispatch.dispatch_to_llms", AsyncMock()
            ) as mock_dispatch,
        ):
            await _run_brand_visibility_async("brand-no-queries")

        mock_dispatch.assert_not_awaited()
        mock_db.commit.assert_not_awaited()

    async def test_multiple_queries_all_processed(self) -> None:
        from app.tasks.llm_dispatch import _run_brand_visibility_async

        mock_queries = [
            {"query_id": f"qid-{i}", "brand_name": "Udva", "prompt_text": f"prompt {i}"}
            for i in range(3)
        ]
        mock_dispatches = [{"model": "gpt-4o", "raw_response": "resp"}]
        mock_parsed = {
            "brand_mentioned": False,
            "mention_rank": None,
            "sentiment": None,
            "cited_urls": [],
        }

        mock_db = MagicMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)
        mock_db.commit = AsyncMock()

        with (
            patch("app.tasks.llm_dispatch.AsyncSessionLocal", return_value=mock_db),
            patch("app.tasks.llm_dispatch.build_queries", AsyncMock(return_value=mock_queries)),
            patch(
                "app.tasks.llm_dispatch.dispatch_to_llms", AsyncMock(return_value=mock_dispatches)
            ),
            patch("app.tasks.llm_dispatch.parse_response", AsyncMock(return_value=mock_parsed)),
            patch("app.tasks.llm_dispatch.write_score", AsyncMock()) as mock_write,
            patch("app.tasks.llm_dispatch.extract_citations", AsyncMock()),
        ):
            await _run_brand_visibility_async("brand-1")

        # 3 queries × 1 model = 3 write_score calls
        assert mock_write.await_count == 3
