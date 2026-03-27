"""File filter for excluding files from PR diff review."""

from __future__ import annotations

import os
import re
from fnmatch import fnmatch
from pathlib import Path

import yaml

from src.logger import get_logger
from src.models import FilterResult

logger = get_logger(__name__)

# Regex to match unified diff file headers: diff --git a/... b/...
_DIFF_HEADER_RE = re.compile(r"^diff --git a/(.+?) b/(.+)$")


class FileFilter:
    """Filter files from a unified diff based on exclude patterns."""

    DEFAULT_EXCLUDE_PATTERNS: list[str] = [
        "*.lock",
        "*.png",
        "*.jpg",
        "*.jpeg",
        "*.gif",
        "*.svg",
        "*.ico",
        "*.woff",
        "*.woff2",
        "*.ttf",
        "*.eot",
    ]

    def __init__(
        self,
        exclude_patterns: list[str] | None = None,
        use_defaults: bool = True,
    ) -> None:
        self._user_patterns: list[str] = (
            list(exclude_patterns) if exclude_patterns else []
        )
        self._use_defaults = use_defaults

    def get_effective_patterns(self) -> list[str]:
        """Return merged patterns (defaults + user) without duplicates."""
        if self._use_defaults:
            combined = list(self.DEFAULT_EXCLUDE_PATTERNS)
            for p in self._user_patterns:
                if p not in combined:
                    combined.append(p)
            return combined
        return list(self._user_patterns)

    def is_excluded(self, file_path: str) -> tuple[bool, str | None]:
        """Check whether *file_path* matches any effective pattern.

        Returns ``(True, matched_pattern)`` or ``(False, None)``.
        """
        name = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path
        for pattern in self.get_effective_patterns():
            if fnmatch(name, pattern) or fnmatch(file_path, pattern):
                return True, pattern
        return False, None

    def filter_diff(self, diff: str) -> FilterResult:
        """Parse a unified diff and remove sections for excluded files."""
        sections: list[tuple[str, str]] = []
        current_path: str | None = None
        current_lines: list[str] = []

        for line in diff.splitlines(keepends=True):
            match = _DIFF_HEADER_RE.match(line.rstrip("\n"))
            if match:
                if current_path is not None:
                    sections.append(
                        (current_path, "".join(current_lines))
                    )
                current_path = match.group(2)
                current_lines = [line]
            else:
                current_lines.append(line)

        if current_path is not None:
            sections.append((current_path, "".join(current_lines)))

        included_parts: list[str] = []
        excluded_files: list[dict] = []

        for path, content in sections:
            excluded, pattern = self.is_excluded(path)
            if excluded:
                excluded_files.append(
                    {"file_path": path, "matched_pattern": pattern}
                )
                logger.info(
                    "Excluded file %s (matched %s)", path, pattern
                )
            else:
                included_parts.append(content)

        return FilterResult(
            filtered_diff="".join(included_parts),
            excluded_files=excluded_files,
            included_file_count=len(included_parts),
            excluded_file_count=len(excluded_files),
        )

    @staticmethod
    def load_patterns_from_config(
        config_path: str = "pr-review.yaml",
    ) -> list[str]:
        """Load exclude patterns from a YAML config file.

        Expected format::

            exclude:
              - "*.lock"
              - "*.png"

        Returns an empty list when the file does not exist.
        """
        path = Path(config_path)
        if not path.is_file():
            return []
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            return []
        patterns = data.get("exclude", [])
        if not isinstance(patterns, list):
            return []
        return [str(p) for p in patterns]

    @staticmethod
    def load_patterns_from_env() -> list[str]:
        """Load exclude patterns from the ``PR_REVIEW_EXCLUDE`` env var.

        Patterns are comma-separated.
        """
        raw = os.environ.get("PR_REVIEW_EXCLUDE", "")
        return [p.strip() for p in raw.split(",") if p.strip()]
