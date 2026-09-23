from __future__ import annotations

import os
import queue
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable

from .exporter import FPS, find_ffmpeg

try:
    import winsound
except ImportError:  # pragma: no cover - Windows is the supported desktop target.
    winsound = None


DISPLAY_WIDTH = 180
DISPLAY_HEIGHT = 320


class PreviewPlayer:
    """Small FFmpeg-backed player that streams one frame at a time into Tk."""

    def __init__(
        self,
        root,
        on_frame: Callable[[bytes, int, int], None],
        on_position: Callable[[float], None],
        on_state: Callable[[bool], None],
    ) -> None:
        self.root = root
        self.on_frame = on_frame
        self.on_position = on_position
        self.on_state = on_state
        self.process: subprocess.Popen | None = None
        self.frames: queue.Queue[bytes | None] = queue.Queue(maxsize=4)
        self.stop_event = threading.Event()
        self.token = 0
        self.started_at = 0.0
        self.start_offset = 0.0
        self.duration = 0.0
        self.frame_index = 0
        self.pending: bytes | None = None
        self.playing = False
        self.audio_temp = tempfile.TemporaryDirectory(prefix="mini-log-audio-", ignore_cleanup_errors=True)
        self.audio_path = Path(self.audio_temp.name) / "preview.wav"
        self.audio_ready = False
        self.audio_started = False

    def play(self, path: str | Path, start_seconds: float, duration: float) -> None:
        self.stop(notify=False)
        self.token += 1
        token = self.token
        self.frames = queue.Queue(maxsize=4)
        self.stop_event = threading.Event()
        self.start_offset = max(0.0, min(start_seconds, duration))
        self.duration = max(0.0, duration)
        self.frame_index = 0
        self.pending = None
        self.audio_ready = self._prepare_audio(path, self.start_offset, self.duration)
        self.audio_started = False
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.process = subprocess.Popen(
            [
                find_ffmpeg(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{self.start_offset:.3f}",
                "-i",
                str(path),
                "-an",
                "-vf",
                f"scale={DISPLAY_WIDTH}:{DISPLAY_HEIGHT}:flags=bilinear",
                "-pix_fmt",
                "rgb24",
                "-f",
                "rawvideo",
                "-",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        self.playing = True
        self.started_at = 0.0
        self.on_state(True)
        threading.Thread(target=self._read_frames, args=(token,), daemon=True).start()
        self.root.after(1, lambda: self._tick(token))

    def _read_frames(self, token: int) -> None:
        frame_size = DISPLAY_WIDTH * DISPLAY_HEIGHT * 3
        stdout = self.process.stdout if self.process else None
        if stdout is None:
            return
        while not self.stop_event.is_set() and token == self.token:
            chunks: list[bytes] = []
            remaining = frame_size
            while remaining and not self.stop_event.is_set():
                chunk = stdout.read(remaining)
                if not chunk:
                    remaining = -1
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            if remaining != 0:
                break
            frame = b"".join(chunks)
            while not self.stop_event.is_set() and token == self.token:
                try:
                    self.frames.put(frame, timeout=0.1)
                    break
                except queue.Full:
                    continue
        if token == self.token and not self.stop_event.is_set():
            while token == self.token and not self.stop_event.is_set():
                try:
                    self.frames.put(None, timeout=0.1)
                    break
                except queue.Full:
                    continue

    def _tick(self, token: int) -> None:
        if token != self.token or not self.playing:
            return
        if self.pending is None:
            try:
                self.pending = self.frames.get_nowait()
            except queue.Empty:
                self.root.after(5, lambda: self._tick(token))
                return
            if self.pending is None:
                self._finish()
                return
            if self.started_at == 0.0:
                self.started_at = time.monotonic()
                self._start_audio()

        target_elapsed = self.frame_index / FPS
        wait_seconds = target_elapsed - (time.monotonic() - self.started_at)
        if wait_seconds > 0.004:
            self.root.after(max(1, round(wait_seconds * 1000)), lambda: self._tick(token))
            return

        self.on_frame(self.pending, DISPLAY_WIDTH, DISPLAY_HEIGHT)
        self.pending = None
        self.frame_index += 1
        self.on_position(min(self.duration, self.start_offset + self.frame_index / FPS))
        self.root.after(1, lambda: self._tick(token))

    def _finish(self) -> None:
        self.playing = False
        self.on_position(self.duration)
        self.on_state(False)
        self._stop_audio()
        self._terminate_process()

    def stop(self, notify: bool = True) -> None:
        was_playing = self.playing
        self.token += 1
        self.playing = False
        self.stop_event.set()
        self.pending = None
        self._stop_audio()
        self._terminate_process()
        if notify and was_playing:
            self.on_state(False)

    def _terminate_process(self) -> None:
        process = self.process
        self.process = None
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                process.kill()

    def _prepare_audio(self, path: str | Path, start_seconds: float, duration: float) -> bool:
        try:
            self.audio_path.unlink(missing_ok=True)
        except OSError:
            return False
        remaining = max(0.0, duration - start_seconds)
        if remaining <= 0:
            return False
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        result = subprocess.run(
            [
                find_ffmpeg(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{start_seconds:.3f}",
                "-i",
                str(path),
                "-map",
                "0:a:0",
                "-vn",
                "-t",
                f"{remaining:.3f}",
                "-c:a",
                "pcm_s16le",
                "-ar",
                "48000",
                "-ac",
                "2",
                str(self.audio_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        return result.returncode == 0 and self.audio_path.is_file() and self.audio_path.stat().st_size > 44

    def _start_audio(self) -> None:
        if not self.audio_ready or winsound is None:
            return
        try:
            winsound.PlaySound(
                str(self.audio_path),
                winsound.SND_ASYNC | winsound.SND_FILENAME | winsound.SND_NODEFAULT,
            )
            self.audio_started = True
        except RuntimeError:
            self.audio_started = False

    def _stop_audio(self) -> None:
        if winsound is not None and self.audio_started:
            try:
                winsound.PlaySound(None, 0)
            except RuntimeError:
                pass
        self.audio_started = False

    def close(self) -> None:
        self.stop(notify=False)
        try:
            self.audio_temp.cleanup()
        except OSError:
            pass
