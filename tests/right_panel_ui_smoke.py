"""Windows UI check for right-pane scope and Cut Caption styles."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PIL import Image
from tkinterdnd2 import TkinterDnD

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main_window import CAPTION_STYLE_LABELS, MiniLogApp, TRANSITION_LABELS
from app.models import Cut, Project


def belongs_to(widget, ancestor) -> bool:
    current = widget
    while current is not None:
        if current is ancestor:
            return True
        current = current.master
    return False


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="mini-log-right-ui-") as temporary:
        folder = Path(temporary)
        paths = [folder / f"image-{index}.png" for index in range(2)]
        for path in paths:
            Image.new("RGB", (360, 640), "#95b7a4").save(path)
        project = Project(cuts=[Cut(str(path), caption_text="今日の記録。") for path in paths])
        root = TkinterDnD.Tk()
        root.withdraw()
        app = MiniLogApp(root)
        app.project = project
        app.selected_index = 0
        app.selected_cut_ids = {project.cuts[0].id}
        app._refresh_all()
        root.deiconify()
        root.update()

        assert app.preview_heading.winfo_rooty() < app.cut_scope.winfo_rooty() < app.whole_scope.winfo_rooty()
        assert not belongs_to(app.export_button, app.cut_scope)
        assert not belongs_to(app.export_button, app.whole_scope)
        assert app.export_button.master.master is app.whole_scope.master
        assert app.whole_scope.winfo_rooty() + app.whole_scope.winfo_height() < app.export_button.winfo_rooty()
        assert app.cut_scope.cget("text") == "このカット"
        assert app.whole_scope.cget("text") == "動画全体"
        for widget in (app.cut_caption_text, app.cut_audio_name_label, app.transition_type_combo):
            assert belongs_to(widget, app.cut_scope)
        for widget in (app.look_mode_combo, app.bgm_box, app.caption_text):
            assert belongs_to(widget, app.whole_scope)

        assert app.transition_type_var.get() == "なし"
        assert not app.transition_duration_combo.winfo_manager()
        app.transition_type_var.set(TRANSITION_LABELS["fade"])
        app._on_transition_type_changed()
        assert app.transition_duration_combo.winfo_manager()
        app.transition_type_var.set(TRANSITION_LABELS["cut"])
        app._on_transition_type_changed()
        assert not app.transition_duration_combo.winfo_manager()
        assert project.cuts[0].transition_type == "cut"

        app.preview_path.touch()
        app.preview_generated_signature = app._project_signature()
        pixels = []
        for style, label in CAPTION_STYLE_LABELS.items():
            app.cut_caption_style_var.set(label)
            app._on_cut_caption_style_edited("caption_style")
            root.update()
            assert project.cuts[0].caption_style == style
            assert app.preview_photo is not None
            pixels.append(app.preview_photo.width() * app.preview_photo.height())
        assert len(pixels) == 4
        assert app.preview_state_var.get() == "このプレビューは現在の編集内容と異なります"
        saved = folder / "style.minilog"
        project.save(saved)
        assert Project.load(saved).cuts[0].caption_style == "shadow"
        app.select_cut(1)
        assert app.cut_caption_style_var.get() == "帯"
        app.select_cut(0)
        assert app.cut_caption_style_var.get() == "影"
        app._on_close()
    print("Right pane UI smoke: PASS (scope order, transition visibility, style/stale/save)")


if __name__ == "__main__":
    main()
