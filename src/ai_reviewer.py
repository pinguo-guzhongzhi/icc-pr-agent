"""AI code review engine using LangChain DeepAgents SDK.

Uses ``create_deep_agent`` with skills support for structured code review.
When a diff is too large it is split by file and each chunk is reviewed
independently, then results are merged.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone

import yaml
from deepagents import create_deep_agent
from deepagents.backends.utils import create_file_data
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import MemorySaver

from src.config import Config
from src.exceptions import AIModelError, EmptyDiffError
from src.logger import get_logger
from src.models import PRInfo, ReviewIssue, ReviewResult

logger = get_logger(__name__)

# Rough char limit per chunk — leaves room for prompt overhead.
_MAX_DIFF_CHARS = 20_000

_DIFF_HEADER_RE = re.compile(r"^diff --git a/.+ b/.+$", re.MULTILINE)

# ---------- Default prompts (used when no YAML config is provided) ----------

_DEFAULT_SYSTEM_PROMPT = (
    "你是一位资深代码审查专家。请根据你掌握的技能，"
    "对代码变更进行专业审查，严格按照 JSON 格式输出结果。"
)

_DEFAULT_REVIEW_USER_PROMPT = """\
请对以下 Pull Request 的代码变更进行审查。

## PR 信息
- 标题: {title}
- 描述: {description}
- 源分支: {source_branch}
- 目标分支: {target_branch}

## 代码变更 (Diff)
```
{diff}
```

请使用你认为合适的技能进行审查，严格按照以下 JSON 格式输出结果，不要包含其他内容：
{{
  "summary": "审查总结（一段简短的总体评价）",
  "issues": [
    {{
      "file_path": "文件路径",
      "line_number": 行号或null,
      "severity": "critical|warning|suggestion",
      "category": "quality|bug|security|improvement",
      "description": "问题描述",
      "suggestion": "改进建议或null"
    }}
  ]
}}
"""

_DEFAULT_SUMMARY_USER_PROMPT = """\
以下是对一个 Pull Request 中多个文件分别审查后的结果摘要列表。
请将它们合并为一段简洁的总体审查总结（2-3 句话）。

各文件审查摘要：
{summaries}

