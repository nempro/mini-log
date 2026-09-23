"""Tk smoke check for per-cut caption editing and stale state."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tkinter import END
from tkinterdnd2 import TkinterDnD

from app.main_window import MiniLogApp
from app.models import Cut, Project
from tests.phase1b_acceptance import ARTIFACTS, make_inputs


def main() -> None:
    inputs = make_inputs()
    project = Project(
        cuts=[
            Cut(
                str(inputs[0]),
                caption_text="はじまり。",
                caption_position="bottom",
                caption_motion="fade",
            ),
            Cut(
                str(inputs[1]),
                caption_text="今日の一枚。",
                caption_position="center",
                caption_motion="fixed",
            ),
        ],
        style="Soft",
        caption_text="今日のまとめ。",
    )

    root = TkinterDnD.Tk()
    root.withdraw()
    app = MiniLogApp(root)
    app.project = project
    app.selected_index = 0
    app._refresh_all()
    root.deiconify()
    root.update()
    root.update_idletasks()

    assert app.cut_caption_text.get("1.0", END).rstrip("\n") == "はじまり。"
    assert app.cut_caption_position_var.get() == "下"
    assert app.cut_caption_motion_var.get() == "フェード"
    assert app.caption_text.get("1.0", END).rstrip("\n") == "今日のまとめ。"
    assert app.preview_photo is not None
    export_bottom = app.export_button.winfo_rooty() + app.export_button.winfo_height()
    window_bottom = root.winfo_rooty() + root.winfo_height()
    assert export_bottom <= window_bottom

    app.preview_path.write_bytes(b"stale marker")
    app.preview_generated_signature = app._project_signature()
    app.cut_caption_text.delete("1.0", END)
    app.cut_caption_text.insert("1.0", "一言を更新。")
    app.cut_caption_position_var.set("上")
    app.cut_caption_motion_var.set("下から表示")
    app._on_cut_caption_edited()
    assert project.cuts[0].caption_text == "一言を更新。"
    assert project.cuts[0].caption_position == "top"
    assert project.cuts[0].caption_motion == "slide_up"
    assert app.preview_state_var.get() == "このプレビューは現在の編集内容と異なります"

    app.select_cut(1)
    assert app.cut_caption_text.get("1.0", END).rstrip("\n") == "今日の一枚。"
    assert app.cut_caption_position_var.get() == "中央"
    assert app.cut_caption_motion_var.get() == "固定"
    assert app.caption_text.get("1.0", END).rstrip("\n") == "今日のまとめ。"

    app.select_cut(0)
    assert app.cut_caption_text.get("1.0", END).rstrip("\n") == "一言を更新。"
    result = {
        "cut_1": [project.cuts[0].caption_text, project.cuts[0].caption_position, project.cuts[0].caption_motion],
        "cut_2": [project.cuts[1].caption_text, project.cuts[1].caption_position, project.cuts[1].caption_motion],
        "end_caption": project.caption_text,
        "stale_state": app.preview_state_var.get(),
        "requested_window": root.geometry(),
        "export_visible": export_bottom <= window_bottom,
    }
    (ARTIFACTS / "ui-results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    app._on_close()
    print("PASS", json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
