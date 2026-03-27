"""Shared pytest fixtures for PR Review tests."""

import pytest


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Ensure tests don't leak environment variable changes."""
    # Remove any PR Review related env vars to isolate tests
    env_keys = [
        "GITHUB_TOKEN",
        "GITLAB_TOKEN",
        "GITLAB_URL",
        "CODEUP_TOKEN",
        "CODEUP_ORG_ID",
        "LLM_API_KEY",
        "LLM_MODEL",
        "LLM_BASE_URL",
        "LOG_LEVEL",
        "REVIEW_STORAGE_DIR",
        "PR_REVIEW_EXCLUDE",
        "WEBHOOK_SECRET_GITHUB",
        "WEBHOOK_SECRET_GITLAB",
        "WEBHOOK_SECRET_CODEUP",
        "MAX_REVIEW_ISSUES",
        "MAX_REVIEW_CONCURRENCY",
        "REVIEW_TIMEOUT",
        "SKILLS_DIR",
    ]
    for key in env_keys:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def tmp_storage(tmp_path):
    """Provide a temporary directory for review record storage."""
    return tmp_path / ".pr_reviews"
