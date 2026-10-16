"""Screenshot and short screen recording into the clip bag.

Uses mss for fast Windows capture and Pillow (already a dependency) to
write PNGs and animated GIFs. Recordings are intentionally short and
lightweight so they fit the bag model.
"""

from __future__ import annotations

import hashlib
import io
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from PIL import Image

from alices_clip.models import ClipKind, ClipRecord
from alices_clip.storage import ClipStore

LOGGER = logging.getLogger(__name__)


def _sha256_bytes(payload: bytes) -> str:
    """Hash an in-memory payload."""
    return hashlib.sha256(payload).hexdigest()


def _new_clip_id() -> str:
    """Build a filesystem-safe unique clip id from local time."""
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")


class ScreenCapture:
    """Capture screenshots and short recordings into a ClipStore."""

    def __init__(self, store: ClipStore) -> None:
        self.store = store
        self._recording = False
        self._record_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    @property
    def is_recording(self) -> bool:
        return self._recording

    def take_screenshot(self, on_done: Callable[[ClipRecord | None], None] | None = None) -> None:
        """Capture the primary monitor and add it to the bag as a PNG clip.

        Runs on a background thread so the tray stays responsive.
        """
        def _work() -> None:
            record = self._capture_png()
            if on_done is not None:
                on_done(record)

        threading.Thread(target=_work, name="alice-screenshot", daemon=True).start()

    def _capture_png(self) -> ClipRecord | None:
        """Grab the primary monitor and commit it as an IMAGE clip."""
        try:
            import mss
        except ImportError:
            LOGGER.error("mss is not installed; screenshot unavailable")
            return None
        try:
            with mss.mss() as sct:
                mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                shot = sct.grab(mon)
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            payload = buffer.getvalue()
        except Exception:
            LOGGER.error("Screenshot capture failed", exc_info=True)
            return None

        digest = _sha256_bytes(payload)
        if self.store.find_by_hash(digest) is not None:
            LOGGER.info("Screenshot identical to an existing clip; skipped")
            return None

        clip_id = _new_clip_id()
        folder = self.store.clip_dir(clip_id)
        folder.mkdir(parents=True, exist_ok=True)
        primary = folder / "screenshot.png"
        primary.write_bytes(payload)

        record = ClipRecord(
            clip_id=clip_id,
            kind=ClipKind.IMAGE,
            created_iso=datetime.now().isoformat(timespec="seconds"),
            preview="Screenshot",
            primary_name="screenshot.png",
            mime="image/png",
            byte_size=len(payload),
            content_sha256=digest,
            source_names=["screenshot.png"],
        )
        (folder / "meta.json").write_text(
            __import__("json").dumps(record.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )
        return self.store.add(record)

    def start_recording(
        self,
        duration_s: float = 8.0,
        fps: int = 8,
        on_done: Callable[[ClipRecord | None], None] | None = None,
    ) -> None:
        """Begin a short animated-GIF recording of the primary monitor."""
        if self._recording:
            return
        self._recording = True
        self._stop_event.clear()

        def _work() -> None:
            record = self._record_gif(duration_s=duration_s, fps=fps)
            self._recording = False
            if on_done is not None:
                on_done(record)

        self._record_thread = threading.Thread(target=_work, name="alice-recording", daemon=True)
        self._record_thread.start()

    def stop_recording(self) -> None:
        """Ask the recording thread to finish early."""
        self._stop_event.set()

    def _record_gif(self, duration_s: float, fps: int) -> ClipRecord | None:
        """Capture frames and write an animated GIF clip."""
        try:
            import mss
        except ImportError:
            LOGGER.error("mss is not installed; recording unavailable")
            return None

        frames: list[Image.Image] = []
        interval = 1.0 / max(1, fps)
        deadline = time.monotonic() + duration_s

        try:
            with mss.mss() as sct:
                mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                while time.monotonic() < deadline and not self._stop_event.is_set():
                    start = time.monotonic()
                    shot = sct.grab(mon)
                    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                    # Downscale a bit so the GIF stays reasonable
                    img.thumbnail((960, 540))
                    frames.append(img)
                    elapsed = time.monotonic() - start
                    sleep = interval - elapsed
                    if sleep > 0:
                        time.sleep(sleep)
        except Exception:
            LOGGER.error("Screen recording failed", exc_info=True)
            return None

        if len(frames) < 2:
            LOGGER.info("Recording too short; discarded")
            return None

        buffer = io.BytesIO()
        frames[0].save(
            buffer,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=int(1000 / fps),
            loop=0,
            optimize=True,
        )
        payload = buffer.getvalue()
        digest = _sha256_bytes(payload)

        clip_id = _new_clip_id()
        folder = self.store.clip_dir(clip_id)
        folder.mkdir(parents=True, exist_ok=True)
        primary = folder / "recording.gif"
        primary.write_bytes(payload)

        record = ClipRecord(
            clip_id=clip_id,
            kind=ClipKind.IMAGE,
            created_iso=datetime.now().isoformat(timespec="seconds"),
            preview=f"Recording ({len(frames)} frames)",
            primary_name="recording.gif",
            mime="image/gif",
            byte_size=len(payload),
            content_sha256=digest,
            source_names=["recording.gif"],
        )
        (folder / "meta.json").write_text(
            __import__("json").dumps(record.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )
        return self.store.add(record)
