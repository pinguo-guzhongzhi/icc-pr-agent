"""DiffComparator — compares two ReviewResults and produces a ReviewDiffReport."""

from __future__ import annotations

from src.models import ReviewDiffReport, ReviewIssue, ReviewResult


class DiffComparator:
    """Compare previous and current review results to classify issues."""

    def compare(
        self, previous: ReviewResult, current: ReviewResult
    ) -> ReviewDiffReport:
        """Compare two review results and classify issues.

        Matching logic: two issues match when they share the same
        ``file_path`` **and** ``category`` **and** their descriptions are
        similar (one contains the other, or they are equal).

        Classification:
        - *improved*: issues present in *previous* but not matched in *current*
        - *unresolved*: issues present in both *previous* and *current*
        - *new_issues*: issues present in *current* but not matched in *previous*
        """
        # Track which current issues have been matched
        matched_current: set[int] = set()

        improved: list[dict] = []
        unresolved: list[dict] = []

        for prev_issue in previous.issues:
            match_idx = self._find_match(prev_issue, current.issues, matched_current)
            if match_idx is not None:
                matched_current.add(match_idx)
                cur_issue = current.issues[match_idx]
                unresolved.append(
                    {
                        "file_path": cur_issue.file_path,
                        "description": cur_issue.description,
                        "category": cur_issue.category,
                        "severity": cur_issue.severity,
                    }
                )
            else:
                improved.append(
                    {
                        "file_path": prev_issue.file_path,
                        "description": prev_issue.description,
                        "category": prev_issue.category,
                        "severity": prev_issue.severity,
                        "resolution": "Issue no longer present in the latest review",
                    }
                )

        new_issues: list[dict] = []
        for idx, cur_issue in enumerate(current.issues):
            if idx not in matched_current:
                new_issues.append(
                    {
                        "file_path": cur_issue.file_path,
                        "description": cur_issue.description,
                        "category": cur_issue.category,
                        "severity": cur_issue.severity,
                        "line_number": cur_issue.line_number,
                        "suggestion": cur_issue.suggestion,
                    }
                )

        return ReviewDiffReport(
            improved=improved,
            unresolved=unresolved,
            new_issues=new_issues,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _descriptions_match(a: str, b: str) -> bool:
        """Return True when two descriptions are considered similar.

        Similarity is defined as equality or one string containing the other.
        """
        if a == b:
            return True
        a_lower = a.lower()
        b_lower = b.lower()
        return a_lower in b_lower or b_lower in a_lower

    @classmethod
    def _find_match(
        cls,
        issue: ReviewIssue,
        candidates: list[ReviewIssue],
        already_matched: set[int],
    ) -> int | None:
        """Find the first matching candidate index for *issue*.

        A candidate matches when it has the same ``file_path`` and
        ``category`` and a similar ``description``.  Already-matched
        indices are skipped.
        """
        for idx, candidate in enumerate(candidates):
            if idx in already_matched:
                continue
            if (
                candidate.file_path == issue.file_path
                and candidate.category == issue.category
                and cls._descriptions_match(issue.description, candidate.description)
            ):
                return idx
        return None
