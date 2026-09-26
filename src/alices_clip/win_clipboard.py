"""Windows clipboard capture and restore.

Copy is observed by polling GetClipboardSequenceNumber. That catches
Ctrl+C, context-menu Copy, and application Copy commands. Restore writes
the chosen file back onto the OS clipboard in the matching native format.
"""

from __future__ import annotations

import ctypes
import hashlib
import io
import json
import logging
import shutil
import struct
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from alices_clip.models import ClipKind, ClipRecord
from alices_clip.storage import ClipStore

LOGGER = logging.getLogger(__name__)
IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".ico"
}
MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".txt": "text/plain",
    ".html": "text/html",
    ".htm": "text/html",
    ".rtf": "application/rtf",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".zip": "application/zip",
}


class User32:
    """Thin wrapper around the user32 calls used for sequence polling."""

    def __init__(self) -> None:
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            raise RuntimeError("ctypes.windll is only available on Windows.")
        self._dll = windll.user32
        self._dll.GetClipboardSequenceNumber.restype = ctypes.c_uint32

    def sequence(self) -> int:
        """Return the current clipboard sequence number."""
        return int(self._dll.GetClipboardSequenceNumber())


def _sha256_file(path: Path) -> str:
    """Hash a file in 1 MiB chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    """Hash an in-memory payload."""
    return hashlib.sha256(payload).hexdigest()


def _preview_text(text: str, limit: int = 160) -> str:
    """Collapse whitespace and trim for the picker row."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1] + "\u2026"


def _new_clip_id() -> str:
    """Build a filesystem-safe unique clip id from local time."""
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def _write_meta(folder: Path, record: ClipRecord) -> None:
    """Write meta.json beside the payload."""
    (folder / "meta.json").write_text(
        json.dumps(record.to_dict(), indent=2) + "\n", encoding="utf-8"
    )


