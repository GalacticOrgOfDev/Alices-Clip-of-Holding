"""One-shot shell actions: copy paths into the bag, paste a clip into a folder."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from alices_clip.config import AppConfig, default_data_dir, load_config
from alices_clip.models import ClipKind, ClipRecord
from alices_clip.storage import ClipStore

LOGGER = logging.getLogger(__name__)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".ico"}


def open_store() -> ClipStore:
    """Load the on-disk bag using the current user config."""
    data_dir = default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    config: AppConfig = load_config(data_dir)
    return ClipStore(data_dir, config)


def ingest_paths(paths: list[Path]) -> ClipRecord | None:
    """Archive existing files into the bag, preserving name and extension."""
    files = [path for path in paths if path.is_file()]
    if not files:
        LOGGER.error("No readable files to ingest: %s", paths)
        return None
    store = open_store()
    digest = _sha256_file(files[0])
    existing = store.find_by_hash(digest)
    if existing is not None:
        return existing
    clip_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    folder = store.clip_dir(clip_id)
    folder.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for source in files:
        dest = folder / source.name
        if dest.exists():
            dest = folder / f"{source.stem}-{len(copied)}{source.suffix}"
        shutil.copy2(source, dest)
        copied.append(dest.name)
    primary = folder / copied[0]
    kind = ClipKind.IMAGE if primary.suffix.lower() in IMAGE_EXTENSIONS else ClipKind.FILE
    record = ClipRecord(
        clip_id=clip_id,
        kind=kind,
        created_iso=datetime.now().isoformat(timespec="seconds"),
        preview=", ".join(copied[:4]),
        primary_name=copied[0],
        extra_names=copied[1:],
        mime="application/octet-stream",
        byte_size=primary.stat().st_size,
        content_sha256=digest,
        source_names=[path.name for path in files],
    )
    (folder / "meta.json").write_text(json.dumps(record.to_dict(), indent=2) + "\n", encoding="utf-8")
    return store.add(record)


def paste_record_into_directory(record: ClipRecord, destination: Path) -> list[Path]:
    """Write a stored clip into a folder as real files."""
    if not destination.is_dir():
        raise NotADirectoryError(str(destination))
    store = open_store()
    written: list[Path] = []
    source_dir = store.clip_dir(record.clip_id)
    for name in [record.primary_name, *record.extra_names]:
        source = source_dir / name
        if not source.is_file() or name == "meta.json":
            continue
        dest = _unique_dest(destination / name)
        shutil.copy2(source, dest)
        written.append(dest)
    if not written:
        raise FileNotFoundError(f"clip {record.clip_id} has no payload files")
    return written


def _unique_dest(path: Path) -> Path:
    """Avoid clobbering an existing file in the paste target."""
    if not path.exists():
        return path
    index = 1
    while True:
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _sha256_file(path: Path) -> str:
    """Hash a file in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()
