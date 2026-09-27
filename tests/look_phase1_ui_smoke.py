"""Exercise LOOK controls, still Preview, and missing-LUT recovery in Tk."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageTk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tkinterdnd2 import TkinterDnD

from app.main_window import MiniLogApp
from app.look_engine import PRESET_LOOKS
from app.models import Project
from look_phase1_acceptance import write_invert_cube


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="minilog-look-ui-") as temporary:
        folder = Path(temporary)
        image = folder / "still.png"
        Image.new("RGB", (180, 320), (70, 125, 180)).save(image)
        lut = folder / "Invert.cube"
        write_invert_cube(lut)

        root = TkinterDnD.Tk()
        root.withdraw()
        app = MiniLogApp(root)
        app.project.add_images([str(image)])
        app.selected_index = 0
        app.selected_cut_ids = {app.project.cuts[0].id}
        app._refresh_all()
        root.deiconify()
        root.update()
        look_widgets = [app.look_mode_combo, app.look_strength_scale]
        look_widgets.extend(
            child for child in app.look_mode_combo.master.winfo_children()
            if child.winfo_class() == "TLabel" and child.cget("text") in {"LOOK", "強度"}
        )
        assert len(look_widgets) == 4
        assert not app.look_lut_button.winfo_ismapped()
        for widget in look_widgets:
            assert widget.winfo_ismapped() and widget.winfo_manager()
            assert str(widget).startswith(str(app.whole_scope))
        app.toggle_preview_visibility()
        root.update()
        assert all(widget.winfo_ismapped() for widget in look_widgets)
        app.toggle_preview_visibility()
        root.update()
        original = ImageTk.getimage(app.preview_photo).convert("RGB").getpixel((10, 10))
        assert app.look_mode_var.get() == "オリジナル"

        app.preview_path.touch()
        app.preview_generated_signature = app._project_signature()
        preset_pixels = set()
        for preset_id, label, _description in PRESET_LOOKS:
            assert label in app.look_mode_combo.cget("values")
            app.look_mode_var.set(label)
            app._on_look_mode_changed()
            assert (app.project.look_type, app.project.look_lut_path) == (preset_id, None)
            assert not app.look_lut_button.winfo_ismapped()
            preset_pixels.add(ImageTk.getimage(app.preview_photo).convert("RGB").getpixel((10, 10)))
        assert app.preview_state_var.get() == "このプレビューは現在の編集内容と異なります"
        assert len(preset_pixels) == len(PRESET_LOOKS)
        app.preview_generated_signature = app._project_signature()
        app.look_strength_var.set(50)
        app._on_look_strength_changed("50")
        assert app.project.look_strength == 0.5
        assert app.preview_state_var.get() == "このプレビューは現在の編集内容と異なります"
        app.look_mode_var.set("オリジナル")
        app._on_look_mode_changed()
        assert ImageTk.getimage(app.preview_photo).convert("RGB").getpixel((10, 10)) == original

        app.preview_path.touch()
        app.preview_generated_signature = app._project_signature()
        with patch("app.main_window.filedialog.askopenfilename", return_value=str(lut)):
            app.choose_look_lut()
        root.update()
        assert app.look_mode_var.get() == "カスタムLUT"
        assert app.look_lut_button.winfo_ismapped()
        assert "Invert.cube" in app.look_name_var.get()
        assert app.project.look_type == "custom_lut"
        assert app.preview_state_var.get() == "このプレビューは現在の編集内容と異なります"
        full = ImageTk.getimage(app.preview_photo).convert("RGB").getpixel((10, 10))
        assert max(abs(a-b) for a, b in zip(original, full)) > 30

        app.look_strength_var.set(50)
        app._on_look_strength_changed("50")
        assert app.project.look_strength == 0.5
        middle = ImageTk.getimage(app.preview_photo).convert("RGB").getpixel((10, 10))
        assert all(min(a, b) <= value <= max(a, b) for a, value, b in zip(original, middle, full))

        app.look_mode_var.set("オリジナル")
        app._on_look_mode_changed()
        assert (app.project.look_type, app.project.look_lut_path, app.project.look_strength) == ("original", None, 1.0)
        assert ImageTk.getimage(app.preview_photo).convert("RGB").getpixel((10, 10)) == original
        app.look_mode_var.set("カスタムLUT")
        app._on_look_mode_changed()
        assert app.project.look_strength == 0.5

        app.project.theme = "summer"
        app._refresh_all()
        root.update()
        assert app.project.look_type == "custom_lut"
        assert all(widget.winfo_ismapped() for widget in look_widgets)
        assert app.look_lut_button.winfo_ismapped()
        saved = folder / "look.minilog"
        app.project.save(saved)
        restored = Project.load(saved)
        assert (restored.look_type, restored.look_lut_path, restored.look_strength) == ("custom_lut", str(lut), 0.5)

        lut.rename(folder / "moved.cube")
        with patch("app.main_window.filedialog.askopenfilename", return_value=str(saved)):
            app.open_project()
        assert app.look_mode_var.get() == "オリジナル"
        assert app.project.look_lut_path is None
        assert app.project.theme == "summer"
        assert app.look_name_var.get() == "LUTファイルが見つかりません"

        app.preview_temp.cleanup()
        root.destroy()
    print("LOOK Phase 1 UI smoke: PASS (load, strength, Original toggle, still Preview, theme, save/load, missing LUT)")


if __name__ == "__main__":
    main()
