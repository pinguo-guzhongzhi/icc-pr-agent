"""Review record storage — persists ReviewRecord as JSON files on disk."""

from __future__ import annotations

import json
from pathlib import Path

from src.logger import get_logger
from src.models import ReviewRecord

logger = get_logger(__name__)


class RecordStore:
    """Persist and retrieve :class:`ReviewRecord` instances as JSON files.

    Directory layout::

        {storage_dir}/{platform}/{owner}/{repo}/prs/{pr_number}.json

    Each file contains a JSON array of review records (newest last).
    """

    def __init__(self, storage_dir: str = ".pr_reviews") -> None:
        self._storage_dir = Path(storage_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, record: ReviewRecord) -> None:
        """Append *record* to the PR's JSON file."""
        filepath = self._pr_file(record.platform, record.pr_id)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # Load existing records
        records = self._load_array(filepath)
        records.append(record.to_dict())

        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(records, fh, ensure_ascii=False, indent=2)

        logger.info(
            "Saved review record %s to %s (%d total)",
            record.record_id, filepath, len(records),
        )

    def get_latest(self, pr_id: str) -> ReviewRecord | None:
        """Return the most recent record for *pr_id*, or ``None``."""
        history = self.get_history(pr_id)
        if not history:
            return None
        return history[-1]

    def get_history(self, pr_id: str) -> list[ReviewRecord]:
        """Return all records for *pr_id*, ascending by created_at."""
        records: list[ReviewRecord] = []

        if not self._storage_dir.exists():
            return records

        owner, repo, number = self._parse_pr_id(pr_id)

        # Search across all platform directories
        for platform_dir in self._storage_dir.iterdir():
            if not platform_dir.is_dir():
                continue

            # New layout: {platform}/{owner}/{repo}/prs/{number}.json
            pr_file = platform_dir / owner / repo / "prs" / f"{number}.json"
            if pr_file.is_file():
                records.extend(self._load_records(pr_file))
                continue

            # Legacy: directory-based layout
            legacy_dir = platform_dir / owner / repo / "prs" / number
            if legacy_dir.is_dir():
                for json_file in legacy_dir.glob("*.json"):
                    if json_file.name.endswith("_trace.json"):
                        continue
                    records.extend(self._load_records(json_file))
                continue

            # Oldest legacy: flat layout
            flat = platform_dir / self._sanitize_pr_id(pr_id)
            if flat.is_dir():
                for json_file in flat.glob("*.json"):
                    records.extend(self._load_records(json_file))

        records.sort(key=lambda r: r.created_at)
        return records

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _pr_file(self, platform: str, pr_id: str) -> Path:
        owner, repo, number = self._parse_pr_id(pr_id)
        return self._storage_dir / platform / owner / repo / "prs" / f"{number}.json"

    @staticmethod
    def _load_array(filepath: Path) -> list[dict]:
        """Load JSON array from file. Returns empty list if missing/invalid."""
        if not filepath.is_file():
            return []
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                return data
            # Single object (legacy) → wrap in list
            if isinstance(data, dict):
                return [data]
            return []
        except (json.JSONDecodeError, OSError):
            return []

    @staticmethod
    def _load_records(filepath: Path) -> list[ReviewRecord]:
        """Load ReviewRecord(s) from a JSON file (array or single object)."""
        records = []
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skipping invalid file %s: %s", filepath, exc)
            return records

        items = data if isinstance(data, list) else [data]
        for item in items:
            try:
                records.append(ReviewRecord.from_dict(item))
            except (KeyError, TypeError) as exc:
                logger.warning("Skipping invalid record in %s: %s", filepath, exc)
        return records

    @staticmethod
    def _parse_pr_id(pr_id: str) -> tuple[str, str, str]:
        """Parse 'owner/repo#number' into (owner, repo, number)."""
        if "#" in pr_id:
            repo_part, number = pr_id.rsplit("#", 1)
        else:
            repo_part, number = pr_id, "unknown"
        if "/" in repo_part:
            owner, repo = repo_part.split("/", 1)
        else:
            owner, repo = "unknown", repo_part
        return owner, repo, number

    @staticmethod
    def _sanitize_pr_id(pr_id: str) -> str:
        """Replace ``/`` and ``#`` with ``_`` (legacy compat)."""
        return pr_id.replace("/", "_").replace("#", "_")
