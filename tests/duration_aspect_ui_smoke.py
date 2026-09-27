"""Windows GUI acceptance for deferred Duration edits and multi-Cut updates."""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageTk
from tkinterdnd2 import TkinterDnD

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main_window import MiniLogApp
from app.exporter import PREVIEW_RENDER, export_project
from app.models import Cut, Project


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="minilog-duration-ui-") as temporary:
        folder = Path(temporary)
        images = []
        for index in range(10):
            image = folder / f"image-{index:02d}.png"
            Image.new("RGB", (300, 400), (50 + index * 10, 120, 160)).save(image)
            images.append(str(image))

        root = TkinterDnD.Tk()
        root.withdraw()
        app = MiniLogApp(root)
        app.project.add_images(images)
        app.selected_index = 0
        app.selected_cut_ids = {app.project.cuts[0].id}
        app._refresh_all()
        root.deiconify()
        root.update()
        assert app.project.aspect_ratio == "3:4"
        assert app._preview_display_size() == (240, 320)

        app.select_cut(1)
        second_entry = app.card_duration_entries[1]
        second_entry.focus_force()
        root.update()
        second_entry.delete(0, "end")
        second_entry.insert(0, "4.5")
        second_entry.event_generate("<Return>")
        root.update()
        assert app.project.cuts[1].duration == 4.5
        app.select_cut(0)
        app.select_cut(1)
        app._mark_preview_stale()
        app._refresh_all()
        root.update()
        assert app.project.cuts[1].duration == 4.5
        assert app.card_duration_entries[1].get() == "4.5"
        first_save = folder / "duration-first-4-5.minilog"
        app.project.save(first_save)
        assert Project.load(first_save).cuts[1].duration == 4.5
        app.select_cut(0)

        entry = app.card_duration_entries[0]
        entry.focus_force()
        root.update()
        entry.delete(0, "end")
        entry.insert(0, "3")
        root.update()
        assert app.project.cuts[0].duration == 1.5
        assert entry.get() == "3"
        entry.event_generate("<Return>")
        root.update()
        assert app.project.cuts[0].duration == 3.0, (app.project.cuts[0].duration, entry.get())
        assert app.card_duration_entries[0] is entry

        entry.focus_force()
        entry.delete(0, "end")
        entry.insert(0, "2.5")
        root.update()
        assert app.project.cuts[0].duration == 3.0
        app.look_mode_combo.focus_set()
        root.update()
        assert app.project.cuts[0].duration == 2.5

        cards = tuple(app.card_widgets)
        for _ in range(10):
            app.card_duration_plus_buttons[0].invoke()
            root.update()
        assert app.project.cuts[0].duration == 3.5
        assert tuple(app.card_widgets) == cards
        assert app.card_duration_entries[0] is entry

        entry.focus_force()
        root.update()
        entry.delete(0, "end")
        entry.insert(0, "4.5")
        entry.event_generate("<Return>")
        root.update()
        first_cut = app.project.cuts[0]
        assert first_cut.duration == 4.5
        app.select_cut(1)
        root.update()
        app.select_cut(0)
        root.update()
        assert first_cut.duration == 4.5
        assert app.card_duration_entries[0].get() == "4.5"
        app._mark_preview_stale()
        app._refresh_all()
        root.update()
        assert first_cut.duration == 4.5
        assert app.card_duration_entries[0].get() == "4.5"
        persistence_path = folder / "duration-4-5.minilog"
        app.project.save(persistence_path)
        assert Project.load(persistence_path).cuts[0].duration == 4.5
        app.card_duration_plus_buttons[0].invoke()
        root.update()
        assert first_cut.duration == 4.6
        app.select_cut(1)
        app.select_cut(0)
        root.update()
        assert app.card_duration_entries[0].get() == "4.6"
        app.project.save(persistence_path)
        assert Project.load(persistence_path).cuts[0].duration == 4.6
        entry = app.card_duration_entries[0]
        entry.focus_force()
        root.update()
        entry.delete(0, "end")
        entry.insert(0, "5.5")
        app.select_cut(1)
        app.select_cut(0)
        root.update()
        assert first_cut.duration == 5.5
        assert app.card_duration_entries[0].get() == "5.5"

        app.select_cut(0)
        for index in (2, 4, 6, 8):
            app.select_cut(index, additive=True)
        assert len(app.selected_cut_ids) == 5 and app.selected_index == 8
        app.preview_path.touch()
        app.preview_generated_signature = app._project_signature()
        entry = app.card_duration_entries[8]
        entry.focus_force()
        root.update()
        entry.delete(0, "end")
        entry.insert(0, "2.0")
        entry.event_generate("<Return>")
        root.update()
        assert [app.project.cuts[index].duration for index in (0, 2, 4, 6, 8)] == [2.0] * 5
        assert app.status_var.get() == "5カットの表示時間を2.0秒に変更しました"
        assert app.preview_state_var.get() == "このプレビューは現在の編集内容と異なります"

        root.focus_force()
        root.update()
        root.event_generate("<Control-a>")
        root.update()
        assert len(app.selected_cut_ids) == 10
        entry = app.card_duration_entries[8]
        entry.focus_force()
        root.update()
        entry.delete(0, "end")
        entry.insert(0, "2.5")
        entry.event_generate("<Return>")
        root.update()
        assert all(cut.duration == 2.5 for cut in app.project.cuts)
        assert app.status_var.get() == "10カットの表示時間を2.5秒に変更しました"

        app.select_cut(0)
        app.project.cuts[0].caption_text = "Captionを選択"
        app._load_selected_cut_caption()
        app.cut_caption_text.focus_force()
        root.update()
        app.cut_caption_text.event_generate("<Control-a>")
        root.update()
        assert len(app.selected_cut_ids) == 1
        assert app.cut_caption_text.tag_ranges("sel")

        saved = folder / "duration.minilog"
        app.project.save(saved)
        restored = Project.load(saved)
        assert restored.aspect_ratio == "3:4"
        assert all(cut.duration == 2.5 for cut in restored.cuts)

        playback_project = Project(cuts=[Cut(images[0], duration=0.5)], aspect_ratio="3:4")
        export_project(playback_project, app.preview_path, settings=PREVIEW_RENDER)
        app.preview_project_snapshot = playback_project
        app.play_preview()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and (
            app.preview_photo is None or ImageTk.getimage(app.preview_photo).size != (240, 320)
        ):
            root.update()
            time.sleep(0.01)
        assert app.preview_photo is not None
        assert ImageTk.getimage(app.preview_photo).size == (240, 320)
        app.stop_preview()
        app.preview_temp.cleanup()
        root.destroy()
    print("Duration/aspect GUI acceptance: PASS (deferred input, 10 steps without rebuild, multi-select, Ctrl+A guard, stale, save/load, 3:4 playback)")


if __name__ == "__main__":
    main()
