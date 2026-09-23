"""Tk acceptance for Phase 1F Duration controls and per-Cut Audio UI."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tkinterdnd2 import TkinterDnD

import app.main_window as main_window_module
from app.main_window import MiniLogApp
from app.models import Cut, Project
from tests.phase1b_acceptance import make_inputs
from tests.phase1f_acceptance import ARTIFACTS


def commit_entry(root, entry, value: str) -> None:
    entry.focus_force()
    root.update()
    entry.delete(0, "end")
    entry.insert(0, value)
    entry.event_generate("<Return>")
    root.update()


def main() -> None:
    paths = make_inputs()
    short_audio = ARTIFACTS / "short-0.4s.wav"
    long_audio = ARTIFACTS / "long-3s.wav"
    assert short_audio.is_file() and long_audio.is_file()

    root = TkinterDnD.Tk()
    root.withdraw()
    app = MiniLogApp(root)
    app.project = Project(cuts=[Cut(str(path), duration=1.5) for path in paths[:3]])
    app.selected_index = 0
    app._refresh_all()
    root.deiconify()
    root.update()

    assert not app.progress_box.winfo_ismapped()
    assert app.project.cuts[0].audio_volume == 0.6
    assert app.project.bgm_volume == 0.6
    assert round(app.bgm_volume_var.get()) == 60
    assert app.cut_audio_timing_label.cget("text") == "カット開始と同時に再生します"
    app._show_progress("プレビュー作成中…")
    root.update()
    assert app.progress_box.winfo_ismapped()
    assert app.progress_text_var.get() == "プレビュー作成中…"
    app._hide_progress()
    root.update()
    assert not app.progress_box.winfo_ismapped()

    app.preview_path.touch()
    app.preview_generated_signature = app._project_signature()
    duration_before = app.project.total_duration()
    app.card_duration_plus_buttons[0].invoke()
    root.update()
    assert app.project.cuts[0].duration == 1.6
    assert app.project.total_duration() == duration_before + 0.1
    assert app.preview_state_var.get() == "このプレビューは現在の編集内容と異なります"
    app.card_duration_minus_buttons[0].invoke()
    root.update()
    assert app.project.cuts[0].duration == 1.5

    commit_entry(root, app.card_duration_entries[0], "2.7")
    assert app.project.cuts[0].duration == 2.7
    commit_entry(root, app.card_duration_entries[0], "0")
    assert app.project.cuts[0].duration == 0.5
    assert app.card_duration_entries[0].get() == "0.5"
    commit_entry(root, app.card_duration_entries[0], "50")
    assert app.project.cuts[0].duration == 30.0
    assert app.card_duration_entries[0].get() == "30.0"
    assert app.card_duration_entries[0].cget("cursor") != "fleur"
    assert app.card_duration_minus_buttons[0].cget("cursor") != "fleur"
    assert app.card_duration_plus_buttons[0].cget("cursor") != "fleur"
    assert not app.card_duration_entries[0].bind("<B1-Motion>")
    assert not app.card_duration_minus_buttons[0].bind("<B1-Motion>")
    assert not app.card_duration_plus_buttons[0].bind("<B1-Motion>")

    app.select_cut(1, additive=True)
    first_duration = app.project.cuts[0].duration
    app.card_duration_plus_buttons[1].invoke()
    root.update()
    assert app.project.cuts[1].duration == 1.6
    assert app.project.cuts[0].duration == first_duration

    app._set_cut_audio_path(short_audio)
    assert Path(app.project.cuts[1].audio_path) == short_audio.resolve()
    assert app.cut_audio_name_var.get() == short_audio.name
    assert app.cut_audio_select_button.cget("text") == "変更"
    assert "disabled" not in app.cut_audio_volume_scale.state()
    app.cut_audio_volume_var.set(70)
    app._on_cut_audio_volume_changed(70)
    assert app.project.cuts[1].audio_volume == 0.7
    assert app.cut_audio_volume_label_var.get() == "70%"

    app.select_cut(2)
    app._set_cut_audio_path(long_audio)
    app.cut_audio_volume_var.set(50)
    app._on_cut_audio_volume_changed(50)
    assert Path(app.project.cuts[2].audio_path) == long_audio.resolve()
    assert app.project.cuts[2].audio_volume == 0.5
    assert app.project.cuts[0].audio_path is None

    with tempfile.TemporaryDirectory(prefix="minilog-phase1f-ui-") as folder:
        path = Path(folder) / "phase1f-ui.minilog"
        app.project.save(path)
        restored = Project.load(path)
    assert Path(restored.cuts[1].audio_path) == short_audio.resolve()
    assert restored.cuts[1].audio_volume == 0.7
    assert Path(restored.cuts[2].audio_path) == long_audio.resolve()
    assert restored.cuts[2].audio_volume == 0.5

    app.project.cuts[2].audio_path = str(ARTIFACTS / "missing.wav")
    app._refresh_cut_audio_display()
    assert "カット音声ファイルが見つかりません" in app.cut_audio_name_var.get()
    app.remove_cut_audio()
    assert app.project.cuts[2].audio_path is None
    assert app.cut_audio_name_var.get() == "未設定"

    with tempfile.TemporaryDirectory(prefix="minilog-progress-ui-") as folder:
        export_path = Path(folder) / "progress-check.mp4"
        release_export = threading.Event()
        original_export_project = main_window_module.export_project
        original_save_dialog = main_window_module.filedialog.asksaveasfilename
        original_showinfo = main_window_module.messagebox.showinfo

        def fake_export(project, output_path, progress, settings=None):
            progress("テスト書き出し中", 0.5)
            release_export.wait(timeout=2.0)
            Path(output_path).touch()
            return Path(output_path)

        try:
            main_window_module.export_project = fake_export
            main_window_module.filedialog.asksaveasfilename = lambda **_kwargs: str(export_path)
            main_window_module.messagebox.showinfo = lambda *_args, **_kwargs: None
            app.start_export()
            assert app.progress_box.winfo_manager() == "pack"
            assert app.progress_text_var.get() == "書き出し中…"
            release_export.set()
            deadline = time.monotonic() + 3.0
            while app.exporting and time.monotonic() < deadline:
                root.update()
                time.sleep(0.01)
            assert not app.exporting
            assert not app.progress_box.winfo_manager()
        finally:
            main_window_module.export_project = original_export_project
            main_window_module.filedialog.asksaveasfilename = original_save_dialog
            main_window_module.messagebox.showinfo = original_showinfo

    app.right_canvas.yview_moveto(1.0)
    root.update()
    export_bottom = app.export_button.winfo_rooty() + app.export_button.winfo_height()
    window_bottom = root.winfo_rooty() + root.winfo_height()
    assert export_bottom <= window_bottom

    result = {
        "duration_buttons": "0.1 sec",
        "duration_direct_input": 2.7,
        "duration_bounds": [0.5, 30.0],
        "duration_controls_exclude_drag": True,
        "duration_active_cut_only": True,
        "cut_audio_formats": ["wav", "mp3", "m4a", "aac"],
        "cut_audio_volume": [0.7, 0.5],
        "new_cut_audio_default": 0.6,
        "new_bgm_default": 0.6,
        "cut_audio_timing_help": app.cut_audio_timing_label.cget("text"),
        "idle_progress_hidden": not app.progress_box.winfo_ismapped(),
        "export_progress_lifecycle": True,
        "missing_audio_safe": True,
        "project_roundtrip": True,
        "export_visible_after_scroll": True,
    }
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "ui-results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    app._on_close()
    print("PASS", json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
