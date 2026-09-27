"""Exercise Phase 2B new-project and transition controls in Tk."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tkinterdnd2 import TkinterDnD

from app.main_window import MiniLogApp, TRANSITION_DURATION_LABELS, TRANSITION_LABELS
from app.models import Cut, Project


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="minilog-phase2b-ui-") as temporary:
        folder = Path(temporary)
        paths = []
        for index in range(3):
            path = folder / f"still-{index}.png"
            Image.new("RGB", (80, 140), (40 + index * 35, 125, 85)).save(path)
            paths.append(path)

        project = Project(
            cuts=[Cut(str(path), duration=1.0) for path in paths],
            theme="summer",
            caption_text="まとめ。",
            bgm_path=str(paths[0]),
        )
        root = TkinterDnD.Tk()
        root.withdraw()
        app = MiniLogApp(root)
        app.project = project
        app.selected_index = 0
        app.selected_cut_ids = {project.cuts[0].id}
        app._refresh_all()
        root.update()

        app.preview_path.touch()
        app.preview_generated_signature = app._project_signature()
        app.transition_type_var.set(TRANSITION_LABELS["crossfade"])
        app._on_transition_type_changed()
        app.transition_duration_var.set(TRANSITION_DURATION_LABELS[0.6])
        app._on_transition_duration_changed()
        assert project.cuts[0].transition_type == "crossfade"
        assert project.cuts[0].transition_duration == 0.6
        assert app.preview_state_var.get() == "このプレビューは現在の編集内容と異なります"
        assert "4.5" in app.total_duration_var.get()

        app.toggle_preview_visibility()
        assert not app.preview_visible
        with patch("app.main_window.messagebox.askyesno", return_value=False) as confirm:
            app.new_project()
        confirm.assert_called_once()
        assert len(app.project.cuts) == 3

        with patch("app.main_window.messagebox.askyesno", return_value=True):
            app.new_project()
        assert not app.project.cuts
        assert app.project.bgm_path is None
        assert app.project.caption_text == ""
        assert app.project.theme == "summer"
        assert app.project_path is None
        assert not app.preview_visible
        assert app.preview_state_var.get() == "プレビューはまだありません"
        assert "0.0" in app.total_duration_var.get()

        app.preview_temp.cleanup()
        root.destroy()

    print("Phase 2B UI smoke: PASS (transition controls, stale/duration, new-project cancel/reset, app preferences retained)")


if __name__ == "__main__":
    main()
