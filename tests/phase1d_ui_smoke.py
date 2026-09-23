"""Tk acceptance for still motion copy, selection styling, card drag, and caption controls."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tkinter import END
from tkinterdnd2 import TkinterDnD

from app.main_window import MiniLogApp, NO_MOTION_LABEL, next_available_mp4_name
from app.models import Cut, Project
from tests.phase1b_acceptance import make_inputs
from tests.phase1d_acceptance import ARTIFACTS


def main() -> None:
    def descendant_texts(widget) -> set[str]:
        texts: set[str] = set()
        for child in widget.winfo_children():
            if "text" in child.keys():
                texts.add(str(child.cget("text")))
            texts.update(descendant_texts(child))
        return texts

    paths = make_inputs()
    project = Project(
        cuts=[
            Cut(str(paths[0]), type="Still"),
            Cut(str(paths[1]), type="Motion", motion_type="Zoom Out"),
            Cut(str(paths[2]), type="Still"),
            Cut(str(paths[3]), type="Motion", motion_type="Pan Right"),
            Cut(str(paths[4]), type="Still"),
            Cut(str(paths[5]), type="Motion", motion_type="Zoom In"),
        ]
    )
    root = TkinterDnD.Tk()
    root.withdraw()
    app = MiniLogApp(root)
    app.project = project
    app.selected_index = 0
    app._refresh_all()
    root.deiconify()
    root.update()

    assert app.card_motion_combos[0].get() == NO_MOTION_LABEL
    still_motion_display = app.card_motion_combos[0].get()
    assert "disabled" in app.card_motion_combos[0].state()
    assert app.card_motion_combos[1].get() == "ズームアウト"
    assert "disabled" not in app.card_motion_combos[1].state()
    assert str(app.card_selection_bars[0].cget("style")) == "SelectionBar.TFrame"
    assert str(app.card_selection_bars[1].cget("style")) == "SelectionBarOff.TFrame"
    assert int(app.card_body_widgets[0].cget("borderwidth")) == 0
    assert int(app.card_body_widgets[0].cget("highlightthickness")) == 0
    card_texts = descendant_texts(app.card_widgets[0])
    assert "↑" not in card_texts
    assert "↓" not in card_texts
    assert "カードをドラッグ" not in card_texts
    assert app.card_widgets[0].bind("<B1-Motion>")

    original_ids = [cut.id for cut in app.project.cuts]
    source_card = app.card_widgets[5]
    target_card = app.card_widgets[0]
    press_y = source_card.winfo_rooty() + source_card.winfo_height() // 2
    target_y = target_card.winfo_rooty() + 1
    app._begin_card_drag(SimpleNamespace(y_root=press_y), 5)
    app._continue_card_drag(SimpleNamespace(y_root=target_y))
    assert app.drag_active
    assert str(app.card_widgets[0].cget("style")) == "DropTargetCard.TFrame"
    app._end_card_drag(SimpleNamespace(y_root=target_y))
    assert app.project.cuts[0].id == original_ids[5]

    order_after_drag = [cut.id for cut in app.project.cuts]
    card = app.card_widgets[2]
    click_y = card.winfo_rooty() + card.winfo_height() // 2
    app._begin_card_drag(SimpleNamespace(y_root=click_y), 2)
    app._end_card_drag(SimpleNamespace(y_root=click_y))
    assert [cut.id for cut in app.project.cuts] == order_after_drag
    assert app.selected_index == 2

    app.cut_caption_text.delete("1.0", END)
    app.cut_caption_text.insert("1.0", "PM1:00\nまた出かけます、紫いいでしょ。")
    app.cut_caption_font_var.set("明朝")
    app.cut_caption_size_var.set("小")
    app._on_cut_caption_edited()
    selected = app.project.cuts[2]
    assert selected.caption_font == "mincho"
    assert selected.caption_size == "small"
    assert app.preview_photo is not None

    with tempfile.TemporaryDirectory(prefix="minilog-phase1d-") as temp_dir:
        export_dir = Path(temp_dir)
        for name in ("mini-log.mp4", "mini-log-001.mp4"):
            (export_dir / name).touch()
        next_export_name = next_available_mp4_name(export_dir)
    assert next_export_name == "mini-log-002.mp4"

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    result = {
        "still_motion_display": still_motion_display,
        "selected_bar_style": app.card_selection_bars[2].cget("style"),
        "full_card_drag_binding": bool(app.card_widgets[0].bind("<B1-Motion>")),
        "reordered_first_id": app.project.cuts[0].id,
        "caption_font": selected.caption_font,
        "caption_size": selected.caption_size,
        "next_export_name": next_export_name,
    }
    (ARTIFACTS / "ui-results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    app._on_close()
    print("PASS", json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
