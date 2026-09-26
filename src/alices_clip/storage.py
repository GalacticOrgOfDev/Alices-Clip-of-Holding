"""On-disk bag: one folder per clip plus a JSON index."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from alices_clip.config import AppConfig
from alices_clip.models import ClipRecord

LOGGER = logging.getLogger(__name__)


class ClipStore:
    """Filesystem-backed clip bag.

    Layout::

        <data_dir>/
          index.json
          clips/
            <clip_id>/
              meta.json
              item.txt | photo.png | original.docx | ...
    """

    def __init__(self, data_dir: Path, config: AppConfig) -> None:
        """Create the store and load any existing index.

        Args:
            data_dir: Per-user application data directory.
            config: Active settings, including ``max_clips``.
        """
        self.data_dir = data_dir
        self.config = config
        self.clips_dir = config.clips_dir(data_dir)
        self.index_path = config.index_path(data_dir)
        self.clips_dir.mkdir(parents=True, exist_ok=True)
        self._records: list[ClipRecord] = []
        self._load_index()

    def records(self) -> list[ClipRecord]:
        """Return clips newest-first without exposing the internal list."""
        return list(self._records)

    def clip_dir(self, clip_id: str) -> Path:
        """Return the folder for one clip id."""
        return self.clips_dir / clip_id

    def primary_path(self, record: ClipRecord) -> Path:
        """Return the absolute path of a record's primary payload."""
        return self.clip_dir(record.clip_id) / record.primary_name

    def add(self, record: ClipRecord) -> ClipRecord:
        """Insert a record at the front of the index and prune if needed.

        Args:
            record: Fully written clip whose folder already exists.

        Returns:
            The same record, for call-site convenience.
        """
        self._records.insert(0, record)
        self._prune()
        self._save_index()
        return record

    def remove(self, clip_id: str) -> None:
        """Delete a clip folder and drop it from the index.

        Args:
            clip_id: Folder name of the clip to remove.
        """
        self._records = [item for item in self._records if item.clip_id != clip_id]
        target = self.clip_dir(clip_id)
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        self._save_index()

    def latest(self) -> ClipRecord | None:
        """Return the newest clip, or None when the bag is empty."""
        return self._records[0] if self._records else None

    def find_by_hash(self, digest: str) -> ClipRecord | None:
        """Return the newest clip whose primary payload matches ``digest``."""
        if not digest:
            return None
        for record in self._records:
            if record.content_sha256 == digest:
                return record
        return None

    def _load_index(self) -> None:
        """Load ``index.json``, rebuilding from folders if it is missing."""
        if not self.index_path.is_file():
            self._rebuild_from_disk()
            return
        try:
            raw_list = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            LOGGER.error("Index unreadable at %s; rebuilding", self.index_path, exc_info=True)
            self._rebuild_from_disk()
            return
        records: list[ClipRecord] = []
        if isinstance(raw_list, list):
            for raw in raw_list:
                try:
                    records.append(ClipRecord.from_dict(raw))
                except (KeyError, ValueError, TypeError):
                    LOGGER.error("Skipping corrupt index entry: %s", raw, exc_info=True)
        self._records = records

    def _rebuild_from_disk(self) -> None:
        """Scan clip folders and rebuild the index from each ``meta.json``."""
        rebuilt: list[ClipRecord] = []
        if self.clips_dir.is_dir():
            for folder in sorted(self.clips_dir.iterdir(), reverse=True):
                meta = folder / "meta.json"
                if not meta.is_file():
                    continue
                try:
                    raw = json.loads(meta.read_text(encoding="utf-8"))
                    rebuilt.append(ClipRecord.from_dict(raw))
                except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError):
                    LOGGER.error("Skipping corrupt clip folder %s", folder, exc_info=True)
        self._records = rebuilt
        self._save_index()

    def _prune(self) -> None:
        """Drop oldest clips once ``max_clips`` is exceeded."""
        overflow = self._records[self.config.max_clips :]
        self._records = self._records[: self.config.max_clips]
        for record in overflow:
            folder = self.clip_dir(record.clip_id)
            if folder.is_dir():
                shutil.rmtree(folder, ignore_errors=True)

    def _save_index(self) -> None:
        """Persist the in-memory index."""
        payload = [record.to_dict() for record in self._records]
        self.index_path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
