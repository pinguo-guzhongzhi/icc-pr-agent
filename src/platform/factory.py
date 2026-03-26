"""Factory for creating platform adapters based on PR URL."""

from __future__ import annotations

import re

from src.config import Config
from src.exceptions import UnknownPlatformError
from src.platform.base import PlatformAdapter

# GitHub PR URL pattern:
#   https://github.com/{owner}/{repo}/pull/{number}
_GITHUB_PR_RE = re.compile(
    r"^https?://github\.com/"
    r"(?P<owner>[^/]+)/(?P<repo>[^/]+)"
    r"/pull/(?P<number>\d+)(?:/.*)?$"
)

_SUPPORTED_FORMATS = (
    "Supported PR URL formats:\n"
    "  - GitHub: "
    "https://github.com/{owner}/{repo}/pull/{number}"
)


class PlatformFactory:
    """Detect platform from a PR URL and create the adapter."""

    @staticmethod
    def detect_platform(pr_url: str) -> str:
        """Identify the platform type from a PR URL.

        Returns:
            Platform identifier (e.g. ``"github"``).

        Raises:
            UnknownPlatformError: URL doesn't match any pattern.
        """
        if _GITHUB_PR_RE.match(pr_url):
            return "github"

        raise UnknownPlatformError(
            f"Cannot identify platform from URL: {pr_url}\n"
            f"{_SUPPORTED_FORMATS}"
        )

    @staticmethod
    def create_adapter(pr_url: str) -> PlatformAdapter:
        """Create a platform adapter for the given PR URL.

        Credentials are loaded from environment variables.

        Raises:
            UnknownPlatformError: URL doesn't match any pattern.
        """
        platform = PlatformFactory.detect_platform(pr_url)

        if platform == "github":
            match = _GITHUB_PR_RE.match(pr_url)
            assert match is not None
            owner = match.group("owner")
            repo = match.group("repo")
            pr_number = int(match.group("number"))

            config = Config.from_env()

            from src.platform.github_adapter import GitHubAdapter

            return GitHubAdapter(
                token=config.github_token,
                owner=owner,
                repo=repo,
                pr_number=pr_number,
            )

        raise UnknownPlatformError(  # pragma: no cover
            f"Platform '{platform}' recognized but no adapter.\n"
            f"{_SUPPORTED_FORMATS}"
        )
