"""Unit tests for FileFilter."""

from __future__ import annotations

import textwrap

from src.file_filter import FileFilter
from src.models import FilterResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_DIFF = textwrap.dedent("""\
    diff --git a/src/main.py b/src/main.py
    --- a/src/main.py
    +++ b/src/main.py
    @@ -1,3 +1,4 @@
    +import os
     import sys
    diff --git a/yarn.lock b/yarn.lock
    --- a/yarn.lock
    +++ b/yarn.lock
    @@ -1 +1 @@
    -old
    +new
    diff --git a/logo.png b/logo.png
    Binary files differ
    diff --git a/README.md b/README.md
    --- a/README.md
    +++ b/README.md
    @@ -1 +1 @@
    -old
    +new
""")


# ---------------------------------------------------------------------------
# __init__ / get_effective_patterns
# ---------------------------------------------------------------------------

class TestEffectivePatterns:
    def test_defaults_only(self):
        ff = FileFilter()
        patterns = ff.get_effective_patterns()
        assert patterns == FileFilter.DEFAULT_EXCLUDE_PATTERNS

    def test_user_patterns_merged(self):
        ff = FileFilter(exclude_patterns=["*.log", "docs/**"])
        patterns = ff.get_effective_patterns()
        assert "*.log" in patterns
        assert "docs/**" in patterns
        # defaults still present
        assert "*.lock" in patterns

    def test_no_duplicates(self):
        ff = FileFilter(exclude_patterns=["*.lock", "*.png"])
        patterns = ff.get_effective_patterns()
        assert patterns.count("*.lock") == 1
        assert patterns.count("*.png") == 1

    def test_defaults_disabled(self):
        ff = FileFilter(
            exclude_patterns=["*.log"], use_defaults=False
        )
        patterns = ff.get_effective_patterns()
        assert patterns == ["*.log"]
        assert "*.lock" not in patterns

    def test_no_patterns_no_defaults(self):
        ff = FileFilter(use_defaults=False)
        assert ff.get_effective_patterns() == []


# ---------------------------------------------------------------------------
# is_excluded
# ---------------------------------------------------------------------------

class TestIsExcluded:
    def test_lock_file_excluded(self):
        ff = FileFilter()
        excluded, pattern = ff.is_excluded("yarn.lock")
        assert excluded is True
        assert pattern == "*.lock"

    def test_json_lock_not_excluded_by_default(self):
        """package-lock.json ends in .json, not .lock."""
        ff = FileFilter()
        excluded, _ = ff.is_excluded("package-lock.json")
        assert excluded is False

    def test_png_excluded(self):
        ff = FileFilter()
        excluded, pattern = ff.is_excluded("assets/logo.png")
        assert excluded is True
        assert pattern == "*.png"

    def test_python_file_not_excluded(self):
        ff = FileFilter()
        excluded, pattern = ff.is_excluded("src/main.py")
        assert excluded is False
        assert pattern is None

    def test_custom_pattern(self):
        ff = FileFilter(exclude_patterns=["*.log"])
        excluded, pattern = ff.is_excluded("app.log")
        assert excluded is True
        assert pattern == "*.log"

    def test_no_patterns(self):
        ff = FileFilter(use_defaults=False)
        excluded, pattern = ff.is_excluded("package-lock.json")
        assert excluded is False


# ---------------------------------------------------------------------------
# filter_diff
# ---------------------------------------------------------------------------

class TestFilterDiff:
    def test_filters_excluded_files(self):
        ff = FileFilter()
        result = ff.filter_diff(SAMPLE_DIFF)

        assert isinstance(result, FilterResult)
        # yarn.lock and logo.png should be excluded
        assert result.excluded_file_count == 2
        assert result.included_file_count == 2
        assert "yarn.lock" not in result.filtered_diff
        assert "logo.png" not in result.filtered_diff
        # kept files should remain
        assert "src/main.py" in result.filtered_diff
        assert "README.md" in result.filtered_diff

    def test_excluded_files_list(self):
        ff = FileFilter()
        result = ff.filter_diff(SAMPLE_DIFF)
        paths = [e["file_path"] for e in result.excluded_files]
        assert "yarn.lock" in paths
        assert "logo.png" in paths

    def test_count_conservation(self):
        ff = FileFilter()
        result = ff.filter_diff(SAMPLE_DIFF)
        total = result.included_file_count + result.excluded_file_count
        assert total == 4  # 4 files in SAMPLE_DIFF

    def test_empty_diff(self):
        ff = FileFilter()
        result = ff.filter_diff("")
        assert result.filtered_diff == ""
        assert result.included_file_count == 0
        assert result.excluded_file_count == 0

    def test_no_exclusions(self):
        ff = FileFilter(use_defaults=False)
        result = ff.filter_diff(SAMPLE_DIFF)
        assert result.excluded_file_count == 0
        assert result.included_file_count == 4


# ---------------------------------------------------------------------------
# load_patterns_from_config
# ---------------------------------------------------------------------------

class TestLoadPatternsFromConfig:
    def test_missing_file(self, tmp_path):
        patterns = FileFilter.load_patterns_from_config(
            str(tmp_path / "nope.yml")
        )
        assert patterns == []

    def test_valid_yaml(self, tmp_path):
        cfg = tmp_path / "pr-review.yaml"
        cfg.write_text("exclude:\n  - '*.log'\n  - 'docs/**'\n")
        patterns = FileFilter.load_patterns_from_config(str(cfg))
        assert patterns == ["*.log", "docs/**"]

    def test_no_exclude_key(self, tmp_path):
        cfg = tmp_path / "pr-review.yaml"
        cfg.write_text("other_key: value\n")
        patterns = FileFilter.load_patterns_from_config(str(cfg))
        assert patterns == []


# ---------------------------------------------------------------------------
# load_patterns_from_env
# ---------------------------------------------------------------------------

class TestLoadPatternsFromEnv:
    def test_empty_env(self):
        patterns = FileFilter.load_patterns_from_env()
        assert patterns == []

    def test_comma_separated(self, monkeypatch):
        monkeypatch.setenv(
            "PR_REVIEW_EXCLUDE", "*.lock, *.png, docs/**"
        )
        patterns = FileFilter.load_patterns_from_env()
        assert patterns == ["*.lock", "*.png", "docs/**"]

    def test_trailing_commas(self, monkeypatch):
        monkeypatch.setenv("PR_REVIEW_EXCLUDE", "*.lock,,")
        patterns = FileFilter.load_patterns_from_env()
        assert patterns == ["*.lock"]
