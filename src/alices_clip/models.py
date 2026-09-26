"""Clipboard record contracts for Alice's Clip of Holding.

These dataclasses are the upstream contract every other module depends on.
Storage, capture, picker, and paste all read and write ``ClipRecord`` only.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ClipKind(str, Enum):
    """Canonical kind of a captured clipboard payload.

    Values are stable on disk (``meta.json``) and in the picker UI.
    """

    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    HTML = "html"
    RTF = "rtf"
    BINARY = "binary"


@dataclass(frozen=True)
class ClipRecord:
    """One archived copy event stored under the clips folder.

    Attributes:
        clip_id: Timestamp-based folder name, unique per capture.
        kind: Primary payload kind. Determines paste reconstruction.
        created_iso: Local ISO-8601 timestamp of capture.
        preview: Short human-readable preview shown in the picker.
        primary_name: Filename of the primary payload inside the clip folder.
        extra_names: Additional files saved with the same capture (sidecars).
        mime: Best-effort MIME type of the primary payload.
        byte_size: Size in bytes of the primary payload file.
        content_sha256: Hex digest of the primary payload. Used for de-dupe.
        source_names: Original filenames when the payload was a file drop.

    Notes:
        Paths are stored as names relative to the clip folder, never as
        absolute paths, so the bag can be moved without breaking records.
    """

    clip_id: str
    kind: ClipKind
    created_iso: str
    preview: str
    primary_name: str
    extra_names: list[str] = field(default_factory=list)
    mime: str = "application/octet-stream"
    byte_size: int = 0
    content_sha256: str = ""
    source_names: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize this record to a JSON-safe dictionary.

        Returns:
            A plain dict with enum values converted to strings.
        """
        payload = asdict(self)
        payload["kind"] = self.kind.value
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ClipRecord:
        """Rebuild a record from ``meta.json`` contents.

        Args:
            raw: Dictionary loaded from disk. ``kind`` may be a string.

        Returns:
            A validated ``ClipRecord``.

        Raises:
            KeyError: If a required field is missing.
            ValueError: If ``kind`` is not a known ``ClipKind``.
        """
        kind_raw = raw["kind"]
        kind = kind_raw if isinstance(kind_raw, ClipKind) else ClipKind(str(kind_raw))
        return cls(
            clip_id=str(raw["clip_id"]),
            kind=kind,
            created_iso=str(raw["created_iso"]),
            preview=str(raw.get("preview", "")),
            primary_name=str(raw["primary_name"]),
            extra_names=[str(name) for name in raw.get("extra_names", [])],
            mime=str(raw.get("mime", "application/octet-stream")),
            byte_size=int(raw.get("byte_size", 0)),
            content_sha256=str(raw.get("content_sha256", "")),
            source_names=[str(name) for name in raw.get("source_names", [])],
        )
