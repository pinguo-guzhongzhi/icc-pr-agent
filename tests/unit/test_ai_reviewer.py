"""Unit tests for AIReviewer (DeepAgents-based)."""

import json
from unittest.mock import MagicMock, patch, PropertyMock

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
        skills_dir="",
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


def _make_mock_agent(content: str = _VALID_LLM_JSON, side_effect=None):
    """Create a mock agent that returns the given content from invoke."""
    mock_agent = MagicMock()
    if side_effect:
        mock_agent.invoke.side_effect = side_effect
    else:
        mock_msg = MagicMock()
        mock_msg.content = content
        mock_msg.usage_metadata = None
        mock_agent.invoke.return_value = {"messages": [mock_msg]}
    return mock_agent


class TestAIReviewer:
    """Tests for AIReviewer (DeepAgents-based)."""

    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_review_normal_flow(self, mock_init_model, mock_create_agent) -> None:
        """Agent returns valid JSON → ReviewResult is correct."""
        mock_create_agent.return_value = _make_mock_agent()

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
        assert result.reviewed_at

    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_review_empty_diff_raises(self, mock_init_model, mock_create_agent) -> None:
        """Empty diff raises EmptyDiffError."""
        reviewer = AIReviewer(_config())
        with pytest.raises(EmptyDiffError, match="无代码变更"):
            reviewer.review(_pr_info(diff=""))

    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_review_whitespace_diff_raises(self, mock_init_model, mock_create_agent) -> None:
        """Whitespace-only diff raises EmptyDiffError."""
        reviewer = AIReviewer(_config())
        with pytest.raises(EmptyDiffError, match="无代码变更"):
            reviewer.review(_pr_info(diff="   \n  "))

    @patch("src.ai_reviewer.time.sleep")
    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_review_agent_failure_retries_then_raises(
        self, mock_init_model, mock_create_agent, mock_sleep
    ) -> None:
        """Agent fails 3 times → AIModelError after retries."""
        mock_agent = MagicMock()
        mock_agent.invoke.side_effect = RuntimeError("connection timeout")
        mock_create_agent.return_value = mock_agent

        reviewer = AIReviewer(_config())
        with pytest.raises(AIModelError, match="AI 模型调用失败"):
            reviewer.review(_pr_info())

        assert mock_agent.invoke.call_count == 3
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)

    @patch("src.ai_reviewer.time.sleep")
    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_review_agent_succeeds_on_retry(
        self, mock_init_model, mock_create_agent, mock_sleep
    ) -> None:
        """Agent fails once then succeeds on second attempt."""
        mock_msg = MagicMock()
        mock_msg.content = _VALID_LLM_JSON
        mock_msg.usage_metadata = None

        mock_agent = MagicMock()
        mock_agent.invoke.side_effect = [
            RuntimeError("temporary error"),
            {"messages": [mock_msg]},
        ]
        mock_create_agent.return_value = mock_agent

        reviewer = AIReviewer(_config())
        result = reviewer.review(_pr_info())

        assert result.summary == "代码整体质量良好，发现1个潜在问题"
        assert mock_agent.invoke.call_count == 2
        mock_sleep.assert_called_once_with(1)

    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_review_parses_markdown_fenced_json(
        self, mock_init_model, mock_create_agent
    ) -> None:
        """Agent wraps JSON in markdown code fences → still parsed."""
        fenced = f"```json\n{_VALID_LLM_JSON}\n```"
        mock_create_agent.return_value = _make_mock_agent(fenced)

        reviewer = AIReviewer(_config())
        result = reviewer.review(_pr_info())

        assert len(result.issues) == 1

    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_review_invalid_json_raises(self, mock_init_model, mock_create_agent) -> None:
        """Agent returns non-JSON → AIModelError."""
        mock_create_agent.return_value = _make_mock_agent("This is not JSON at all")

        reviewer = AIReviewer(_config())
        with pytest.raises(AIModelError, match="JSON 解析失败"):
            reviewer.review(_pr_info())

    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_review_no_issues(self, mock_init_model, mock_create_agent) -> None:
        """Agent returns result with empty issues list."""
        no_issues = json.dumps(
            {"summary": "代码质量优秀，未发现问题", "issues": []}
        )
        mock_create_agent.return_value = _make_mock_agent(no_issues)

        reviewer = AIReviewer(_config())
        result = reviewer.review(_pr_info())

        assert result.summary == "代码质量优秀，未发现问题"
        assert result.issues == []

    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_init_creates_agent_with_skills(
        self, mock_init_model, mock_create_agent
    ) -> None:
        """create_deep_agent is called with skills parameter."""
        mock_create_agent.return_value = _make_mock_agent()

        reviewer = AIReviewer(_config())
        reviewer.review(_pr_info())

        mock_create_agent.assert_called()
        call_kwargs = mock_create_agent.call_args[1]
        assert call_kwargs["skills"] == ["/skills/"]
        assert "system_prompt" in call_kwargs

    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_init_model_with_base_url(self, mock_init_model, mock_create_agent) -> None:
        """init_chat_model receives api_key and base_url from config."""
        mock_create_agent.return_value = _make_mock_agent()
        cfg = _config(
            llm_model="deepseek-v3",
            llm_api_key="sk-test",
            llm_base_url="https://custom.api/v1",
        )

        reviewer = AIReviewer(cfg)
        reviewer.review(_pr_info())

        mock_init_model.assert_called_with(
            "openai:deepseek-v3",
            api_key="sk-test",
            base_url="https://custom.api/v1",
        )

    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_init_model_no_base_url(self, mock_init_model, mock_create_agent) -> None:
        """When llm_base_url is empty, base_url kwarg is omitted."""
        mock_create_agent.return_value = _make_mock_agent()
        cfg = _config(llm_base_url="")

        reviewer = AIReviewer(cfg)
        reviewer.review(_pr_info())

        call_kwargs = mock_init_model.call_args[1]
        assert "base_url" not in call_kwargs

    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_model_string_with_provider_prefix(self, mock_init_model, mock_create_agent) -> None:
        """Model string with provider prefix is passed through as-is."""
        mock_create_agent.return_value = _make_mock_agent()
        cfg = _config(llm_model="anthropic:claude-sonnet-4-5-20250929")

        reviewer = AIReviewer(cfg)
        reviewer.review(_pr_info())

        assert mock_init_model.call_args[0][0] == "anthropic:claude-sonnet-4-5-20250929"

    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_agent_invoke_receives_skills_files(
        self, mock_init_model, mock_create_agent
    ) -> None:
        """Agent invoke is called with files containing skills data."""
        mock_agent = _make_mock_agent()
        mock_create_agent.return_value = mock_agent

        reviewer = AIReviewer(_config())
        result = reviewer.review(_pr_info())

        invoke_call = mock_agent.invoke.call_args
        invoke_input = invoke_call[0][0]
        assert "messages" in invoke_input
        assert "files" in invoke_input

    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_review_extracts_json_from_mixed_content(
        self, mock_init_model, mock_create_agent
    ) -> None:
        """Agent returns JSON embedded in text → still parsed."""
        mixed = f"Here is my review:\n{_VALID_LLM_JSON}\nHope this helps!"
        mock_create_agent.return_value = _make_mock_agent(mixed)

        reviewer = AIReviewer(_config())
        result = reviewer.review(_pr_info())

        assert len(result.issues) == 1


