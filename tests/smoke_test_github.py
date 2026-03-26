"""Smoke test — calls the real GitHub API.

NOT intended for CI. Run manually:
    python -m pytest tests/smoke_test_github.py -v -s

Requires a valid GITHUB_TOKEN in .env (or environment).
"""

from __future__ import annotations

from src.platform.factory import PlatformFactory

TEST_PR_URL = (
    "https://github.com/pinguo-guzhongzhi/icc-agent-skills/pull/2"
)


def test_fetch_pr_info_real_api():
    """Fetch real PR info from GitHub and verify fields."""
    adapter = PlatformFactory.create_adapter(TEST_PR_URL)
    pr_info = adapter.fetch_pr_info(TEST_PR_URL)

    # Basic structural checks
    assert pr_info.platform == "github"
    assert pr_info.pr_url == TEST_PR_URL
    assert pr_info.pr_id == "pinguo-guzhongzhi/icc-agent-skills#2"
    assert pr_info.title  # non-empty
    assert pr_info.diff  # non-empty
    assert pr_info.source_branch  # non-empty
    assert pr_info.target_branch  # non-empty
    assert pr_info.author  # non-empty
    assert pr_info.version_id  # commit SHA

    print(f"\n--- Smoke Test Results ---")
    print(f"Title:         {pr_info.title}")
    print(f"Author:        {pr_info.author}")
    print(f"Branches:      {pr_info.source_branch} -> {pr_info.target_branch}")
    print(f"Version (SHA): {pr_info.version_id}")
    print(f"Diff length:   {len(pr_info.diff)} chars")
    print(f"Description:   {(pr_info.description or '(empty)')[:120]}")
