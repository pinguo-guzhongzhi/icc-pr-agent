"""Unit tests for core data models."""

from src.models import (
    FilterResult,
    PRInfo,
    ReviewDiffReport,
    ReviewIssue,
    ReviewOptions,
    ReviewRecord,
    ReviewResult,
)


class TestPRInfo:
    def test_creation(self):
        info = PRInfo(
            platform="github",
            pr_id="123",
            pr_url="https://github.com/owner/repo/pull/123",
            title="Fix bug",
            description="Fixes a critical bug",
            diff="--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new",
            source_branch="fix/bug",
            target_branch="main",
            author="dev",
            version_id="abc123",
        )
        assert info.platform == "github"
        assert info.pr_id == "123"


class TestReviewIssue:
    def test_creation_with_line_number(self):
        issue = ReviewIssue(
            file_path="src/main.py",
            line_number=42,
            severity="critical",
            category="bug",
            description="Null pointer dereference",
            suggestion="Add null check",
        )
        assert issue.line_number == 42
        assert issue.suggestion == "Add null check"

    def test_creation_without_line_number(self):
        issue = ReviewIssue(
            file_path="src/main.py",
            line_number=None,
            severity="suggestion",
            category="improvement",
            description="Consider refactoring",
            suggestion=None,
        )
        assert issue.line_number is None
        assert issue.suggestion is None


class TestReviewRecord:
    def _make_record(self, with_diff_report=True):
        issues = [
            ReviewIssue(
                file_path="src/app.py",
                line_number=10,
                severity="warning",
                category="quality",
                description="Long function",
                suggestion="Split into smaller functions",
            ),
            ReviewIssue(
                file_path="src/db.py",
                line_number=None,
                severity="critical",
                category="security",
                description="SQL injection risk",
                suggestion=None,
            ),
        ]
        result = ReviewResult(
            summary="Found 2 issues",
            issues=issues,
            reviewed_at="2024-01-15T10:30:00Z",
        )
        diff_report = None
        if with_diff_report:
            diff_report = ReviewDiffReport(
                improved=[{"file_path": "old.py", "description": "Fixed"}],
                unresolved=[{"file_path": "src/db.py", "description": "Still risky"}],
                new_issues=[{"file_path": "src/app.py", "description": "New issue"}],
            )
        return ReviewRecord(
            record_id="550e8400-e29b-41d4-a716-446655440000",
            pr_id="123",
            pr_url="https://github.com/owner/repo/pull/123",
            platform="github",
            version_id="abc123",
            review_result=result,
            diff_report=diff_report,
            created_at="2024-01-15T10:30:00Z",
        )

    def test_to_dict(self):
        record = self._make_record()
        d = record.to_dict()
        assert d["record_id"] == "550e8400-e29b-41d4-a716-446655440000"
        assert d["platform"] == "github"
        assert len(d["review_result"]["issues"]) == 2
        assert d["diff_report"]["improved"][0]["file_path"] == "old.py"

    def test_from_dict(self):
        record = self._make_record()
        d = record.to_dict()
        restored = ReviewRecord.from_dict(d)
        assert restored.record_id == record.record_id
        assert restored.pr_id == record.pr_id
        assert restored.review_result.summary == record.review_result.summary
        assert len(restored.review_result.issues) == 2
        assert restored.review_result.issues[0].file_path == "src/app.py"
        assert restored.diff_report is not None
        assert len(restored.diff_report.improved) == 1

    def test_round_trip(self):
        record = self._make_record()
        restored = ReviewRecord.from_dict(record.to_dict())
        assert restored == record

    def test_round_trip_without_diff_report(self):
        record = self._make_record(with_diff_report=False)
        assert record.diff_report is None
        restored = ReviewRecord.from_dict(record.to_dict())
        assert restored == record
        assert restored.diff_report is None


class TestReviewOptions:
    def test_defaults(self):
        opts = ReviewOptions()
        assert opts.template_path is None
        assert opts.write_back is True
        assert opts.exclude_patterns is None
        assert opts.use_default_excludes is True

    def test_custom(self):
        opts = ReviewOptions(
            template_path="custom.md.j2",
            write_back=False,
            exclude_patterns=["*.lock"],
            use_default_excludes=False,
        )
        assert opts.template_path == "custom.md.j2"
        assert opts.write_back is False


class TestFilterResult:
    def test_creation(self):
        fr = FilterResult(
            filtered_diff="diff content",
            excluded_files=[{"file_path": "pkg.lock", "matched_pattern": "*.lock"}],
            included_file_count=5,
            excluded_file_count=1,
        )
        assert fr.included_file_count == 5
        assert len(fr.excluded_files) == 1
