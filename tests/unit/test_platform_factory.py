"""Unit tests for PlatformFactory."""

import pytest

from src.exceptions import UnknownPlatformError
from src.platform.factory import PlatformFactory


class TestDetectPlatform:
    """Tests for PlatformFactory.detect_platform."""

    def test_github_pr_url(self):
        url = "https://github.com/owner/repo/pull/42"
        assert PlatformFactory.detect_platform(url) == "github"

    def test_github_pr_url_with_trailing_path(self):
        url = (
            "https://github.com/owner/repo/pull/42/files"
        )
        assert PlatformFactory.detect_platform(url) == "github"

    def test_github_http_url(self):
        url = "http://github.com/owner/repo/pull/1"
        assert PlatformFactory.detect_platform(url) == "github"

    def test_unknown_url_raises(self):
        with pytest.raises(UnknownPlatformError) as exc:
            PlatformFactory.detect_platform(
                "https://example.com/pr/1"
            )
        assert "Supported PR URL formats" in str(exc.value)

    def test_empty_string_raises(self):
        with pytest.raises(UnknownPlatformError):
            PlatformFactory.detect_platform("")

    def test_gitlab_url_not_yet_supported(self):
        url = (
            "https://gitlab.com/group/project/"
            "-/merge_requests/10"
        )
        with pytest.raises(UnknownPlatformError):
            PlatformFactory.detect_platform(url)

    def test_github_non_pr_url_raises(self):
        url = "https://github.com/owner/repo/issues/5"
        with pytest.raises(UnknownPlatformError):
            PlatformFactory.detect_platform(url)


class TestCreateAdapter:
    """Tests for PlatformFactory.create_adapter."""

    def test_creates_github_adapter(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        url = "https://github.com/octo/repo/pull/99"
        adapter = PlatformFactory.create_adapter(url)

        from src.platform.github_adapter import GitHubAdapter

        assert isinstance(adapter, GitHubAdapter)
        assert adapter.owner == "octo"
        assert adapter.repo == "repo"
        assert adapter.pr_number == 99
        assert adapter.token == "test-token"

    def test_unknown_url_raises(self):
        with pytest.raises(UnknownPlatformError):
            PlatformFactory.create_adapter(
                "https://unknown.com/pr/1"
            )
