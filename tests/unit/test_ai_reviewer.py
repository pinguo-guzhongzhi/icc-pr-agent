"""Unit tests for AIReviewer."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.ai_reviewer import AIReviewer
from src.config import Config
from src.exceptions import AIModelError, EmptyDiffError
from src.models import PRInfo


def _config(**overrides) -> Config:
    defaults = dict(
        llm_api_key="test-key",
        llm_model="gpt-4",
        llm_base_url="https://api.example.com/v1",
    )
    defaults.update(overrides)
    return Config(**defaults)


def _pr_info(**overrides) -> PRInfo:
    defaults = dict(
        platform="github",
        pr_id="42",
        pr_url="https://github.com/owner/repo/pull/42",
        title="Add user auth",
        description="Implements JWT authentication",
        diff=(
            "diff --git a/auth.py b/auth.py\n"
            "--- a/auth.py\n"
            "+++ b/auth.py\n"
            "@@ -1,3 +1,5 @@\n"
            " import os\n"
            "+import jwt\n"
            "+\n"
            " def login():\n"
            "     pass\n"
        ),
        source_branch="feature/auth",
        target_branch="main",
        author="dev",
        version_id="abc123",
    )
    defaults.update(overrides)
    return PRInfo(**defaults)


_VALID_LLM_JSON = json.dumps(
    {
        "summary": "代码整体质量良好，发现1个潜在问题",
        "issues": [
            {
                "file_path": "auth.py",
                "line_number": 2,
                "severity": "warning",
                "category": "security",
                "description": "JWT secret 应从环境变量读取",
                "suggestion": "使用 os.environ.get('JWT_SECRET')",
            }
        ],
    }
)


class TestAIReviewer:
    """Tests for AIReviewer."""

    @patch("src.ai_reviewer.ChatOpenAI")
    def test_review_normal_flow(self, mock_chat_cls) -> None:
        """Mock LLM returns valid JSON → ReviewResult is correct."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = _VALID_LLM_JSON
        mock_llm.invoke.return_value = mock_response
        mock_chat_cls.return_value = mock_llm

        reviewer = AIReviewer(_config())
        result = reviewer.review(_pr_info())

        assert result.summary == "代码整体质量良好，发现1个潜在问题"
        assert len(result.issues) == 1
        issue = result.issues[0]
        assert issue.file_path == "auth.py"
        assert issue.line_number == 2
        assert issue.severity == "warning"
        assert issue.category == "security"
        assert issue.description == "JWT secret 应从环境变量读取"
        assert issue.suggestion == "使用 os.environ.get('JWT_SECRET')"
        assert result.reviewed_at  # non-empty ISO timestamp

    @patch("src.ai_reviewer.ChatOpenAI")
    def test_review_empty_diff_raises(self, mock_chat_cls) -> None:
        """Empty diff raises EmptyDiffError."""
        reviewer = AIReviewer(_config())
        with pytest.raises(EmptyDiffError, match="无代码变更"):
            reviewer.review(_pr_info(diff=""))

    @patch("src.ai_reviewer.ChatOpenAI")
    def test_review_whitespace_diff_raises(self, mock_chat_cls) -> None:
        """Whitespace-only diff raises EmptyDiffError."""
        reviewer = AIReviewer(_config())
        with pytest.raises(EmptyDiffError, match="无代码变更"):
            reviewer.review(_pr_info(diff="   \n  "))

    @patch("src.ai_reviewer.time.sleep")
    @patch("src.ai_reviewer.ChatOpenAI")
    def test_review_llm_failure_retries_then_raises(
        self, mock_chat_cls, mock_sleep
    ) -> None:
        """LLM fails 3 times → AIModelError after retries."""
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = RuntimeError("connection timeout")
        mock_chat_cls.return_value = mock_llm

        reviewer = AIReviewer(_config())
        with pytest.raises(AIModelError, match="AI 模型调用失败"):
            reviewer.review(_pr_info())

        assert mock_llm.invoke.call_count == 3
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)

    @patch("src.ai_reviewer.time.sleep")
    @patch("src.ai_reviewer.ChatOpenAI")
    def test_review_llm_succeeds_on_retry(
        self, mock_chat_cls, mock_sleep
    ) -> None:
        """LLM fails once then succeeds on second attempt."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = _VALID_LLM_JSON
        mock_llm.invoke.side_effect = [
            RuntimeError("temporary error"),
            mock_response,
        ]
        mock_chat_cls.return_value = mock_llm

        reviewer = AIReviewer(_config())
        result = reviewer.review(_pr_info())

        assert result.summary == "代码整体质量良好，发现1个潜在问题"
        assert mock_llm.invoke.call_count == 2
        mock_sleep.assert_called_once_with(1)

    @patch("src.ai_reviewer.ChatOpenAI")
    def test_review_parses_markdown_fenced_json(
        self, mock_chat_cls
    ) -> None:
        """LLM wraps JSON in markdown code fences → still parsed."""
        fenced = f"```json\n{_VALID_LLM_JSON}\n```"
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = fenced
        mock_llm.invoke.return_value = mock_response
        mock_chat_cls.return_value = mock_llm

        reviewer = AIReviewer(_config())
        result = reviewer.review(_pr_info())

        assert len(result.issues) == 1

    @patch("src.ai_reviewer.ChatOpenAI")
    def test_review_invalid_json_raises(self, mock_chat_cls) -> None:
        """LLM returns non-JSON → AIModelError."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "This is not JSON at all"
        mock_llm.invoke.return_value = mock_response
        mock_chat_cls.return_value = mock_llm

        reviewer = AIReviewer(_config())
        with pytest.raises(AIModelError, match="JSON 解析失败"):
            reviewer.review(_pr_info())

    @patch("src.ai_reviewer.ChatOpenAI")
    def test_review_no_issues(self, mock_chat_cls) -> None:
        """LLM returns result with empty issues list."""
        no_issues = json.dumps(
            {"summary": "代码质量优秀，未发现问题", "issues": []}
        )
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = no_issues
        mock_llm.invoke.return_value = mock_response
        mock_chat_cls.return_value = mock_llm

        reviewer = AIReviewer(_config())
        result = reviewer.review(_pr_info())

        assert result.summary == "代码质量优秀，未发现问题"
        assert result.issues == []

    @patch("src.ai_reviewer.ChatOpenAI")
    def test_init_passes_config_to_llm(self, mock_chat_cls) -> None:
        """ChatOpenAI is initialized with config values."""
        cfg = _config(
            llm_model="deepseek-v3",
            llm_api_key="sk-test",
            llm_base_url="https://custom.api/v1",
        )
        AIReviewer(cfg)

        mock_chat_cls.assert_called_once_with(
            model="deepseek-v3",
            api_key="sk-test",
            base_url="https://custom.api/v1",
        )

    @patch("src.ai_reviewer.ChatOpenAI")
    def test_init_no_base_url(self, mock_chat_cls) -> None:
        """When llm_base_url is empty, base_url kwarg is omitted."""
        cfg = _config(llm_base_url="")
        AIReviewer(cfg)

        call_kwargs = mock_chat_cls.call_args[1]
        assert "base_url" not in call_kwargs
