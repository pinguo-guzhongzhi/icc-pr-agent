"""AI code review engine using LangChain ChatOpenAI.

Supports chunked review: when a diff is too large, it is split by file
and each file is reviewed independently, then results are merged.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone

from langchain_openai import ChatOpenAI

from src.config import Config
from src.exceptions import AIModelError, EmptyDiffError
from src.logger import get_logger
from src.models import PRInfo, ReviewIssue, ReviewResult

logger = get_logger(__name__)

# Rough char limit per chunk — leaves room for prompt overhead.
# Most models handle ~8K tokens ≈ ~24K chars comfortably.
_MAX_DIFF_CHARS = 20_000

_DIFF_HEADER_RE = re.compile(r"^diff --git a/.+ b/.+$", re.MULTILINE)

_REVIEW_PROMPT_TEMPLATE = """\
你是一位资深代码审查专家。请对以下 Pull Request 的代码变更进行审查。

## PR 信息
- 标题: {title}
- 描述: {description}
- 源分支: {source_branch}
- 目标分支: {target_branch}

## 代码变更 (Diff)
```
{diff}
```

## 审查要求
请从以下维度进行审查：
1. 代码质量 (quality) — 代码风格、可读性、可维护性
2. 潜在缺陷 (bug) — 逻辑错误、边界条件、空指针等
3. 安全风险 (security) — 注入、敏感信息泄露、权限问题等
4. 改进建议 (improvement) — 性能优化、更好的实现方式等

## 输出格式
请严格按照以下 JSON 格式输出，不要包含其他内容：
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

_SUMMARY_PROMPT_TEMPLATE = """\
你是一位资深代码审查专家。以下是对一个 Pull Request 中多个文件分别审查后的结果摘要列表。
请将它们合并为一段简洁的总体审查总结（2-3 句话）。

各文件审查摘要：
{summaries}

请只输出总结文本，不要输出 JSON 或其他格式。
"""

_MAX_RETRIES = 3
_BACKOFF_SECONDS = [1, 2, 4]


class AIReviewer:
    """AI-powered code review engine backed by LangChain ChatOpenAI.

    When the diff exceeds ``_MAX_DIFF_CHARS`` it is automatically split
    into per-file chunks and each chunk is reviewed independently.
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        kwargs: dict = {
            "model": config.llm_model,
            "api_key": config.llm_api_key,
        }
        if config.llm_base_url:
            kwargs["base_url"] = config.llm_base_url
        self._llm = ChatOpenAI(**kwargs, timeout=120)

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

        # Large diff → split by file and review in chunks
        return self._review_chunked(pr_info)

    # ------------------------------------------------------------------
    # Single-pass review (small diff)
    # ------------------------------------------------------------------

    def _review_single(self, pr_info: PRInfo, diff: str) -> ReviewResult:
        prompt = _REVIEW_PROMPT_TEMPLATE.format(
            title=pr_info.title,
            description=pr_info.description,
            source_branch=pr_info.source_branch,
            target_branch=pr_info.target_branch,
            diff=diff,
        )
        raw = self._call_llm_with_retry(prompt)
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

        # Group files into chunks that fit within the char limit
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

        # Merge summaries
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
        """Split a unified diff into per-file sections."""
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
        """Group per-file diffs into chunks that fit within max_chars.

        A single file that exceeds max_chars is kept as its own chunk
        (the model will do its best with truncation).
        """
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
        """Ask the LLM to merge multiple per-chunk summaries."""
        numbered = "\n".join(
            f"{i}. {s}" for i, s in enumerate(summaries, 1)
        )
        prompt = _SUMMARY_PROMPT_TEMPLATE.format(summaries=numbered)
        try:
            raw = self._call_llm_with_retry(prompt)
            return raw.strip()
        except AIModelError:
            # Fallback: just join them
            return " | ".join(summaries)

    # ------------------------------------------------------------------
    # LLM call with retry
    # ------------------------------------------------------------------

    def _call_llm_with_retry(self, prompt: str) -> str:
        """Call the LLM with up to 3 retries and exponential backoff."""
        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                logger.info(
                    "调用 AI 模型 (尝试 %d/%d)", attempt + 1, _MAX_RETRIES
                )
                response = self._llm.invoke(prompt)
                return str(response.content)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt < _MAX_RETRIES - 1:
                    wait = _BACKOFF_SECONDS[attempt]
                    logger.warning(
                        "AI 模型调用失败，%ds 后重试: %s", wait, exc
                    )
                    time.sleep(wait)

        raise AIModelError(f"AI 模型调用失败: {last_error}")

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(raw: str) -> ReviewResult:
        """Parse the LLM JSON response into a ReviewResult."""
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

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
