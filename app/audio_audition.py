"""Short, single-source Windows audio audition for the editing UI."""

from __future__ import annotations

import os
import queue
import subprocess
import tempfile
import threading
import wave
from pathlib import Path
from typing import Callable

from .exporter import find_ffmpeg

try:
    import winsound
except ImportError:  # pragma: no cover - Windows is the supported desktop target.
    winsound = None


class AudioAudition:
    MAX_SECONDS = 10.0

    def __init__(self, root, on_state: Callable[[str | None], None], on_error: Callable[[str], None] | None = None):
        self.root = root
        self.on_state = on_state
        self.on_error = on_error
        self.temp = tempfile.TemporaryDirectory(prefix="mini-log-audition-", ignore_cleanup_errors=True)
        self.results: queue.Queue[tuple[int, Path, float, str | None]] = queue.Queue()
        self.token = 0
        self.kind: str | None = None
        self.source_path: str | None = None
        self.owner_id: str | None = None
        self.playing_path: Path | None = None
        self.timer_id: str | None = None
        self.closed = False

    def play(self, kind: str, source_path: str, volume: float, owner_id: str | None = None) -> None:
        self.stop()
        if self.closed:
            return
        if winsound is None:
            if self.on_error:
                self.on_error("この環境では音声を試聴できません")
            return
        self.token += 1
        token = self.token
        self.kind = kind
        self.source_path = source_path
        self.owner_id = owner_id
        self.on_state(kind)
        threading.Thread(
            target=self._prepare,
            args=(token, source_path, max(0.0, min(float(volume), 1.0))),
            daemon=True,
        ).start()
        self.root.after(40, self._poll)

    def _prepare(self, token: int, source_path: str, volume: float) -> None:
        output = Path(self.temp.name) / f"audition-{token}.wav"
        duration = 0.0
        error = None
        try:
            result = subprocess.run(
                [
                    find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                    "-i", source_path, "-map", "0:a:0", "-vn", "-t", str(self.MAX_SECONDS),
                    "-af", f"volume={volume:.3f}", "-c:a", "pcm_s16le", "-ar", "48000",
                    "-ac", "2", str(output),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if result.returncode != 0 or not output.is_file():
                raise ValueError("音声ファイルを試聴できませんでした")
            with wave.open(str(output), "rb") as recording:
                duration = recording.getnframes() / recording.getframerate()
            if duration <= 0:
                raise ValueError("音声ファイルに再生できる音がありません")
        except Exception as exc:
            error = str(exc)
        if token != self.token or self.closed:
            output.unlink(missing_ok=True)
            if self.closed:
                try:
                    output.parent.rmdir()
                except OSError:
                    pass
            return
        self.results.put((token, output, duration, error))

    def _poll(self) -> None:
        try:
            while True:
                token, output, duration, error = self.results.get_nowait()
                if token != self.token or self.closed:
                    output.unlink(missing_ok=True)
                    continue
                if error is not None:
                    output.unlink(missing_ok=True)
                    self.stop()
                    if self.on_error:
                        self.on_error(error)
                    return
                try:
                    winsound.PlaySound(
                        str(output), winsound.SND_ASYNC | winsound.SND_FILENAME | winsound.SND_NODEFAULT,
                    )
                except RuntimeError:
                    output.unlink(missing_ok=True)
                    self.stop()
                    if self.on_error:
                        self.on_error("音声を再生できませんでした")
                    return
                self.playing_path = output
                self.timer_id = self.root.after(round(duration * 1000) + 100, self.stop)
                return
        except queue.Empty:
            pass
        if self.kind is not None and not self.closed:
            self.root.after(40, self._poll)

    def stop(self) -> None:
        self.token += 1
        if self.timer_id is not None:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None
        if self.playing_path is not None:
            try:
                winsound.PlaySound(None, 0)
            except RuntimeError:
                pass
            try:
                self.playing_path.unlink(missing_ok=True)
            except OSError:
                pass
            self.playing_path = None
        was_active = self.kind is not None
        self.kind = None
        self.source_path = None
        self.owner_id = None
        if was_active:
            self.on_state(None)

    def close(self) -> None:
        self.stop()
        self.closed = True
        try:
            while True:
                _, output, _, _ = self.results.get_nowait()
                output.unlink(missing_ok=True)
        except queue.Empty:
            pass
        self.temp.cleanup()
