"""Tk acceptance for compact preview layout and Cut multi-selection/deletion."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tkinter import END
from tkinterdnd2 import TkinterDnD

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main_window import MiniLogApp
from app.models import Cut, Project
from tests.phase1b_acceptance import make_inputs


ARTIFACTS = ROOT / "output" / "cut-multi-select-acceptance"
CONTROL_MASK = 0x0004


def card_click(app: MiniLogApp, index: int, control: bool = False) -> None:
    card = app.card_widgets[index]
    y = card.winfo_rooty() + card.winfo_height() // 2
    event = SimpleNamespace(y_root=y, state=CONTROL_MASK if control else 0)
    app._begin_card_drag(event, index)
    app._end_card_drag(event)


def main() -> None:
    paths = make_inputs()
    cuts = [
        Cut(str(paths[index % len(paths)]), duration=1.5, caption_text=f"Caption {index + 1}")
        for index in range(8)
    ]
    root = TkinterDnD.Tk()
    root.withdraw()
    app = MiniLogApp(root)
    app.project = Project(cuts=cuts)
    app.selected_index = 0
    app.selected_cut_ids.clear()
    app._refresh_all()
    root.deiconify()
    root.update()

    assert not hasattr(app, "notebook_decoration")

    card_click(app, 1)
    assert app.selected_cut_ids == {app.project.cuts[1].id}
    assert app.selected_index == 1
    assert app.cut_caption_text.get("1.0", END).rstrip("\n") == "Caption 2"

    card_click(app, 4, control=True)
    card_click(app, 6, control=True)
    selected_ids = {app.project.cuts[index].id for index in (1, 4, 6)}
    assert app.selected_cut_ids == selected_ids
    assert app.selected_index == 6
    assert app.cut_caption_text.get("1.0", END).rstrip("\n") == "Caption 7"
    assert str(app.card_selection_bars[6].cget("style")) == "SelectionBar.TFrame"
    assert str(app.card_selection_bars[1].cget("style")) == "SelectionBarOff.TFrame"

    original_texts = {cut.id: cut.caption_text for cut in app.project.cuts}
    app.preview_path.touch()
    app.preview_generated_signature = "before-caption-style"
    app.cut_caption_font_var.set("明朝")
    app._on_cut_caption_style_edited("caption_font")
    app.cut_caption_size_var.set("小")
    app._on_cut_caption_style_edited("caption_size")
    app.cut_caption_position_var.set("上")
    app._on_cut_caption_style_edited("caption_position")
    app.cut_caption_motion_var.set("下から表示")
    app._on_cut_caption_style_edited("caption_motion")
    assert app.status_var.get() == "3カットのCaption 表示を変更しました"
    assert app.preview_photo is not None
    for index in (1, 4, 6):
        cut = app.project.cuts[index]
        assert (cut.caption_font, cut.caption_size) == ("mincho", "small")
        assert (cut.caption_position, cut.caption_motion) == ("top", "slide_up")
    for index in (0, 2, 3, 5, 7):
        cut = app.project.cuts[index]
        assert (cut.caption_font, cut.caption_size) == ("gothic", "medium")
        assert (cut.caption_position, cut.caption_motion) == ("bottom", "fade")
    assert app.preview_state_var.get() == "このプレビューは現在の編集内容と異なります"

    app.cut_caption_text.delete("1.0", END)
    app.cut_caption_text.insert("1.0", "Active Cutだけの本文")
    app._on_cut_caption_text_edited()
    for index, cut in enumerate(app.project.cuts):
        expected = "Active Cutだけの本文" if index == 6 else original_texts[cut.id]
        assert cut.caption_text == expected

    with tempfile.TemporaryDirectory(prefix="minilog-multi-caption-") as folder:
        project_path = Path(folder) / "multi-caption.minilog"
        app.project.save(project_path)
        restored = Project.load(project_path)
    for index in (1, 4, 6):
        restored_cut = restored.cuts[index]
        assert (restored_cut.caption_font, restored_cut.caption_size) == ("mincho", "small")
        assert (restored_cut.caption_position, restored_cut.caption_motion) == ("top", "slide_up")
    assert restored.cuts[6].caption_text == "Active Cutだけの本文"
    assert restored.cuts[1].caption_text == "Caption 2"

    card_click(app, 4, control=True)
    assert app.selected_cut_ids == {app.project.cuts[1].id, app.project.cuts[6].id}
    assert app.selected_index == 6

    card_click(app, 3)
    assert app.selected_cut_ids == {app.project.cuts[3].id}
    assert app.selected_index == 3

    app.select_cut(1)
    app.select_cut(4, additive=True)
    app.select_cut(6, additive=True)
    old_next_id = app.project.cuts[7].id
    old_duration = app.project.total_duration()
    app.preview_generated_signature = "before-delete"
    with patch("app.main_window.messagebox.askokcancel", return_value=True) as confirm:
        app.remove_cut(6)
    confirm.assert_called_once()
    assert confirm.call_args.args[1] == "3カットを削除しますか？"
    assert len(app.project.cuts) == 5
    assert [cut.order for cut in app.project.cuts] == list(range(5))
    assert app.project.total_duration() == old_duration - 4.5
    assert app.project.cuts[app.selected_index].id == old_next_id
    assert app.selected_cut_ids == {old_next_id}
    assert app.preview_state_var.get() == "このプレビューは現在の編集内容と異なります"

    app.select_cut(0)
    app.select_cut(2, additive=True)
    count_before_key = len(app.project.cuts)
    with patch.object(type(root), "focus_get", return_value=app.cut_caption_text):
        assert app._on_delete_key() is None
    assert len(app.project.cuts) == count_before_key

    with (
        patch.object(type(root), "focus_get", return_value=root),
        patch("app.main_window.messagebox.askokcancel", return_value=True),
    ):
        assert app._on_delete_key() == "break"
    assert len(app.project.cuts) == count_before_key - 2

    root.update()
    original_last_id = app.project.cuts[-1].id
    source_card = app.card_widgets[-1]
    target_card = app.card_widgets[0]
    press_y = source_card.winfo_rooty() + source_card.winfo_height() // 2
    target_y = target_card.winfo_rooty() + 1
    app._begin_card_drag(SimpleNamespace(y_root=press_y, state=0), len(app.project.cuts) - 1)
    app._continue_card_drag(SimpleNamespace(y_root=target_y))
    app._end_card_drag(SimpleNamespace(y_root=target_y))
    assert app.project.cuts[0].id == original_last_id

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    result = {
        "notebook_decoration_removed": not hasattr(app, "notebook_decoration"),
        "multi_select_count": 3,
        "active_caption": "Caption 7",
        "caption_style_batch_applied": ["font", "size", "position", "motion"],
        "caption_text_active_only": True,
        "project_roundtrip": True,
        "bulk_delete_confirmation": "3カットを削除しますか？",
        "delete_key_ignores_text_input": True,
        "drag_reorder_preserved": True,
    }
    (ARTIFACTS / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    app._on_close()
    print("PASS", json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
