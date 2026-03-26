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

        {storage_dir}/{platform}/{pr_id_sanitized}/{timestamp}_{version_id}.json
    """

    def __init__(self, storage_dir: str = ".pr_reviews") -> None:
        self._storage_dir = Path(storage_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, record: ReviewRecord) -> None:
        """Save *record* to disk as a JSON file."""
        pr_dir = self._pr_dir(record.platform, record.pr_id)
        pr_dir.mkdir(parents=True, exist_ok=True)

        filename = self._make_filename(record.created_at, record.version_id)
        filepath = pr_dir / filename

        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(
                record.to_dict(), fh, ensure_ascii=False, indent=2,
            )

        logger.info(
            "Saved review record %s to %s",
            record.record_id, filepath,
        )

    def get_latest(self, pr_id: str) -> ReviewRecord | None:
        """Return the most recent record for *pr_id*, or ``None``."""
        history = self.get_history(pr_id)
        if not history:
            return None
        return history[-1]

    def get_history(self, pr_id: str) -> list[ReviewRecord]:
        """Return all records for *pr_id*, ascending."""
        records: list[ReviewRecord] = []

        sanitized = self._sanitize_pr_id(pr_id)

        # Search across all platform directories
        if not self._storage_dir.exists():
            return records

        for platform_dir in self._storage_dir.iterdir():
            if not platform_dir.is_dir():
                continue
            pr_dir = platform_dir / sanitized
            if not pr_dir.is_dir():
                continue
            for json_file in pr_dir.glob("*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    records.append(ReviewRecord.from_dict(data))
                except (
                    json.JSONDecodeError, KeyError, TypeError,
                ) as exc:
                    logger.warning(
                        "Skipping invalid record file %s: %s",
                        json_file, exc,
                    )

        records.sort(key=lambda r: r.created_at)
        return records

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _pr_dir(self, platform: str, pr_id: str) -> Path:
        sanitized = self._sanitize_pr_id(pr_id)
        return self._storage_dir / platform / sanitized

    @staticmethod
    def _sanitize_pr_id(pr_id: str) -> str:
        """Replace ``/`` and ``#`` with ``_``."""
        return pr_id.replace("/", "_").replace("#", "_")

    @staticmethod
    def _make_filename(
        created_at: str, version_id: str,
    ) -> str:
        """Build filename, sanitising ``:`` to ``-``."""
        safe_ts = created_at.replace(":", "-")
        return f"{safe_ts}_{version_id}.json"
