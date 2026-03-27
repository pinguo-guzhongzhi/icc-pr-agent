"""Environment-based configuration for the PR Review system."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(env_path: str = ".env") -> None:
    """Load key=value pairs from a .env file into os.environ (if file exists)."""
    path = Path(env_path)
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not os.environ.get(key):
            os.environ[key] = value


@dataclass
class Config:
    """Lazily loaded configuration backed by environment variables."""

    # Platform tokens
    github_token: str = ""
    gitlab_token: str = ""
    gitlab_url: str = "https://gitlab.com"
    codeup_token: str = ""
    codeup_org_id: str = ""

    # LLM settings
    llm_api_key: str = ""
    llm_model: str = "gpt-4"
    llm_base_url: str = ""

    # General settings
    log_level: str = "INFO"
    review_storage_dir: str = ".pr_reviews"
    pr_review_exclude: list[str] = field(default_factory=list)
    skills_dir: str = ""

    # Webhook secrets
    webhook_secret_github: str = ""
    webhook_secret_gitlab: str = ""
    webhook_secret_codeup: str = ""

    @classmethod
    def from_env(cls, dotenv_path: str = ".env") -> Config:
        """Create a Config instance from current environment variables.

        Loads .env file first (won't override existing env vars).
        """
        _load_dotenv(dotenv_path)
        exclude_raw = os.environ.get("PR_REVIEW_EXCLUDE", "")
        exclude_patterns = [
            p.strip() for p in exclude_raw.split(",") if p.strip()
        ]

        return cls(
            github_token=os.environ.get("GITHUB_TOKEN", ""),
            gitlab_token=os.environ.get("GITLAB_TOKEN", ""),
            gitlab_url=os.environ.get("GITLAB_URL", "https://gitlab.com"),
            codeup_token=os.environ.get("CODEUP_TOKEN", ""),
            codeup_org_id=os.environ.get("CODEUP_ORG_ID", ""),
            llm_api_key=os.environ.get("LLM_API_KEY", ""),
            llm_model=os.environ.get("LLM_MODEL", "gpt-4"),
            llm_base_url=os.environ.get("LLM_BASE_URL", ""),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            review_storage_dir=os.environ.get(
                "REVIEW_STORAGE_DIR", ".pr_reviews"
            ),
            pr_review_exclude=exclude_patterns,
            skills_dir=os.environ.get("SKILLS_DIR", ""),
            webhook_secret_github=os.environ.get("WEBHOOK_SECRET_GITHUB", ""),
            webhook_secret_gitlab=os.environ.get("WEBHOOK_SECRET_GITLAB", ""),
            webhook_secret_codeup=os.environ.get(
                "WEBHOOK_SECRET_CODEUP", ""
            ),
        )