class TestAIReviewer:
    """Tests for AIReviewer (DeepAgents-based)."""

    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_review_normal_flow(self, mock_init_model, mock_create_agent) -> None:
        mock_create_agent.return_value = _make_mock_agent()

        reviewer = AIReviewer(_config())
        result = reviewer.review(_pr_info())

        assert result.summary == "代码整体质量良好，发现1个潜在问题"
        assert len(result.issues) == 1
        issue = result.issues[0]
        assert issue.file_path == "auth.py"
        assert issue.line_number == 2
        assert issue.severity == "warning"
        assert issue.category == "security"
        assert result.reviewed_at

    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_review_empty_diff_raises(self, mock_init_model, mock_create_agent) -> None:
        reviewer = AIReviewer(_config())
        with pytest.raises(EmptyDiffError, match="无代码变更"):
            reviewer.review(_pr_info(diff=""))

    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_review_whitespace_diff_raises(self, mock_init_model, mock_create_agent) -> None:
        reviewer = AIReviewer(_config())
        with pytest.raises(EmptyDiffError, match="无代码变更"):
            reviewer.review(_pr_info(diff="   \n  "))

    @patch("src.ai_reviewer.time.sleep")
    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_review_agent_failure_retries_then_raises(
        self, mock_init_model, mock_create_agent, mock_sleep
    ) -> None:
        mock_agent = MagicMock()
        mock_agent.invoke.side_effect = RuntimeError("connection timeout")
        mock_create_agent.return_value = mock_agent

        reviewer = AIReviewer(_config())
        with pytest.raises(AIModelError, match="AI 模型调用失败"):
            reviewer.review(_pr_info())

        assert mock_agent.invoke.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("src.ai_reviewer.time.sleep")
    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_review_agent_succeeds_on_retry(
        self, mock_init_model, mock_create_agent, mock_sleep
    ) -> None:
        mock_msg = MagicMock()
        mock_msg.content = _VALID_LLM_JSON
        mock_msg.usage_metadata = None

        mock_agent = MagicMock()
        mock_agent.invoke.side_effect = [
            RuntimeError("temporary error"),
            {"messages": [mock_msg]},
        ]
        mock_create_agent.return_value = mock_agent

        reviewer = AIReviewer(_config())
        result = reviewer.review(_pr_info())

        assert result.summary == "代码整体质量良好，发现1个潜在问题"
        assert mock_agent.invoke.call_count == 2

    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_review_parses_markdown_fenced_json(self, mock_init_model, mock_create_agent) -> None:
        fenced = f"```json\n{_VALID_LLM_JSON}\n```"
        mock_create_agent.return_value = _make_mock_agent(fenced)

        reviewer = AIReviewer(_config())
        result = reviewer.review(_pr_info())
        assert len(result.issues) == 1

    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_review_invalid_json_raises(self, mock_init_model, mock_create_agent) -> None:
        mock_create_agent.return_value = _make_mock_agent("This is not JSON at all")

        reviewer = AIReviewer(_config())
        with pytest.raises(AIModelError, match="JSON 解析失败"):
            reviewer.review(_pr_info())

    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_review_no_issues(self, mock_init_model, mock_create_agent) -> None:
        no_issues = json.dumps({"summary": "代码质量优秀，未发现问题", "issues": []})
        mock_create_agent.return_value = _make_mock_agent(no_issues)

        reviewer = AIReviewer(_config())
        result = reviewer.review(_pr_info())

        assert result.summary == "代码质量优秀，未发现问题"
        assert result.issues == []

    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_agent_called_with_skills(self, mock_init_model, mock_create_agent) -> None:
        mock_create_agent.return_value = _make_mock_agent()

        reviewer = AIReviewer(_config())
        reviewer.review(_pr_info())

        call_kwargs = mock_create_agent.call_args[1]
        assert call_kwargs["skills"] == ["/skills/"]

    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_init_model_with_base_url(self, mock_init_model, mock_create_agent) -> None:
        mock_create_agent.return_value = _make_mock_agent()
        cfg = _config(llm_model="deepseek-v3", llm_api_key="sk-test", llm_base_url="https://custom.api/v1")

        reviewer = AIReviewer(cfg)
        reviewer.review(_pr_info())

        mock_init_model.assert_called_with("openai:deepseek-v3", api_key="sk-test", base_url="https://custom.api/v1")

    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_init_model_no_base_url(self, mock_init_model, mock_create_agent) -> None:
        mock_create_agent.return_value = _make_mock_agent()
        cfg = _config(llm_base_url="")

        reviewer = AIReviewer(cfg)
        reviewer.review(_pr_info())

        call_kwargs = mock_init_model.call_args[1]
        assert "base_url" not in call_kwargs

    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_model_string_with_provider_prefix(self, mock_init_model, mock_create_agent) -> None:
        mock_create_agent.return_value = _make_mock_agent()
        cfg = _config(llm_model="anthropic:claude-sonnet-4-5-20250929")

        reviewer = AIReviewer(cfg)
        reviewer.review(_pr_info())

        assert mock_init_model.call_args[0][0] == "anthropic:claude-sonnet-4-5-20250929"

    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_invoke_receives_files_and_messages(self, mock_init_model, mock_create_agent) -> None:
        mock_agent = _make_mock_agent()
        mock_create_agent.return_value = mock_agent

        reviewer = AIReviewer(_config())
        reviewer.review(_pr_info())

        invoke_input = mock_agent.invoke.call_args[0][0]
        assert "messages" in invoke_input
        assert "files" in invoke_input

    @patch("src.ai_reviewer.create_deep_agent")
    @patch("src.ai_reviewer.init_chat_model")
    def test_review_extracts_json_from_mixed_content(self, mock_init_model, mock_create_agent) -> None:
        mixed = f"Here is my review:\n{_VALID_LLM_JSON}\nHope this helps!"
        mock_create_agent.return_value = _make_mock_agent(mixed)

        reviewer = AIReviewer(_config())
        result = reviewer.review(_pr_info())
        assert len(result.issues) == 1