class ClipboardBag:
    """Capture OS clipboard changes into the clip store and restore them."""

    def __init__(self, store: ClipStore) -> None:
        """Bind this bag to an existing store.

        Args:
            store: Filesystem clip store.

        Raises:
            RuntimeError: If the process is not running on Windows.
        """
        if sys.platform != "win32":
            raise RuntimeError("Alice's Clip of Holding currently requires Windows.")
        self.store = store
        self.user32 = User32()
        self.last_sequence = self.user32.sequence()
        self.ignore_sequence = -1
        self._win32clipboard = None

    def _wcb(self) -> Any:
        """Import win32clipboard lazily so non-Windows syntax checks pass."""
        if self._win32clipboard is None:
            import win32clipboard

            self._win32clipboard = win32clipboard
        return self._win32clipboard

    def poll(self) -> ClipRecord | None:
        """Archive a new clipboard payload if the sequence number moved."""
        current = self.user32.sequence()
        if current == self.last_sequence or current == self.ignore_sequence:
            self.last_sequence = current
            return None
        previous = self.last_sequence
        self.last_sequence = current
        try:
            return self._capture(previous_sequence=previous)
        except OSError:
            LOGGER.error("Clipboard capture failed", exc_info=True)
            return None

    def mark_own_write(self) -> None:
        """Ignore the next sequence bump caused by our own SetClipboard."""
        self.ignore_sequence = self.user32.sequence()

    def restore_to_clipboard(self, record: ClipRecord) -> bool:
        """Place a stored clip back on the OS clipboard."""
        path = self.store.primary_path(record)
        if not path.is_file():
            LOGGER.error("Primary payload missing for clip %s at %s", record.clip_id, path)
            return False
        try:
            if record.kind == ClipKind.TEXT:
                self._set_text(path.read_text(encoding="utf-8"))
            elif record.kind == ClipKind.HTML:
                self._set_html_and_text(path)
            elif record.kind == ClipKind.RTF:
                self._set_rtf(path)
            elif record.kind == ClipKind.IMAGE:
                self._set_image(path)
            else:
                extras = [self.store.clip_dir(record.clip_id) / name for name in record.extra_names]
                self._set_files([path] + [item for item in extras if item.is_file()])
            self.mark_own_write()
            self.last_sequence = self.user32.sequence()
            return True
        except OSError:
            LOGGER.error("Failed to restore clip %s", record.clip_id, exc_info=True)
            return False

    def _capture(self, previous_sequence: int) -> ClipRecord | None:
        """Inspect the current clipboard and persist the richest payload."""
        del previous_sequence
        wcb = self._wcb()
        if not self._open_with_retry():
            LOGGER.error("OpenClipboard failed after retries")
            return None
        try:
            has_files = bool(wcb.IsClipboardFormatAvailable(wcb.CF_HDROP))
            has_image = bool(
                wcb.IsClipboardFormatAvailable(wcb.CF_DIB)
                or wcb.IsClipboardFormatAvailable(wcb.CF_BITMAP)
            )
            has_text = bool(wcb.IsClipboardFormatAvailable(wcb.CF_UNICODETEXT))
            html_fmt = self._registered_format("HTML Format")
            rtf_fmt = self._registered_format("Rich Text Format")
            png_fmt = self._registered_format("PNG")
            has_html = bool(html_fmt and wcb.IsClipboardFormatAvailable(html_fmt))
            has_rtf = bool(rtf_fmt and wcb.IsClipboardFormatAvailable(rtf_fmt))
            has_png = bool(png_fmt and wcb.IsClipboardFormatAvailable(png_fmt))
        finally:
            wcb.CloseClipboard()
        if has_files:
            return self._capture_files()
        if has_png or has_image:
            return self._capture_image(prefer_png=has_png)
        if has_rtf:
            return self._capture_rtf()
        if has_html:
            return self._capture_html()
        if has_text:
            return self._capture_text()
        LOGGER.info("Clipboard changed but no supported format was present")
        return None

    def _open_with_retry(self, attempts: int = 8, delay_s: float = 0.02) -> bool:
        """Open the clipboard, retrying while another owner holds it."""
        wcb = self._wcb()
        for _ in range(attempts):
            try:
                wcb.OpenClipboard()
                return True
            except OSError:
                time.sleep(delay_s)
        return False

    def _registered_format(self, name: str) -> int:
        """Return a registered clipboard format id, or 0 if unknown."""
        try:
            return int(self._wcb().RegisterClipboardFormat(name))
        except OSError:
            LOGGER.error("RegisterClipboardFormat(%s) failed", name, exc_info=True)
            return 0

    def _capture_text(self) -> ClipRecord | None:
        """Save CF_UNICODETEXT as a UTF-8 .txt file."""
        text = self._get_unicode_text()
        if text is None:
            return None
        encoded = text.encode("utf-8")
        digest = _sha256_bytes(encoded)
        if self.store.find_by_hash(digest) is not None:
            return None
        return self._commit(ClipKind.TEXT, "item.txt", encoded, _preview_text(text), "text/plain")

    def _capture_html(self) -> ClipRecord | None:
        """Save HTML Format as .html and keep a plain-text sidecar."""
        raw = self._get_registered_bytes("HTML Format")
        if raw is None:
            return self._capture_text()
        digest = _sha256_bytes(raw)
        if self.store.find_by_hash(digest) is not None:
            return None
        html_body = _extract_html_fragment(raw)
        text = self._get_unicode_text()
        extras = {"item.txt": text.encode("utf-8")} if text else None
        return self._commit(
            ClipKind.HTML,
            "item.html",
            html_body.encode("utf-8"),
            _preview_text(text or html_body),
            "text/html",
            extras=extras,
            digest=digest,
        )

    def _capture_rtf(self) -> ClipRecord | None:
        """Save Rich Text Format as a genuine .rtf file."""
        raw = self._get_registered_bytes("Rich Text Format")
        if raw is None:
            return self._capture_text()
        digest = _sha256_bytes(raw)
        if self.store.find_by_hash(digest) is not None:
            return None
        preview = self._get_unicode_text() or raw[:200].decode("latin-1", errors="replace")
        return self._commit(
            ClipKind.RTF, "item.rtf", raw, _preview_text(preview), "application/rtf", digest=digest
        )

    def _capture_image(self, prefer_png: bool) -> ClipRecord | None:
        """Save a clipboard image in its genuine format when possible."""
        payload: bytes | None = None
        if prefer_png:
            payload = self._get_registered_bytes("PNG")
        if payload is None:
            from PIL import ImageGrab

            grabbed = ImageGrab.grabclipboard()
            if grabbed is None:
                return None
            if isinstance(grabbed, list):
                return self._capture_files()
            buffer = io.BytesIO()
            grabbed.save(buffer, format="PNG")
            payload = buffer.getvalue()
        digest = _sha256_bytes(payload)
        if self.store.find_by_hash(digest) is not None:
            return None
        return self._commit(ClipKind.IMAGE, "item.png", payload, "Image", "image/png", digest=digest)

    def _capture_files(self) -> ClipRecord | None:
        """Copy dropped files into the bag, preserving original extensions."""
        paths = self._get_drop_paths()
        files = [path for path in paths if path.is_file()]
        if not files:
            LOGGER.error("Clipboard file drop did not contain a readable file: %s", paths)
            return None
        digest = _sha256_file(files[0])
        if self.store.find_by_hash(digest) is not None:
            return None
        clip_id = _new_clip_id()
        folder = self.store.clip_dir(clip_id)
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
            mime=MIME.get(primary.suffix.lower(), "application/octet-stream"),
            byte_size=primary.stat().st_size,
            content_sha256=digest,
            source_names=[path.name for path in files],
        )
        _write_meta(folder, record)
        return self.store.add(record)

    def _commit(
        self,
        kind: ClipKind,
        primary_name: str,
        payload: bytes,
        preview: str,
        mime: str,
        extras: dict[str, bytes] | None = None,
        digest: str | None = None,
    ) -> ClipRecord:
        """Write a single-payload clip folder and index it."""
        clip_id = _new_clip_id()
        folder = self.store.clip_dir(clip_id)
        folder.mkdir(parents=True, exist_ok=True)
        primary = folder / primary_name
        primary.write_bytes(payload)
        extra_names: list[str] = []
        if extras:
            for name, content in extras.items():
                (folder / name).write_bytes(content)
                extra_names.append(name)
        record = ClipRecord(
            clip_id=clip_id,
            kind=kind,
            created_iso=datetime.now().isoformat(timespec="seconds"),
            preview=preview,
            primary_name=primary_name,
            extra_names=extra_names,
            mime=mime,
            byte_size=len(payload),
            content_sha256=digest or _sha256_bytes(payload),
        )
        _write_meta(folder, record)
        return self.store.add(record)

    def _get_unicode_text(self) -> str | None:
        """Read CF_UNICODETEXT, or None if absent."""
        wcb = self._wcb()
        if not self._open_with_retry():
            return None
        try:
            if not wcb.IsClipboardFormatAvailable(wcb.CF_UNICODETEXT):
                return None
            data = wcb.GetClipboardData(wcb.CF_UNICODETEXT)
            return None if data is None else str(data)
        except OSError:
            LOGGER.error("GetClipboardData(CF_UNICODETEXT) failed", exc_info=True)
            return None
        finally:
            wcb.CloseClipboard()

    def _get_registered_bytes(self, name: str) -> bytes | None:
        """Read a named registered clipboard format as raw bytes."""
        fmt = self._registered_format(name)
        if not fmt or not self._open_with_retry():
            return None
        wcb = self._wcb()
        try:
            if not wcb.IsClipboardFormatAvailable(fmt):
                return None
            data = wcb.GetClipboardData(fmt)
            if data is None:
                return None
            if isinstance(data, bytes):
                return data
            if isinstance(data, str):
                return data.encode("utf-8")
            return bytes(data)
        except OSError:
            LOGGER.error("GetClipboardData(%s) failed", name, exc_info=True)
            return None
        finally:
            wcb.CloseClipboard()

    def _get_drop_paths(self) -> list[Path]:
        """Read CF_HDROP as a list of filesystem paths."""
        wcb = self._wcb()
        if not self._open_with_retry():
            return []
        try:
            if not wcb.IsClipboardFormatAvailable(wcb.CF_HDROP):
                return []
            raw = wcb.GetClipboardData(wcb.CF_HDROP)
            return [] if not raw else [Path(item) for item in raw]
        except OSError:
            LOGGER.error("GetClipboardData(CF_HDROP) failed", exc_info=True)
            return []
        finally:
            wcb.CloseClipboard()

    def _set_text(self, text: str) -> None:
        """Write Unicode text onto the clipboard."""
        wcb = self._wcb()
        if not self._open_with_retry():
            raise OSError("OpenClipboard failed while setting text")
        try:
            wcb.EmptyClipboard()
            wcb.SetClipboardData(wcb.CF_UNICODETEXT, text)
        finally:
            wcb.CloseClipboard()

    def _set_html_and_text(self, html_path: Path) -> None:
        """Restore HTML plus a plain-text fallback when the sidecar exists."""
        html = html_path.read_text(encoding="utf-8")
        sidecar = html_path.with_name("item.txt")
        text = sidecar.read_text(encoding="utf-8") if sidecar.is_file() else html
        wcb = self._wcb()
        fmt = self._registered_format("HTML Format")
        if not self._open_with_retry():
            raise OSError("OpenClipboard failed while setting HTML")
        try:
            wcb.EmptyClipboard()
            wcb.SetClipboardData(wcb.CF_UNICODETEXT, text)
            if fmt:
                wcb.SetClipboardData(fmt, _wrap_html_clipboard(html))
        finally:
            wcb.CloseClipboard()

    def _set_rtf(self, rtf_path: Path) -> None:
        """Restore RTF bytes onto the clipboard."""
        raw = rtf_path.read_bytes()
        wcb = self._wcb()
        fmt = self._registered_format("Rich Text Format")
        if not self._open_with_retry():
            raise OSError("OpenClipboard failed while setting RTF")
        try:
            wcb.EmptyClipboard()
            if fmt:
                wcb.SetClipboardData(fmt, raw)
            wcb.SetClipboardData(wcb.CF_UNICODETEXT, raw.decode("latin-1", errors="replace"))
        finally:
            wcb.CloseClipboard()

    def _set_image(self, image_path: Path) -> None:
        """Restore an image as CF_DIB plus PNG when the file is a PNG."""
        from PIL import Image

        image = Image.open(image_path)
        wcb = self._wcb()
        if not self._open_with_retry():
            raise OSError("OpenClipboard failed while setting image")
        try:
            wcb.EmptyClipboard()
            wcb.SetClipboardData(wcb.CF_DIB, _image_to_dib_bytes(image))
            if image_path.suffix.lower() == ".png":
                png_fmt = self._registered_format("PNG")
                if png_fmt:
                    wcb.SetClipboardData(png_fmt, image_path.read_bytes())
        finally:
            wcb.CloseClipboard()

    def _set_files(self, paths: list[Path]) -> None:
        """Restore files as CF_HDROP, preferring PowerShell Set-Clipboard."""
        if _set_files_via_powershell(paths):
            return
        payload = _build_dropfiles([str(path) for path in paths])
        wcb = self._wcb()
        if not self._open_with_retry():
            raise OSError("OpenClipboard failed while setting files")
        try:
            wcb.EmptyClipboard()
            wcb.SetClipboardData(wcb.CF_HDROP, payload)
        finally:
            wcb.CloseClipboard()


