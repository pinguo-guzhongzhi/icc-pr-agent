"""Unit tests for RecordStore."""

from __future__ import annotations

import json

from src.models import (
    ReviewDiffReport,
    ReviewIssue,
    ReviewRecord,
    ReviewResult,
)
from src.record_store import RecordStore


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _make_record(
    *,
    record_id: str = "rec-1",
    pr_id: str = "owner/repo#42",
    pr_url: str = "https://github.com/owner/repo/pull/42",
    platform: str = "github",
    version_id: str = "abc123",
    created_at: str = "2024-01-15T10:30:00",
    summary: str = "Looks good",
    diff_report: ReviewDiffReport | None = None,
    trace: list[dict] | None = None,
) -> ReviewRecord:
    result = ReviewResult(
        summary=summary,
        issues=[
            ReviewIssue(
                file_path="src/main.py",
                line_number=10,
                severity="warning",
                category="quality",
                description="Unused import",
                suggestion="Remove it",
            )
        ],
        reviewed_at=created_at,
    )
    return ReviewRecord(
        record_id=record_id,
        pr_id=pr_id,
        pr_url=pr_url,
        platform=platform,
        version_id=version_id,
        review_result=result,
        diff_report=diff_report,
        created_at=created_at,
        trace=trace,
    )


# -------------------------------------------------------------------
# Tests — save
# -------------------------------------------------------------------

class TestRecordStoreSave:
    """Tests for RecordStore.save (single-file-per-PR)."""

    def test_save_creates_json_file(self, tmp_path):
        store = RecordStore(storage_dir=str(tmp_path))
        store.save(_make_record())

        pr_file = tmp_path / "github" / "owner" / "repo" / "prs" / "42.json"
        assert pr_file.is_file()

        with open(pr_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["record_id"] == "rec-1"

    def test_save_appends_to_existing(self, tmp_path):
        store = RecordStore(storage_dir=str(tmp_path))
        store.save(_make_record(record_id="r1", created_at="2024-01-15T10:00:00"))
        store.save(_make_record(record_id="r2", created_at="2024-01-16T14:00:00"))

        pr_file = tmp_path / "github" / "owner" / "repo" / "prs" / "42.json"
        with open(pr_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        assert len(data) == 2
        assert data[0]["record_id"] == "r1"
        assert data[1]["record_id"] == "r2"

    def test_save_with_diff_report(self, tmp_path):
        store = RecordStore(storage_dir=str(tmp_path))
        diff_report = ReviewDiffReport(
            improved=[{"issue": "fixed"}],
            unresolved=[],
            new_issues=[],
        )
        store.save(_make_record(diff_report=diff_report))

        pr_file = tmp_path / "github" / "owner" / "repo" / "prs" / "42.json"
        with open(pr_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        assert data[0]["diff_report"]["improved"] == [{"issue": "fixed"}]

    def test_save_with_trace(self, tmp_path):
        store = RecordStore(storage_dir=str(tmp_path))
        trace = [{"group_name": "backend", "batch_index": 0, "message_count": 5}]
        store.save(_make_record(trace=trace))

        pr_file = tmp_path / "github" / "owner" / "repo" / "prs" / "42.json"
        with open(pr_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        assert data[0]["trace"] == trace


# -------------------------------------------------------------------
# Tests — get_latest
# -------------------------------------------------------------------

class TestRecordStoreGetLatest:
    """Tests for RecordStore.get_latest."""

    def test_returns_none_when_no_records(self, tmp_path):
        store = RecordStore(storage_dir=str(tmp_path))
        assert store.get_latest("owner/repo#42") is None

    def test_returns_none_when_dir_missing(self, tmp_path):
        store = RecordStore(storage_dir=str(tmp_path / "nonexistent"))
        assert store.get_latest("owner/repo#42") is None

    def test_returns_most_recent_record(self, tmp_path):
        store = RecordStore(storage_dir=str(tmp_path))
        store.save(_make_record(record_id="r1", created_at="2024-01-15T10:00:00"))
        store.save(_make_record(record_id="r2", created_at="2024-01-16T14:00:00"))

        latest = store.get_latest("owner/repo#42")
        assert latest is not None
        assert latest.record_id == "r2"


# -------------------------------------------------------------------
# Tests — get_history
# -------------------------------------------------------------------

class TestRecordStoreGetHistory:
    """Tests for RecordStore.get_history."""

    def test_empty_history(self, tmp_path):
        store = RecordStore(storage_dir=str(tmp_path))
        assert store.get_history("owner/repo#42") == []

    def test_returns_sorted_ascending(self, tmp_path):
        store = RecordStore(storage_dir=str(tmp_path))
        store.save(_make_record(record_id="r2", created_at="2024-01-16T14:00:00"))
        store.save(_make_record(record_id="r1", created_at="2024-01-15T10:00:00"))
        store.save(_make_record(record_id="r3", created_at="2024-01-17T08:00:00"))

        history = store.get_history("owner/repo#42")
        assert len(history) == 3
        assert [r.record_id for r in history] == ["r1", "r2", "r3"]

    def test_latest_matches_last_history(self, tmp_path):
        store = RecordStore(storage_dir=str(tmp_path))
        store.save(_make_record(record_id="r1", created_at="2024-01-15T10:00:00"))
        store.save(_make_record(record_id="r2", created_at="2024-01-16T14:00:00"))

        history = store.get_history("owner/repo#42")
        latest = store.get_latest("owner/repo#42")
        assert latest is not None
        assert latest.record_id == history[-1].record_id

    def test_different_pr_ids_isolated(self, tmp_path):
        store = RecordStore(storage_dir=str(tmp_path))
        store.save(_make_record(record_id="r1", pr_id="owner/repo#42"))
        store.save(_make_record(record_id="r2", pr_id="owner/repo#99"))

        assert len(store.get_history("owner/repo#42")) == 1
        assert len(store.get_history("owner/repo#99")) == 1
        assert store.get_history("owner/repo#42")[0].record_id == "r1"
        assert store.get_history("owner/repo#99")[0].record_id == "r2"

    def test_handles_corrupt_file(self, tmp_path):
        """Corrupt JSON file returns empty history without crashing."""
        store = RecordStore(storage_dir=str(tmp_path))
        pr_file = tmp_path / "github" / "owner" / "repo" / "prs" / "42.json"
        pr_file.parent.mkdir(parents=True)
        pr_file.write_text("not valid json", encoding="utf-8")

        assert store.get_history("owner/repo#42") == []
