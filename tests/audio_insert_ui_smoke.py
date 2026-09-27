"""Windows GUI smoke for insertion and short audio audition."""

from __future__ import annotations

import math
import subprocess
import sys
import tempfile
import time
import wave
from array import array
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
from tkinterdnd2 import TkinterDnD

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.exporter import find_ffmpeg
from app.main_window import MiniLogApp
from app.models import Project
import app.audio_audition as audio_module


class QuietSound:
    SND_ASYNC = 1
    SND_FILENAME = 2
    SND_NODEFAULT = 4

    def __init__(self):
        self.calls: list[str | None] = []

    def PlaySound(self, filename, _flags):
        self.calls.append(filename)


def wait_for_audio(root, app, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        root.update()
        if app.audio_audition.playing_path is not None:
            return app.audio_audition.playing_path
        time.sleep(0.01)
    raise AssertionError("試聴WAVが作成されませんでした")


def rms(path: Path) -> float:
    with wave.open(str(path), "rb") as recording:
        samples = array("h", recording.readframes(recording.getnframes()))
    return math.sqrt(sum(value * value for value in samples) / len(samples))


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="mini-log-audio-insert-") as temporary:
        folder = Path(temporary)
        images = [folder / f"base-{index}.png" for index in range(5)]
        additions = [folder / f"new-{index}.png" for index in range(4)]
        for path in images + additions:
            Image.new("RGB", (300, 400), "#7aab96").save(path)
        video = folder / "insert.mp4"
        subprocess.run(
            [find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
             "-i", "color=c=green:s=300x400:r=30:d=0.7", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
            check=True,
        )
        sound = folder / "tone.wav"
        subprocess.run(
            [find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
             "-i", "sine=frequency=440:duration=1", "-ar", "48000", "-ac", "2", str(sound)],
            check=True,
        )
        long_sound = folder / "long-tone.wav"
        subprocess.run(
            [find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
             "-i", "sine=frequency=440:duration=12", "-ar", "48000", "-ac", "2", str(long_sound)],
            check=True,
        )

        quiet = QuietSound()
        with patch.object(audio_module, "winsound", quiet):
            root = TkinterDnD.Tk()
            root.withdraw()
            app = MiniLogApp(root)
            app._add_material_paths(map(str, images))
            app.select_cut(2)
            app._add_material_paths(map(str, additions[:2]))
            assert [Path(c.source_path) for c in app.project.cuts] == [
                *images[:3], *additions[:2], *images[3:],
            ]
            assert app.selected_index == 3
            app.select_cut(2)
            with patch("app.main_window.filedialog.askopenfilenames", return_value=(str(video),)):
                app.add_materials()
            assert Path(app.project.cuts[3].source_path) == video
            app.select_cut(2)
            app._on_files_dropped(SimpleNamespace(data=root.tk.call("list", str(additions[2]))))
            assert Path(app.project.cuts[3].source_path) == additions[2]
            app.selected_index = None
            app.selected_cut_ids.clear()
            app._add_material_paths([str(additions[3])])
            assert Path(app.project.cuts[-1].source_path) == additions[3]
            assert [c.order for c in app.project.cuts] == list(range(len(app.project.cuts)))
            saved = folder / "insert.minilog"
            app.project.save(saved)
            assert [c.source_path for c in Project.load(saved).cuts] == [c.source_path for c in app.project.cuts]

            app.select_cut(0)
            app._set_bgm_path(sound)
            app._set_cut_audio_path(sound)
            app.project.bgm_volume = 0.6
            app.project.cuts[0].audio_volume = 0.6
            signature = app._project_signature()
            app.preview_path.touch()
            app.preview_generated_signature = signature
            app.preview_state_var.set("プレビューの準備ができました")
            app.toggle_bgm_audition()
            first_wav = wait_for_audio(root, app)
            loud = rms(first_wav)
            assert app.bgm_audition_button.cget("text") == "■ 停止"
            assert app._project_signature() == signature
            assert app.preview_state_var.get() == "プレビューの準備ができました"
            app.toggle_bgm_audition()
            assert app.audio_audition.kind is None
            app.bgm_volume_var.set(30)
            app._on_bgm_volume_changed(30)
            assert app.preview_state_var.get() == "このプレビューは現在の編集内容と異なります"
            state = app.preview_state_var.get()
            app.toggle_bgm_audition()
            quiet_wav = wait_for_audio(root, app)
            assert 0.45 < rms(quiet_wav) / loud < 0.55
            app.toggle_cut_audio_audition()
            wait_for_audio(root, app)
            assert app.audio_audition.kind == "cut" and app.bgm_audition_button.cget("text") == "▶ 試聴"
            assert None in quiet.calls
            deadline = time.monotonic() + 2.0
            while app.audio_audition.kind is not None and time.monotonic() < deadline:
                root.update()
                time.sleep(0.01)
            assert app.audio_audition.kind is None  # short source ends without user intervention
            app.toggle_cut_audio_audition()
            wait_for_audio(root, app)
            app.select_cut(1)
            assert app.audio_audition.kind is None
            assert app.cut_audio_audition_button.instate(["disabled"])
            app.select_cut(0)
            app.toggle_cut_audio_audition()
            wait_for_audio(root, app)
            app.preview_project_snapshot = Project.from_dict(app.project.to_dict())
            with patch.object(app.player, "play") as preview_play:
                app.play_preview()
                assert app.audio_audition.kind is None
                preview_play.assert_called_once()
            assert app._project_signature() != signature  # only the deliberate volume change above
            assert app.preview_state_var.get() == state  # audition never marks stale
            app._set_bgm_path(long_sound)
            app.toggle_bgm_audition()
            capped = wait_for_audio(root, app)
            with wave.open(str(capped), "rb") as recording:
                assert 9.9 <= recording.getnframes() / recording.getframerate() <= 10.0
            app._on_close()
    print("Audio/insertion GUI smoke: PASS")


if __name__ == "__main__":
    main()
