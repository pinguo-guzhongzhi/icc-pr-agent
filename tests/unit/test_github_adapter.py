"""Unit tests for GitHubAdapter."""

import httpx
import pytest

from src.exceptions import (
    CommentWriteBackError,
    CredentialMissingError,
    PlatformAPIError,
)
from src.models import PRInfo
from src.platform.github_adapter import GitHubAdapter


# ---- Fixtures --------------------------------------------------------

@pytest.fixture
def adapter():
    return GitHubAdapter(
        token="ghp_test123",
        owner="octo",
        repo="hello",
        pr_number=42,
    )


@pytest.fixture
def pr_json():
    """Minimal GitHub PR API response."""
    return {
        "title": "Fix bug",
        "body": "Fixes #1",
        "head": {
            "ref": "fix-branch",
            "sha": "abc123",
        },
        "base": {"ref": "main"},
        "user": {"login": "dev"},
    }


def _mock_response(
    status_code=200,
    json_data=None,
    text="",
):
    """Build a fake httpx.Response."""
    if json_data is not None:
        resp = httpx.Response(
            status_code=status_code,
            json=json_data,
            request=httpx.Request("GET", "https://x"),
        )
    else:
        resp = httpx.Response(
            status_code=status_code,
            text=text,
            request=httpx.Request("GET", "https://x"),
        )
    return resp


# ---- Credential checks ----------------------------------------------

class TestCredentialChecks:

    def test_fetch_raises_without_token(self):
        adapter = GitHubAdapter(
            token="", owner="o", repo="r", pr_number=1
        )
        with pytest.raises(CredentialMissingError) as exc:
            adapter.fetch_pr_info("https://github.com/o/r/pull/1")
        assert "GITHUB_TOKEN" in str(exc.value)

    def test_post_comment_raises_without_token(self):
        adapter = GitHubAdapter(
            token="", owner="o", repo="r", pr_number=1
        )
        with pytest.raises(CredentialMissingError):
            adapter.post_comment(
                "https://github.com/o/r/pull/1", "hi"
            )


# ---- fetch_pr_info ---------------------------------------------------

class TestFetchPRInfo:

    def test_success(self, adapter, pr_json, monkeypatch):
        call_count = 0

        def mock_request(
            method, url, *, headers=None, json=None, timeout=None
        ):
            nonlocal call_count
            call_count += 1
            if "diff" in headers.get("Accept", ""):
                return _mock_response(
                    text="diff --git a/f.py b/f.py"
                )
            return _mock_response(json_data=pr_json)

        monkeypatch.setattr(httpx, "request", mock_request)

        info = adapter.fetch_pr_info(
            "https://github.com/octo/hello/pull/42"
        )

        assert isinstance(info, PRInfo)
        assert info.platform == "github"
        assert info.title == "Fix bug"
        assert info.description == "Fixes #1"
        assert info.source_branch == "fix-branch"
        assert info.target_branch == "main"
        assert info.author == "dev"
        assert info.version_id == "abc123"
        assert "diff --git" in info.diff
        assert call_count == 2

    def test_401_raises_platform_api_error(
        self, adapter, monkeypatch
    ):
        def mock_request(
            method, url, *, headers=None, json=None, timeout=None
        ):
            return _mock_response(status_code=401)

        monkeypatch.setattr(httpx, "request", mock_request)

        with pytest.raises(PlatformAPIError) as exc:
            adapter.fetch_pr_info(
                "https://github.com/octo/hello/pull/42"
            )
        assert "authentication" in str(exc.value).lower()

    def test_404_raises_platform_api_error(
        self, adapter, monkeypatch
    ):
        def mock_request(
            method, url, *, headers=None, json=None, timeout=None
        ):
            return _mock_response(status_code=404)

        monkeypatch.setattr(httpx, "request", mock_request)

        with pytest.raises(PlatformAPIError) as exc:
            adapter.fetch_pr_info(
                "https://github.com/octo/hello/pull/42"
            )
        assert "not found" in str(exc.value).lower()

    def test_403_raises_platform_api_error(
        self, adapter, monkeypatch
    ):
        def mock_request(
            method, url, *, headers=None, json=None, timeout=None
        ):
            return _mock_response(status_code=403)

        monkeypatch.setattr(httpx, "request", mock_request)

        with pytest.raises(PlatformAPIError) as exc:
            adapter.fetch_pr_info(
                "https://github.com/octo/hello/pull/42"
            )
        assert "forbidden" in str(exc.value).lower()


# ---- post_comment ----------------------------------------------------

class TestPostComment:

    def test_success(self, adapter, monkeypatch):
        captured = {}

        def mock_request(
            method, url, *, headers=None, json=None, timeout=None
        ):
            captured["method"] = method
            captured["json"] = json
            return _mock_response(status_code=201)

        monkeypatch.setattr(httpx, "request", mock_request)

        adapter.post_comment(
            "https://github.com/octo/hello/pull/42",
            "Great PR!",
        )

        assert captured["method"] == "POST"
        body = captured["json"]["body"]
        assert "Great PR!" in body
        assert "auto-generated" in body.lower()

    def test_failure_raises_writeback_error(
        self, adapter, monkeypatch
    ):
        def mock_request(
            method, url, *, headers=None, json=None, timeout=None
        ):
            return _mock_response(status_code=422, text="err")

        monkeypatch.setattr(httpx, "request", mock_request)

        with pytest.raises(CommentWriteBackError):
            adapter.post_comment(
                "https://github.com/octo/hello/pull/42",
                "comment",
            )


# ---- Retry behaviour -------------------------------------------------

class TestRetry:

    def test_retries_on_network_error(
        self, adapter, pr_json, monkeypatch
    ):
        attempts = []

        def mock_request(
            method, url, *, headers=None, json=None, timeout=None
        ):
            attempts.append(1)
            if len(attempts) <= 1:
                raise httpx.ConnectError("connection refused")
            if "diff" in headers.get("Accept", ""):
                return _mock_response(
                    text="diff --git a/f.py b/f.py"
                )
            return _mock_response(json_data=pr_json)

        monkeypatch.setattr(httpx, "request", mock_request)
        # Speed up test by removing sleep
        monkeypatch.setattr("time.sleep", lambda _: None)

        info = adapter.fetch_pr_info(
            "https://github.com/octo/hello/pull/42"
        )
        assert info.title == "Fix bug"
        assert len(attempts) >= 2

    def test_retries_on_5xx(
        self, adapter, pr_json, monkeypatch
    ):
        call_count = 0

        def mock_request(
            method, url, *, headers=None, json=None, timeout=None
        ):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_response(status_code=502)
            if "diff" in headers.get("Accept", ""):
                return _mock_response(
                    text="diff --git a/f.py b/f.py"
                )
            return _mock_response(json_data=pr_json)

        monkeypatch.setattr(httpx, "request", mock_request)
        monkeypatch.setattr("time.sleep", lambda _: None)

        info = adapter.fetch_pr_info(
            "https://github.com/octo/hello/pull/42"
        )
        assert info.title == "Fix bug"
