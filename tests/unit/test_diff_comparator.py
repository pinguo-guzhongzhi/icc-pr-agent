"""Unit tests for DiffComparator."""

from src.diff_comparator import DiffComparator
from src.models import ReviewDiffReport, ReviewIssue, ReviewResult


def _issue(
    file_path: str = "src/app.py",
    line_number: int | None = 10,
    severity: str = "warning",
    category: str = "quality",
    description: str = "unused import",
    suggestion: str | None = "Remove the import",
) -> ReviewIssue:
    return ReviewIssue(
        file_path=file_path,
        line_number=line_number,
        severity=severity,
        category=category,
        description=description,
        suggestion=suggestion,
    )


def _result(*issues: ReviewIssue, summary: str = "Review done") -> ReviewResult:
    return ReviewResult(
        summary=summary,
        issues=list(issues),
        reviewed_at="2024-01-01T00:00:00Z",
    )


class TestDiffComparator:
    def setup_method(self) -> None:
        self.comparator = DiffComparator()

    # ---- basic classification ----

    def test_identical_results_all_unresolved(self) -> None:
        issue = _issue()
        prev = _result(issue)
        curr = _result(issue)
        report = self.comparator.compare(prev, curr)

        assert len(report.improved) == 0
        assert len(report.unresolved) == 1
        assert len(report.new_issues) == 0
        assert report.unresolved[0]["file_path"] == issue.file_path

    def test_issue_fixed_becomes_improved(self) -> None:
        prev = _result(_issue(description="unused import"))
        curr = _result()  # no issues
        report = self.comparator.compare(prev, curr)

        assert len(report.improved) == 1
        assert len(report.unresolved) == 0
        assert len(report.new_issues) == 0
        assert "resolution" in report.improved[0]

    def test_new_issue_detected(self) -> None:
        prev = _result()
        new = _issue(description="SQL injection risk", category="security", severity="critical")
        curr = _result(new)
        report = self.comparator.compare(prev, curr)

        assert len(report.improved) == 0
        assert len(report.unresolved) == 0
        assert len(report.new_issues) == 1
        assert report.new_issues[0]["description"] == "SQL injection risk"
        assert report.new_issues[0]["line_number"] == new.line_number
        assert report.new_issues[0]["suggestion"] == new.suggestion

    def test_mixed_classification(self) -> None:
        fixed = _issue(description="unused import", category="quality")
        still_there = _issue(description="missing docstring", category="quality", file_path="src/utils.py")
        brand_new = _issue(description="hardcoded secret", category="security", file_path="src/config.py")

        prev = _result(fixed, still_there)
        curr = _result(still_there, brand_new)
        report = self.comparator.compare(prev, curr)

        assert len(report.improved) == 1
        assert report.improved[0]["description"] == "unused import"
        assert len(report.unresolved) == 1
        assert report.unresolved[0]["description"] == "missing docstring"
        assert len(report.new_issues) == 1
        assert report.new_issues[0]["description"] == "hardcoded secret"

    # ---- matching logic ----

    def test_match_requires_same_file_path(self) -> None:
        a = _issue(file_path="a.py", description="unused import")
        b = _issue(file_path="b.py", description="unused import")
        report = self.comparator.compare(_result(a), _result(b))

        # different file → not matched → a is improved, b is new
        assert len(report.improved) == 1
        assert len(report.new_issues) == 1

    def test_match_requires_same_category(self) -> None:
        a = _issue(category="quality", description="unused import")
        b = _issue(category="bug", description="unused import")
        report = self.comparator.compare(_result(a), _result(b))

        assert len(report.improved) == 1
        assert len(report.new_issues) == 1

    def test_fuzzy_description_containment(self) -> None:
        a = _issue(description="unused import")
        b = _issue(description="unused import os module")
        report = self.comparator.compare(_result(a), _result(b))

        # "unused import" is contained in "unused import os module" → match
        assert len(report.unresolved) == 1
        assert len(report.improved) == 0
        assert len(report.new_issues) == 0

    def test_fuzzy_description_case_insensitive(self) -> None:
        a = _issue(description="Unused Import")
        b = _issue(description="unused import")
        report = self.comparator.compare(_result(a), _result(b))

        assert len(report.unresolved) == 1

    # ---- edge cases ----

    def test_both_empty(self) -> None:
        report = self.comparator.compare(_result(), _result())
        assert report == ReviewDiffReport(improved=[], unresolved=[], new_issues=[])

    def test_previous_empty(self) -> None:
        curr = _result(_issue())
        report = self.comparator.compare(_result(), curr)
        assert len(report.new_issues) == 1
        assert len(report.improved) == 0
        assert len(report.unresolved) == 0

    def test_current_empty(self) -> None:
        prev = _result(_issue())
        report = self.comparator.compare(prev, _result())
        assert len(report.improved) == 1
        assert len(report.unresolved) == 0
        assert len(report.new_issues) == 0

    def test_improved_item_has_required_fields(self) -> None:
        prev = _result(_issue(severity="critical", category="bug", description="NPE"))
        report = self.comparator.compare(prev, _result())
        item = report.improved[0]
        assert "file_path" in item
        assert "description" in item
        assert "category" in item
        assert "severity" in item
        assert "resolution" in item

    def test_unresolved_item_has_required_fields(self) -> None:
        issue = _issue()
        report = self.comparator.compare(_result(issue), _result(issue))
        item = report.unresolved[0]
        assert "file_path" in item
        assert "description" in item
        assert "category" in item
        assert "severity" in item

    def test_new_issue_item_has_required_fields(self) -> None:
        issue = _issue(line_number=42, suggestion="fix it")
        report = self.comparator.compare(_result(), _result(issue))
        item = report.new_issues[0]
        assert "file_path" in item
        assert "description" in item
        assert "category" in item
        assert "severity" in item
        assert "line_number" in item
        assert "suggestion" in item

    def test_duplicate_issues_matched_one_to_one(self) -> None:
        """Two identical issues in previous should each match at most one in current."""
        issue = _issue(description="dup")
        prev = _result(issue, issue)
        curr = _result(issue)  # only one copy
        report = self.comparator.compare(prev, curr)

        assert len(report.unresolved) == 1
        assert len(report.improved) == 1