请只输出总结文本，不要输出 JSON 或其他格式。
"""

_MAX_RETRIES = 3
_BACKOFF_SECONDS = [1, 2, 4]

# Default skills directory (relative to project root)
_DEFAULT_SKILLS_DIR = os.path.join(os.getcwd(), "skills")
_DEFAULT_CONFIG_PATH = os.path.join(os.getcwd(), "pr-review.yaml")


def _load_prompts(config_path: str) -> dict:
    """Load prompt templates from the ``prompts:`` section of pr-review.yaml.

    Returns a dict with keys: system_prompt, review_user_prompt,
    summary_user_prompt.  Missing keys fall back to defaults.
    """
    defaults = {
        "system_prompt": _DEFAULT_SYSTEM_PROMPT,
        "review_user_prompt": _DEFAULT_REVIEW_USER_PROMPT,
        "summary_user_prompt": _DEFAULT_SUMMARY_USER_PROMPT,
    }
    if not config_path or not os.path.isfile(config_path):
        return defaults

    try:
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        prompts_section = data.get("prompts", {})
        if not isinstance(prompts_section, dict):
            return defaults
        loaded = {k: prompts_section[k] for k in defaults if k in prompts_section}
        result = {**defaults, **loaded}
        logger.info(
            "已加载 prompts 配置: %s (覆盖 %d 项)",
            config_path,
            len(loaded),
        )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取 prompts 配置失败: %s，使用默认值", exc)
        return defaults


class AIReviewer:
    """AI-powered code review engine backed by DeepAgents SDK.

    Uses ``create_deep_agent()`` with skills for structured review.
    When the diff exceeds ``_MAX_DIFF_CHARS`` it is automatically split
    into per-file chunks and each chunk is reviewed independently.
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._skills_dir = config.skills_dir or _DEFAULT_SKILLS_DIR
        config_path = _DEFAULT_CONFIG_PATH
        self._prompts = _load_prompts(config_path)
        # Token usage tracking
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0

    def _build_model_string(self) -> str:
        """Build the provider:model string for init_chat_model."""
        # If user already specified provider prefix, use as-is
        model = self._config.llm_model
        if ":" in model:
            return model
        # Default to openai-compatible provider
        return f"openai:{model}"

    def _create_agent(self):
        """Create a fresh DeepAgents agent instance."""
        model_kwargs = {}
        if self._config.llm_api_key:
            model_kwargs["api_key"] = self._config.llm_api_key
        if self._config.llm_base_url:
            model_kwargs["base_url"] = self._config.llm_base_url

        model = init_chat_model(
            self._build_model_string(),
            **model_kwargs,
        )

        # Load skills files into state backend
        skills_files = self._load_skills_files()

        agent = create_deep_agent(
            model=model,
            system_prompt=self._prompts["system_prompt"],
            skills=["/skills/"],
            checkpointer=MemorySaver(),
        )
        return agent, skills_files

    def _load_skills_files(self) -> dict:
        """Load SKILL.md files from the skills directory into state backend format.

        Only loads SKILL.md files (not all supporting files) to minimize
        token usage. The agent can read additional skill files on demand
        via its built-in filesystem tools.
        """
        skills_files = {}
        skills_dir = self._skills_dir
        if not os.path.isdir(skills_dir):
            logger.warning("Skills 目录不存在: %s", skills_dir)
            return skills_files

        for entry in os.listdir(skills_dir):
            skill_dir = os.path.join(skills_dir, entry)
            if not os.path.isdir(skill_dir):
                continue
            skill_md = os.path.join(skill_dir, "SKILL.md")
            if not os.path.isfile(skill_md):
                continue
            try:
                content = open(skill_md, encoding="utf-8").read()
                virtual_path = f"/skills/{entry}/SKILL.md"
                skills_files[virtual_path] = create_file_data(content)
                logger.info(
                    "已加载 skill: %s (%d chars)",
                    virtual_path,
                    len(content),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("无法读取 skill 文件 %s: %s", skill_md, exc)

        logger.info(
            "Skills 加载完成: %d 个 skill, 来源目录: %s",
            len(skills_files),
            skills_dir,
        )
        return skills_files

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def review(self, pr_info: PRInfo) -> ReviewResult:
        """Review PR code changes and return structured results."""
        if not pr_info.diff or not pr_info.diff.strip():
            raise EmptyDiffError("无代码变更，无需审查")

        diff = pr_info.diff
        if len(diff) <= _MAX_DIFF_CHARS:
            return self._review_single(pr_info, diff)

        return self._review_chunked(pr_info)

    # ------------------------------------------------------------------
    # Single-pass review (small diff)
    # ------------------------------------------------------------------

    def _review_single(self, pr_info: PRInfo, diff: str) -> ReviewResult:
        prompt = self._prompts["review_user_prompt"].format(
            title=pr_info.title,
            description=pr_info.description,
            source_branch=pr_info.source_branch,
            target_branch=pr_info.target_branch,
            diff=diff,
        )
        raw = self._call_agent_with_retry(prompt)
        return self._parse_response(raw)

    # ------------------------------------------------------------------
    # Chunked review (large diff)
    # ------------------------------------------------------------------

    def _review_chunked(self, pr_info: PRInfo) -> ReviewResult:
        """Split diff by file, review each chunk, merge results."""
        file_diffs = self._split_diff_by_file(pr_info.diff)
        logger.info(
            "Diff 过大 (%d chars, %d 个文件)，将分片审查",
            len(pr_info.diff),
            len(file_diffs),
        )

        chunks = self._group_into_chunks(file_diffs)
        logger.info("分为 %d 个批次进行审查", len(chunks))

        all_issues: list[ReviewIssue] = []
        summaries: list[str] = []

        for idx, chunk_diff in enumerate(chunks, 1):
            logger.info("审查批次 %d/%d ...", idx, len(chunks))
            result = self._review_single(pr_info, chunk_diff)
            all_issues.extend(result.issues)
            if result.summary:
                summaries.append(result.summary)

        if len(summaries) <= 1:
            merged_summary = summaries[0] if summaries else "审查完成"
        else:
            merged_summary = self._merge_summaries(summaries)

        return ReviewResult(
            summary=merged_summary,
            issues=all_issues,
            reviewed_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _split_diff_by_file(diff: str) -> list[str]:
        positions = [m.start() for m in _DIFF_HEADER_RE.finditer(diff)]
        if not positions:
            return [diff]
        sections: list[str] = []
        for i, start in enumerate(positions):
            end = positions[i + 1] if i + 1 < len(positions) else len(diff)
            sections.append(diff[start:end])
        return sections

    @staticmethod
    def _group_into_chunks(
        file_diffs: list[str],
        max_chars: int = _MAX_DIFF_CHARS,
    ) -> list[str]:
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        for fd in file_diffs:
            fd_len = len(fd)
            if current and current_len + fd_len > max_chars:
                chunks.append("".join(current))
                current = []
                current_len = 0
            current.append(fd)
            current_len += fd_len
        if current:
            chunks.append("".join(current))
        return chunks

    def _merge_summaries(self, summaries: list[str]) -> str:
        numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(summaries, 1))
        prompt = self._prompts["summary_user_prompt"].format(
            summaries=numbered,
        )
        try:
            raw = self._call_agent_with_retry(prompt)
            return raw.strip()
        except AIModelError:
            return " | ".join(summaries)

    # ------------------------------------------------------------------
    # DeepAgents invocation with retry
    # ------------------------------------------------------------------

    def _call_agent_with_retry(self, prompt: str) -> str:
        """Invoke the DeepAgents agent with up to 3 retries."""
        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                logger.info(
                    "调用 DeepAgents (尝试 %d/%d)", attempt + 1, _MAX_RETRIES
                )
                agent, skills_files = self._create_agent()
                thread_id = f"review-{datetime.now(timezone.utc).timestamp()}"
                result = agent.invoke(
                    {
                        "messages": [{"role": "user", "content": prompt}],
                        "files": skills_files,
                    },
                    config={"configurable": {"thread_id": thread_id}},
                )
                # Extract the final assistant message
                messages = result.get("messages", [])
                if not messages:
                    raise AIModelError("DeepAgents 返回空消息")

                last_msg = messages[-1]
                content = (
                    last_msg.content
                    if hasattr(last_msg, "content")
                    else str(last_msg)
                )

                # Track token usage from response metadata if available
                usage = getattr(last_msg, "usage_metadata", None)
                if usage:
                    self.total_prompt_tokens += usage.get("input_tokens", 0)
                    self.total_completion_tokens += usage.get("output_tokens", 0)
                    self.total_tokens += usage.get("total_tokens", 0)

                return content
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt < _MAX_RETRIES - 1:
                    wait = _BACKOFF_SECONDS[attempt]
                    logger.warning(
                        "DeepAgents 调用失败，%ds 后重试: %s", wait, exc
                    )
                    time.sleep(wait)

        raise AIModelError(f"AI 模型调用失败: {last_error}")

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(raw: str) -> ReviewResult:
        """Parse the agent JSON response into a ReviewResult."""
        text = raw.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.splitlines()
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        # Try to extract JSON from mixed content
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            text = json_match.group()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AIModelError(
                f"AI 返回的 JSON 解析失败: {exc}"
            ) from exc

        issues = [
            ReviewIssue(
                file_path=item.get("file_path", ""),
                line_number=item.get("line_number"),
                severity=item.get("severity", "suggestion"),
                category=item.get("category", "improvement"),
                description=item.get("description", ""),
                suggestion=item.get("suggestion"),
            )
            for item in data.get("issues", [])
        ]

        return ReviewResult(
            summary=data.get("summary", ""),
            issues=issues,
            reviewed_at=datetime.now(timezone.utc).isoformat(),
        )
