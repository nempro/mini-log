"""Tk smoke check for BGM controls, stale state, and synchronized preview audio."""

from __future__ import annotations

import json
import shutil
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tkinterdnd2 import TkinterDnD

import app.preview_player as preview_player_module
from app.main_window import MiniLogApp
from app.models import Project
from tests.phase1c_acceptance import ARTIFACTS


def pump(root, condition, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while condition() and time.monotonic() < deadline:
        root.update()
        time.sleep(0.005)


class DropEvent:
    def __init__(self, path: Path) -> None:
        self.data = "{" + str(path) + "}"
        self.action = "copy"


def main() -> None:
    project = Project.load(ARTIFACTS / "phase1c.minilog")
    preview = ARTIFACTS / "preview-with-bgm.mp4"
    short_bgm = ARTIFACTS / "short-bgm-5s.mp3"

    root = TkinterDnD.Tk()
    root.withdraw()
    app = MiniLogApp(root)
    app.project = project
    app.selected_index = 2
    app._refresh_all()
    root.deiconify()
    root.update()

    assert app.bgm_name_var.get() == Path(project.bgm_path).name
    assert round(app.bgm_volume_var.get()) == 70
    cut_count = len(app.project.cuts)
    app._on_files_dropped(DropEvent(short_bgm))
    assert "BGM欄" in app.status_var.get()
    assert len(app.project.cuts) == cut_count

    app._on_bgm_dropped(DropEvent(short_bgm))
    assert Path(app.project.bgm_path).name == short_bgm.name
    assert app.bgm_name_var.get() == short_bgm.name

    shutil.copyfile(preview, app.preview_path)
    app.preview_generated_signature = app._project_signature()
    app.bgm_volume_var.set(55)
    app._on_bgm_volume_changed(55)
    assert abs(app.project.bgm_volume - 0.55) < 0.001
    assert app.bgm_volume_label_var.get() == "55%"
    assert app.preview_state_var.get() == "このプレビューは現在の編集内容と異なります"

    app.project.bgm_path = str(ARTIFACTS / "missing.mp3")
    app._refresh_bgm_display()
    assert "BGMファイルが見つかりません" in app.bgm_name_var.get()
    app.project.bgm_path = str((ARTIFACTS / "long-bgm-20s.mp3").resolve())
    app.project.bgm_volume = 0.7
    app._refresh_all()

    shutil.copyfile(preview, app.preview_path)
    app.preview_project_snapshot = Project.from_dict(app.project.to_dict())
    app.preview_generated_signature = app._project_signature()
    calls: list[tuple[object, int]] = []
    original_play_sound = preview_player_module.winsound.PlaySound
    preview_player_module.winsound.PlaySound = lambda sound, flags: calls.append((sound, flags))
    try:
        app.play_preview(from_selected=True)
        pump(root, lambda: not app.player.audio_started, 2.0)
        assert app.player.playing
        assert app.player.audio_ready
        assert app.player.audio_started
        assert abs(app.player.start_offset - 4.5) < 0.001
        assert calls and calls[0][0] == str(app.player.audio_path)
        with wave.open(str(app.player.audio_path), "rb") as audio:
            audio_duration = audio.getnframes() / audio.getframerate()
            assert abs(audio_duration - 11.5) < 0.1
            assert audio.getframerate() == 48000
            assert audio.getnchannels() == 2
        app.stop_preview()
        assert calls[-1][0] is None
    finally:
        preview_player_module.winsound.PlaySound = original_play_sound

    app.right_canvas.yview_moveto(1.0)
    root.update()
    export_bottom = app.export_button.winfo_rooty() + app.export_button.winfo_height()
    window_bottom = root.winfo_rooty() + root.winfo_height()
    assert export_bottom <= window_bottom

    result = {
        "bgm_name": Path(app.project.bgm_path).name,
        "volume": app.project.bgm_volume,
        "stale": "このプレビューは現在の編集内容と異なります",
        "audio_start_offset": app.player.start_offset,
        "audio_duration_from_cut": round(audio_duration, 3),
        "audio_format": "PCM 48kHz Stereo preview playback",
        "export_visible_after_scroll": export_bottom <= window_bottom,
    }
    (ARTIFACTS / "ui-results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    app._on_close()
    print("PASS", json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
