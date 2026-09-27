"""Audition volume must follow the currently visible slider, not a stale model value."""

from __future__ import annotations

import math
import subprocess
import sys
import tempfile
import time
import unittest
import wave
from array import array
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.audio_audition import AudioAudition
from app.exporter import find_ffmpeg
from app.main_window import MiniLogApp
from app.models import Cut, Project
import app.audio_audition as audio_module


class FakeRoot:
    def after(self, _delay, _callback):
        return "timer"

    def after_cancel(self, _timer):
        pass


class FakeVar:
    def __init__(self, value=0):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeSound:
    SND_ASYNC = 1
    SND_FILENAME = 2
    SND_NODEFAULT = 4

    def __init__(self):
        self.paths = []

    def PlaySound(self, path, _flags):
        self.paths.append(path)


class FakeScale:
    def __init__(self, variable, command):
        self.variable = variable
        self.command = command
        self.handlers = {}
        self.disabled = False

    def winfo_width(self):
        return 400

    def winfo_height(self):
        return 26

    def instate(self, states):
        return self.disabled and "disabled" in states

    def identify(self, _x, _y):
        return "Horizontal.Scale.track"

    def set(self, value):
        self.variable.set(value)
        self.command(value)

    def bind(self, sequence, handler, add=None):
        self.handlers[sequence] = handler


def rms(path: Path) -> float:
    with wave.open(str(path), "rb") as recording:
        samples = array("h", recording.readframes(recording.getnframes()))
    return math.sqrt(sum(value * value for value in samples) / len(samples))


class AudioAuditionVolumeTests(unittest.TestCase):
    def test_both_volume_tracks_seek_on_click_and_keep_dragging(self):
        app = MiniLogApp.__new__(MiniLogApp)
        app.project = Project(cuts=[Cut(source_path="picture.png")])
        app.selected_index = 0
        app._suspend_dirty = False
        app._suspend_cut_audio = False
        app.bgm_volume_var = FakeVar(60)
        app.bgm_volume_label_var = FakeVar("60%")
        app.cut_audio_volume_var = FakeVar(60)
        app.cut_audio_volume_label_var = FakeVar("60%")
        app._mark_preview_stale = Mock()

        for variable, label, value, callback in (
            (app.bgm_volume_var, app.bgm_volume_label_var, lambda: app.project.bgm_volume,
             app._on_bgm_volume_changed),
            (app.cut_audio_volume_var, app.cut_audio_volume_label_var,
             lambda: app.project.cuts[0].audio_volume, app._on_cut_audio_volume_changed),
        ):
            scale = FakeScale(variable, callback)
            app._enable_volume_track_click(scale)
            for percent in (0, 25, 50, 75, 100):
                x = 8 + round(percent * 384 / 100)
                event = SimpleNamespace(x=x, y=13)
                self.assertEqual(scale.handlers["<Button-1>"](event), "break")
                self.assertEqual(label.get(), f"{percent}%")
                self.assertEqual(value(), percent / 100)
                scale.handlers["<ButtonRelease-1>"](event)
            scale.handlers["<Button-1>"](SimpleNamespace(x=104, y=13))
            scale.handlers["<B1-Motion>"](SimpleNamespace(x=296, y=13))
            self.assertEqual(value(), 0.75)
            scale.handlers["<ButtonRelease-1>"](SimpleNamespace(x=296, y=13))
            scale.disabled = True
            self.assertIsNone(scale.handlers["<Button-1>"](SimpleNamespace(x=8, y=13)))
            self.assertEqual(value(), 0.75)

    def test_bgm_and_cut_wav_levels_are_monotonic_and_zero_is_silent(self):
        with tempfile.TemporaryDirectory(prefix="mini-log-volume-test-") as folder:
            sources = {}
            ffmpeg = find_ffmpeg()
            for kind, extension in (("bgm", "mp3"), ("cut", "wav")):
                source = Path(folder) / f"source.{extension}"
                subprocess.run(
                    [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                     "-i", "sine=frequency=440:duration=1", "-c:a", "libmp3lame" if extension == "mp3" else "pcm_s16le",
                     str(source)], check=True,
                )
                sources[kind] = source

            sound = FakeSound()
            with patch.object(audio_module, "winsound", sound):
                audition = AudioAudition(FakeRoot(), lambda _kind: None)
                try:
                    for kind, source in sources.items():
                        levels = []
                        played_paths = []
                        for percent in (0, 30, 60, 100):
                            audition.play(kind, str(source), percent / 100)
                            deadline = time.monotonic() + 10
                            while audition.results.empty() and time.monotonic() < deadline:
                                time.sleep(0.01)
                            self.assertFalse(audition.results.empty())
                            audition._poll()
                            self.assertIsNotNone(audition.playing_path)
                            self.assertEqual(sound.paths[-1], str(audition.playing_path))
                            levels.append(rms(audition.playing_path))
                            played_paths.append(str(audition.playing_path))
                        self.assertEqual(len(set(played_paths)), 4)
                        self.assertLess(levels[0], 1)
                        self.assertTrue(all(a < b for a, b in zip(levels, levels[1:])), levels)
                        self.assertAlmostEqual(levels[1] / levels[3], 0.3, delta=0.03)
                        self.assertAlmostEqual(levels[2] / levels[3], 0.6, delta=0.03)
                finally:
                    audition.close()

    def test_both_audition_buttons_use_current_slider_value(self):
        with tempfile.TemporaryDirectory(prefix="mini-log-volume-ui-") as folder:
            source = Path(folder) / "sound.wav"
            source.touch()
            app = MiniLogApp.__new__(MiniLogApp)
            app.project = Project(cuts=[Cut(source_path="picture.png", audio_path=str(source))], bgm_path=str(source))
            app.selected_index = 0
            app._suspend_dirty = False
            app._suspend_cut_audio = False
            app.bgm_volume_var = FakeVar()
            app.bgm_volume_label_var = FakeVar()
            app.cut_audio_volume_var = FakeVar()
            app.cut_audio_volume_label_var = FakeVar()
            app.audio_audition = Mock(kind=None)
            app.player = SimpleNamespace(playing=False)
            app._mark_preview_stale = Mock()

            for percent in (100, 30, 0):
                app.bgm_volume_var.set(percent)
                app.cut_audio_volume_var.set(percent)
                app.project.bgm_volume = 0.6  # deliberately stale model
                app.project.cuts[0].audio_volume = 0.6
                app.toggle_bgm_audition()
                app.audio_audition.play.assert_called_with("bgm", str(source), percent / 100)
                app.toggle_cut_audio_audition()
                app.audio_audition.play.assert_called_with(
                    "cut", str(source), percent / 100, owner_id=app.project.cuts[0].id,
                )
                self.assertEqual(app.project.bgm_volume, percent / 100)
                self.assertEqual(app.project.cuts[0].audio_volume, percent / 100)


if __name__ == "__main__":
    unittest.main()
