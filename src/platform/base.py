"""Abstract base class for platform adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.models import PRInfo


class PlatformAdapter(ABC):
    """Unified interface for interacting with code hosting platforms."""

    @abstractmethod
    def fetch_pr_info(self, pr_url: str) -> PRInfo:
        """Fetch complete PR information.

        Includes title, description, and diff.
        """
        ...

    @abstractmethod
    def post_comment(self, pr_url: str, comment: str) -> None:
        """Write a review comment back to the PR."""
        ...