def _extract_html_fragment(raw: bytes) -> str:
    """Pull the HTML body out of a Windows HTML Format payload."""
    text = raw.decode("utf-8", errors="replace")
    lower = text.lower()
    start = lower.find("<!--startfragment-->")
    end = lower.find("<!--endfragment-->")
    if start != -1 and end != -1 and end > start:
        fragment = text[start + len("<!--startfragment-->") : end]
        return "<!DOCTYPE html><html><body>" + fragment.strip() + "</body></html>\n"
    header_end = text.find("<html")
    return text[header_end:] if header_end != -1 else text


def _wrap_html_clipboard(html: str) -> bytes:
    """Wrap an HTML document in the CF_HTML header Windows expects."""
    header_template = (
        "Version:0.9\r\n"
        "StartHTML:{start_html:08d}\r\n"
        "EndHTML:{end_html:08d}\r\n"
        "StartFragment:{start_frag:08d}\r\n"
        "EndFragment:{end_frag:08d}\r\n"
    )
    placeholder = header_template.format(start_html=0, end_html=0, start_frag=0, end_frag=0)
    prefix = "<!--StartFragment-->"
    suffix = "<!--EndFragment-->"
    body = prefix + html + suffix
    start_html = len(placeholder)
    start_frag = start_html + len(prefix)
    end_frag = start_frag + len(html)
    end_html = start_html + len(body)
    header = header_template.format(
        start_html=start_html, end_html=end_html, start_frag=start_frag, end_frag=end_frag
    )
    return (header + body).encode("utf-8")


def _image_to_dib_bytes(image: Any) -> bytes:
    """Convert a PIL image to CF_DIB bytes (BMP without the 14-byte file header)."""
    converted = image.convert("RGB")
    buffer = io.BytesIO()
    converted.save(buffer, format="BMP")
    return buffer.getvalue()[14:]


def _set_files_via_powershell(paths: list[Path]) -> bool:
    """Use Windows PowerShell Set-Clipboard -Path when available."""
    if not paths:
        return False
    items = ", ".join("'" + str(path).replace("'", "''") + "'" for path in paths)
    command = f"Set-Clipboard -Path @({items})"
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command", command],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError):
        LOGGER.error("PowerShell Set-Clipboard failed to start", exc_info=True)
        return False
    if completed.returncode != 0:
        LOGGER.error(
            "PowerShell Set-Clipboard exited %s: %s", completed.returncode, completed.stderr
        )
        return False
    return True


def _build_dropfiles(paths: list[str]) -> bytes:
    """Build a DROPFILES memory block for CF_HDROP."""
    joined = "\0".join(paths) + "\0\0"
    encoded = joined.encode("utf-16le")
    header = struct.pack("<Iiiii", 20, 0, 0, 0, 1)
    return header + encoded
