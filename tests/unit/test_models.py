"""Unit tests for core data models."""

from src.models import (
    Batch,
    FileGroup,
    FilterResult,
    PRInfo,
    ReviewDiffReport,
    ReviewIssue,
    ReviewOptions,
    ReviewOutput,
    ReviewRecord,
    ReviewResult,
    SubAgentResult,
    SymbolEntry,
    TokenUsageByGroup,
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


class TestFileGroup:
    def test_creation(self):
        fg = FileGroup(
            name="backend",
            file_paths=["src/main.go", "api/user.proto"],
            file_diffs=["diff1", "diff2"],
            total_chars=100,
        )
        assert fg.name == "backend"
        assert fg.file_paths == ["src/main.go", "api/user.proto"]
        assert fg.file_diffs == ["diff1", "diff2"]
        assert fg.total_chars == 100

    def test_empty_group(self):
        fg = FileGroup(name="empty", file_paths=[], file_diffs=[], total_chars=0)
        assert fg.file_paths == []
        assert fg.total_chars == 0


class TestBatch:
    def test_creation(self):
        batch = Batch(
            group_name="backend",
            batch_index=0,
            file_paths=["src/main.go"],
            diff_content="diff content here",
            char_count=17,
        )
        assert batch.group_name == "backend"
        assert batch.batch_index == 0
        assert batch.file_paths == ["src/main.go"]
        assert batch.diff_content == "diff content here"
        assert batch.char_count == 17

    def test_second_batch(self):
        batch = Batch(
            group_name="frontend",
            batch_index=1,
            file_paths=["app.tsx", "style.css"],
            diff_content="more diff",
            char_count=9,
        )
        assert batch.batch_index == 1
        assert len(batch.file_paths) == 2


class TestSymbolEntry:
    def test_creation(self):
        entry = SymbolEntry(
            name="CreateOrder",
            signature="func (s *OrderService) CreateOrder(ctx context.Context) error",
            file_path="internal/service/order.go",
            line_number=42,
            kind="method",
            language="go",
        )
        assert entry.name == "CreateOrder"
        assert entry.kind == "method"
        assert entry.language == "go"
        assert entry.line_number == 42

    def test_proto_entry(self):
        entry = SymbolEntry(
            name="UserService",
            signature="service UserService { ... }",
            file_path="api/user.proto",
            line_number=10,
            kind="service",
            language="proto",
        )
        assert entry.kind == "service"
        assert entry.language == "proto"


class TestSubAgentResult:
    def test_successful_result(self):
        review = ReviewResult(
            summary="Found 1 issue",
            issues=[],
            reviewed_at="2024-01-15T10:30:00Z",
        )
        result = SubAgentResult(
            group_name="backend",
            batch_index=0,
            result=review,
            error=None,
            prompt_tokens=500,
            completion_tokens=300,
            total_tokens=800,
            elapsed_seconds=2.5,
        )
        assert result.group_name == "backend"
        assert result.result is not None
        assert result.error is None
        assert result.total_tokens == 800
        assert result.elapsed_seconds == 2.5

    def test_failed_result(self):
        result = SubAgentResult(
            group_name="frontend",
            batch_index=1,
            result=None,
            error="Timeout after 300s",
        )
        assert result.result is None
        assert result.error == "Timeout after 300s"

    def test_defaults(self):
        result = SubAgentResult(
            group_name="infra",
            batch_index=0,
            result=None,
            error=None,
        )
        assert result.prompt_tokens == 0
        assert result.completion_tokens == 0
        assert result.total_tokens == 0
        assert result.elapsed_seconds == 0.0


class TestTokenUsageByGroup:
    def test_creation(self):
        usage = TokenUsageByGroup(
            group_name="backend",
            prompt_tokens=5000,
            completion_tokens=3200,
            total_tokens=8200,
        )
        assert usage.group_name == "backend"
        assert usage.prompt_tokens == 5000
        assert usage.completion_tokens == 3200
        assert usage.total_tokens == 8200


class TestReviewOutput:
    def test_backward_compatibility_default_none(self):
        """token_usage_by_group defaults to None for backward compatibility."""
        output = ReviewOutput(
            review_result=ReviewResult(
                summary="OK", issues=[], reviewed_at="2024-01-15T10:30:00Z"
            ),
            diff_report=None,
            formatted_comment="comment",
            written_back=True,
        )
        assert output.token_usage_by_group is None
        assert output.prompt_tokens == 0
        assert output.completion_tokens == 0
        assert output.total_tokens == 0

    def test_with_token_usage_by_group(self):
        usage = [
            TokenUsageByGroup("backend", 5000, 3200, 8200),
            TokenUsageByGroup("frontend", 2000, 1100, 3100),
        ]
        output = ReviewOutput(
            review_result=ReviewResult(
                summary="Found issues", issues=[], reviewed_at="2024-01-15T10:30:00Z"
            ),
            diff_report=None,
            formatted_comment="comment",
            written_back=True,
            prompt_tokens=7000,
            completion_tokens=4300,
            total_tokens=11300,
            token_usage_by_group=usage,
        )
        assert output.token_usage_by_group is not None
        assert len(output.token_usage_by_group) == 2
        assert output.token_usage_by_group[0].group_name == "backend"
        assert output.token_usage_by_group[1].total_tokens == 3100
        assert output.total_tokens == 11300
