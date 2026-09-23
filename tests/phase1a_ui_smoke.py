"""Tk smoke check for async preview state and playback.

Run this in a normal desktop Python session. The Codex sandbox command used for
acceptance supplies local Tcl/tkDND copies because its process cannot read Tcl
resources outside the workspace.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tkinterdnd2 import TkinterDnD

from app.main_window import MiniLogApp
from app.models import Cut, Project
from tests.human_acceptance import make_inputs
from tests.phase1a_acceptance import ARTIFACTS, make_seventh_image


def pump(root, condition, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while condition() and time.monotonic() < deadline:
        root.update()
        time.sleep(0.005)


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    inputs = make_inputs() + [make_seventh_image()]
    project = Project(
        cuts=[
            Cut(str(inputs[0]), type="Motion", duration=3.0, motion_type="Zoom In"),
            Cut(str(inputs[1]), duration=1.5),
            Cut(str(inputs[2]), duration=1.5),
            Cut(str(inputs[3]), type="Motion", duration=3.0, motion_type="Pan Right"),
            Cut(str(inputs[4]), type="Motion", duration=3.0, motion_type="Zoom Out"),
            Cut(str(inputs[5]), duration=1.5),
            Cut(str(inputs[6]), type="Motion", duration=3.0, motion_type="Pan Left"),
        ],
        style="Film",
        caption_text="今日のまとめ。",
        caption_duration=1.8,
    )

    root = TkinterDnD.Tk()
    root.withdraw()
    app = MiniLogApp(root)
    app.project = project
    app.selected_index = 3
    app._refresh_all()
    root.update()
    assert not app.progress_box.winfo_manager()

    heartbeat = {"ticks": 0}

    def tick() -> None:
        heartbeat["ticks"] += 1
        if app.preview_generating:
            root.after(20, tick)

    app.start_preview()
    root.update()
    assert app.progress_box.winfo_manager() == "pack"
    assert app.progress_text_var.get() == "プレビュー作成中…"
    root.after(20, tick)
    pump(root, lambda: app.preview_generating, 15.0)
    assert not app.preview_generating
    assert not app.progress_box.winfo_manager()
    assert heartbeat["ticks"] > 10
    assert app.preview_path.is_file()
    assert app.preview_state_var.get() == "プレビューの準備ができました"
    assert app.total_duration_var.get() == "動画の長さ：18.3秒"

    app.play_preview(from_selected=True)
    playback_deadline = time.monotonic() + 0.7
    pump(root, lambda: time.monotonic() < playback_deadline, 1.0)
    assert app.player.playing
    assert app.preview_photo is not None
    assert app.preview_time_var.get().startswith("00:06"), app.preview_time_var.get()
    app.project.cuts[0].duration = 2.8
    app._mark_preview_stale()
    assert app.player.playing
    assert app.preview_state_var.get() == "このプレビューは現在の編集内容と異なります"
    app.stop_preview()
    assert not app.player.playing
    stale_state = app.preview_state_var.get()
    app.start_preview()
    root.update()
    assert app.progress_box.winfo_manager() == "pack"
    pump(root, lambda: app.preview_generating, 15.0)
    assert not app.preview_generating
    assert not app.progress_box.winfo_manager()
    assert app.preview_state_var.get() == "プレビューの準備ができました"
    assert app.preview_generated_signature == app._project_signature()
    result = {
        "heartbeat_ticks": heartbeat["ticks"],
        "stale_state": stale_state,
        "regenerated_state": app.preview_state_var.get(),
        "time": app.preview_time_var.get(),
    }
    temp_path = Path(app.preview_temp.name)
    app._on_close()
    assert not temp_path.exists()
    print(
        "PASS",
        result,
    )


if __name__ == "__main__":
    main()
