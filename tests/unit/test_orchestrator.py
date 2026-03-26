"""Unit tests for ReviewOrchestrator."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.config import Config
from src.exceptions import (
    AllFilesExcludedError,
    CommentWriteBackError,
    EmptyDiffError,
)
from src.models import (
    FilterResult,
    PRInfo,
    ReviewDiffReport,
    ReviewIssue,
    ReviewOptions,
    ReviewRecord,
    ReviewResult,
)
from src.orchestrator import ReviewOrchestrator


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture()
def config():
    return Config(
        github_token="fake-token",
        llm_api_key="fake-key",
        llm_model="gpt-4",
        review_storage_dir="/tmp/test_reviews",
    )


@pytest.fixture()
def pr_url():
    return "https://github.com/owner/repo/pull/1"


@pytest.fixture()
def pr_info():
    return PRInfo(
        platform="github",
        pr_id="owner/repo#1",
        pr_url="https://github.com/owner/repo/pull/1",
        title="Fix bug",
        description="Fixes a critical bug",
        diff="diff --git a/foo.py b/foo.py\n+hello\n",
        source_branch="fix",
        target_branch="main",
        author="dev",
        version_id="abc123",
    )


@pytest.fixture()
def review_result():
    return ReviewResult(
        summary="Looks good",
        issues=[
            ReviewIssue(
                file_path="foo.py",
                line_number=1,
                severity="suggestion",
                category="quality",
                description="Minor style issue",
                suggestion="Use snake_case",
            )
        ],
        reviewed_at=datetime.now(timezone.utc).isoformat(),
    )


@pytest.fixture()
def filter_result():
    return FilterResult(
        filtered_diff="diff --git a/foo.py b/foo.py\n+hello\n",
        excluded_files=[],
        included_file_count=1,
        excluded_file_count=0,
    )


@pytest.fixture()
def options():
    return ReviewOptions(write_back=True)


# ── Tests ─────────────────────────────────────────────────


class TestReviewOrchestratorRun:
    """Tests for the happy-path and error flows."""

    @patch("src.orchestrator.PlatformFactory")
    @patch.object(ReviewOrchestrator, "__init__", lambda self, cfg: None)
    def _build(self, mock_factory, config, pr_info, review_result, filter_result):
        """Helper: build an orchestrator with all deps mocked."""
        orch = ReviewOrchestrator.__new__(ReviewOrchestrator)
        orch._config = config

        orch._ai_reviewer = MagicMock()
        orch._ai_reviewer.review.return_value = review_result

        orch._template_engine = MagicMock()
        orch._template_engine.render.return_value = "# Review"

        orch._diff_comparator = MagicMock()
        orch._record_store = MagicMock()
        orch._record_store.get_latest.return_value = None
        orch._file_filter = MagicMock()

        adapter = MagicMock()
        adapter.fetch_pr_info.return_value = pr_info
        mock_factory.create_adapter.return_value = adapter
        mock_factory.detect_platform.return_value = "github"

        return orch, adapter, mock_factory

    @patch("src.orchestrator.FileFilter")
    @patch("src.orchestrator.PlatformFactory")
    @patch.object(ReviewOrchestrator, "__init__", lambda self, cfg: None)
    def test_happy_path(
        self,
        mock_factory,
        mock_filter_cls,
        config,
        pr_info,
        review_result,
        filter_result,
        options,
    ):
        orch = ReviewOrchestrator.__new__(ReviewOrchestrator)
        orch._config = config
        orch._ai_reviewer = MagicMock()
        orch._ai_reviewer.review.return_value = review_result
        orch._template_engine = MagicMock()
        orch._template_engine.render.return_value = "# Review"
        orch._diff_comparator = MagicMock()
        orch._record_store = MagicMock()
        orch._record_store.get_latest.return_value = None

        adapter = MagicMock()
        adapter.fetch_pr_info.return_value = pr_info
        mock_factory.create_adapter.return_value = adapter
        mock_factory.detect_platform.return_value = "github"

        mock_filter_cls.load_patterns_from_config.return_value = []
        mock_filter_cls.load_patterns_from_env.return_value = []
        ff_instance = MagicMock()
        ff_instance.filter_diff.return_value = filter_result
        mock_filter_cls.return_value = ff_instance

        output = orch.run(pr_url="https://github.com/owner/repo/pull/1", options=options)

        assert output.review_result is review_result
        assert output.diff_report is None
        assert output.formatted_comment == "# Review"
        assert output.written_back is True
        adapter.post_comment.assert_called_once()
        orch._record_store.save.assert_called_once()

    @patch("src.orchestrator.FileFilter")
    @patch("src.orchestrator.PlatformFactory")
    @patch.object(ReviewOrchestrator, "__init__", lambda self, cfg: None)
    def test_all_files_excluded_raises(
        self,
        mock_factory,
        mock_filter_cls,
        config,
        pr_info,
        options,
    ):
        orch = ReviewOrchestrator.__new__(ReviewOrchestrator)
        orch._config = config
        orch._ai_reviewer = MagicMock()
        orch._template_engine = MagicMock()
        orch._diff_comparator = MagicMock()
        orch._record_store = MagicMock()

        adapter = MagicMock()
        adapter.fetch_pr_info.return_value = pr_info
        mock_factory.create_adapter.return_value = adapter
        mock_factory.detect_platform.return_value = "github"

        mock_filter_cls.load_patterns_from_config.return_value = []
        mock_filter_cls.load_patterns_from_env.return_value = []
        ff_instance = MagicMock()
        ff_instance.filter_diff.return_value = FilterResult(
            filtered_diff="",
            excluded_files=[{"file_path": "foo.lock", "matched_pattern": "*.lock"}],
            included_file_count=0,
            excluded_file_count=1,
        )
        mock_filter_cls.return_value = ff_instance

        with pytest.raises(AllFilesExcludedError):
            orch.run(pr_url="https://github.com/owner/repo/pull/1", options=options)

    @patch("src.orchestrator.FileFilter")
    @patch("src.orchestrator.PlatformFactory")
    @patch.object(ReviewOrchestrator, "__init__", lambda self, cfg: None)
    def test_empty_diff_raises(
        self,
        mock_factory,
        mock_filter_cls,
        config,
        pr_info,
        options,
    ):
        orch = ReviewOrchestrator.__new__(ReviewOrchestrator)
        orch._config = config
        orch._ai_reviewer = MagicMock()
        orch._template_engine = MagicMock()
        orch._diff_comparator = MagicMock()
        orch._record_store = MagicMock()

        pr_info.diff = ""
        adapter = MagicMock()
        adapter.fetch_pr_info.return_value = pr_info
        mock_factory.create_adapter.return_value = adapter
        mock_factory.detect_platform.return_value = "github"

        mock_filter_cls.load_patterns_from_config.return_value = []
        mock_filter_cls.load_patterns_from_env.return_value = []
        ff_instance = MagicMock()
        ff_instance.filter_diff.return_value = FilterResult(
            filtered_diff="",
            excluded_files=[],
            included_file_count=0,
            excluded_file_count=0,
        )
        mock_filter_cls.return_value = ff_instance

        with pytest.raises(EmptyDiffError):
            orch.run(pr_url="https://github.com/owner/repo/pull/1", options=options)

    @patch("src.orchestrator.FileFilter")
    @patch("src.orchestrator.PlatformFactory")
    @patch.object(ReviewOrchestrator, "__init__", lambda self, cfg: None)
    def test_write_back_failure_does_not_raise(
        self,
        mock_factory,
        mock_filter_cls,
        config,
        pr_info,
        review_result,
        filter_result,
        options,
    ):
        orch = ReviewOrchestrator.__new__(ReviewOrchestrator)
        orch._config = config
        orch._ai_reviewer = MagicMock()
        orch._ai_reviewer.review.return_value = review_result
        orch._template_engine = MagicMock()
        orch._template_engine.render.return_value = "# Review"
        orch._diff_comparator = MagicMock()
        orch._record_store = MagicMock()
        orch._record_store.get_latest.return_value = None

        adapter = MagicMock()
        adapter.fetch_pr_info.return_value = pr_info
        adapter.post_comment.side_effect = CommentWriteBackError("fail")
        mock_factory.create_adapter.return_value = adapter
        mock_factory.detect_platform.return_value = "github"

        mock_filter_cls.load_patterns_from_config.return_value = []
        mock_filter_cls.load_patterns_from_env.return_value = []
        ff_instance = MagicMock()
        ff_instance.filter_diff.return_value = filter_result
        mock_filter_cls.return_value = ff_instance

        output = orch.run(pr_url="https://github.com/owner/repo/pull/1", options=options)

        assert output.written_back is False
        assert output.review_result is review_result

    @patch("src.orchestrator.FileFilter")
    @patch("src.orchestrator.PlatformFactory")
    @patch.object(ReviewOrchestrator, "__init__", lambda self, cfg: None)
    def test_no_write_back_option(
        self,
        mock_factory,
        mock_filter_cls,
        config,
        pr_info,
        review_result,
        filter_result,
    ):
        options = ReviewOptions(write_back=False)

        orch = ReviewOrchestrator.__new__(ReviewOrchestrator)
        orch._config = config
        orch._ai_reviewer = MagicMock()
        orch._ai_reviewer.review.return_value = review_result
        orch._template_engine = MagicMock()
        orch._template_engine.render.return_value = "# Review"
        orch._diff_comparator = MagicMock()
        orch._record_store = MagicMock()
        orch._record_store.get_latest.return_value = None

        adapter = MagicMock()
        adapter.fetch_pr_info.return_value = pr_info
        mock_factory.create_adapter.return_value = adapter
        mock_factory.detect_platform.return_value = "github"

        mock_filter_cls.load_patterns_from_config.return_value = []
        mock_filter_cls.load_patterns_from_env.return_value = []
        ff_instance = MagicMock()
        ff_instance.filter_diff.return_value = filter_result
        mock_filter_cls.return_value = ff_instance

        output = orch.run(pr_url="https://github.com/owner/repo/pull/1", options=options)

        assert output.written_back is False
        adapter.post_comment.assert_not_called()

    @patch("src.orchestrator.FileFilter")
    @patch("src.orchestrator.PlatformFactory")
    @patch.object(ReviewOrchestrator, "__init__", lambda self, cfg: None)
    def test_diff_report_generated_when_previous_exists(
        self,
        mock_factory,
        mock_filter_cls,
        config,
        pr_info,
        review_result,
        filter_result,
        options,
    ):
        prev_result = ReviewResult(
            summary="Old review",
            issues=[],
            reviewed_at="2024-01-01T00:00:00+00:00",
        )
        prev_record = ReviewRecord(
            record_id="prev-uuid",
            pr_id="owner/repo#1",
            pr_url="https://github.com/owner/repo/pull/1",
            platform="github",
            version_id="old123",
            review_result=prev_result,
            diff_report=None,
            created_at="2024-01-01T00:00:00+00:00",
        )
        diff_report = ReviewDiffReport(
            improved=[], unresolved=[], new_issues=[]
        )

        orch = ReviewOrchestrator.__new__(ReviewOrchestrator)
        orch._config = config
        orch._ai_reviewer = MagicMock()
        orch._ai_reviewer.review.return_value = review_result
        orch._template_engine = MagicMock()
        orch._template_engine.render.return_value = "# Review"
        orch._diff_comparator = MagicMock()
        orch._diff_comparator.compare.return_value = diff_report
        orch._record_store = MagicMock()
        orch._record_store.get_latest.return_value = prev_record

        adapter = MagicMock()
        adapter.fetch_pr_info.return_value = pr_info
        mock_factory.create_adapter.return_value = adapter
        mock_factory.detect_platform.return_value = "github"

        mock_filter_cls.load_patterns_from_config.return_value = []
        mock_filter_cls.load_patterns_from_env.return_value = []
        ff_instance = MagicMock()
        ff_instance.filter_diff.return_value = filter_result
        mock_filter_cls.return_value = ff_instance

        output = orch.run(pr_url="https://github.com/owner/repo/pull/1", options=options)

        assert output.diff_report is diff_report
        orch._diff_comparator.compare.assert_called_once_with(
            prev_result, review_result
        )

    @patch("src.orchestrator.FileFilter")
    @patch("src.orchestrator.PlatformFactory")
    @patch.object(ReviewOrchestrator, "__init__", lambda self, cfg: None)
    def test_exclude_patterns_merged(
        self,
        mock_factory,
        mock_filter_cls,
        config,
        pr_info,
        review_result,
        filter_result,
    ):
        options = ReviewOptions(
            exclude_patterns=["*.log"],
            write_back=False,
        )

        orch = ReviewOrchestrator.__new__(ReviewOrchestrator)
        orch._config = config
        orch._ai_reviewer = MagicMock()
        orch._ai_reviewer.review.return_value = review_result
        orch._template_engine = MagicMock()
        orch._template_engine.render.return_value = "# Review"
        orch._diff_comparator = MagicMock()
        orch._record_store = MagicMock()
        orch._record_store.get_latest.return_value = None

        adapter = MagicMock()
        adapter.fetch_pr_info.return_value = pr_info
        mock_factory.create_adapter.return_value = adapter
        mock_factory.detect_platform.return_value = "github"

        mock_filter_cls.load_patterns_from_config.return_value = ["*.min.js"]
        mock_filter_cls.load_patterns_from_env.return_value = ["*.csv"]
        ff_instance = MagicMock()
        ff_instance.filter_diff.return_value = filter_result
        mock_filter_cls.return_value = ff_instance

        orch.run(pr_url="https://github.com/owner/repo/pull/1", options=options)

        call_kwargs = mock_filter_cls.call_args
        patterns = call_kwargs[1].get("exclude_patterns") or call_kwargs[0][0]
        assert "*.log" in patterns
        assert "*.min.js" in patterns
        assert "*.csv" in patterns
