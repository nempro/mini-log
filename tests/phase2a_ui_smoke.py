"""Exercise Phase 2A Tk controls with the distribution's bundled Tcl/Tk runtime."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tkinterdnd2 import TkinterDnD

from app.exporter import find_ffmpeg, probe_video
from app.main_window import MiniLogApp
from app.models import Project


def make_video(path: Path, duration: float, frequency: int) -> None:
    subprocess.run(
        [
            find_ffmpeg(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size=320x180:rate=24:duration={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:sample_rate=48000:duration={duration}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="minilog-phase2a-ui-") as temporary:
        folder = Path(temporary)
        materials: list[Path] = []
        for index in range(3):
            image_path = folder / f"still-{index}.png"
            Image.new("RGB", (320, 240), (30 + index * 40, 105, 80)).save(image_path)
            materials.append(image_path)
        first_video = folder / "video-a.mp4"
        second_video = folder / "video-b.mp4"
        make_video(first_video, 2.0, 440)
        make_video(second_video, 1.2, 660)

        ordered_materials = [materials[0], first_video, materials[1], second_video, materials[2]]
        project = Project()
        images, videos, errors = project.add_materials(
            [str(path) for path in ordered_materials], probe_video
        )
        assert (images, videos, errors) == (3, 2, [])
        assert [cut.type for cut in project.cuts] == ["Still", "Video", "Still", "Video", "Still"]

        root = TkinterDnD.Tk()
        root.withdraw()
        app = MiniLogApp(root)
        app.project = project
        app.selected_index = 0
        app.selected_cut_ids = {project.cuts[0].id}
        app._refresh_all()
        root.update()

        assert app.preview_visible and app.preview_area.winfo_manager() == "pack"
        app.toggle_preview_visibility()
        root.update()
        assert app.preview_area.winfo_manager() == ""
        assert app.cut_caption_text.winfo_manager() == "grid"
        app.toggle_preview_visibility()
        root.update()
        assert app.preview_area.winfo_manager() == "pack"
        children = app.preview_area.master.pack_slaves()
        assert children.index(app.preview_heading) < children.index(app.preview_area) < children.index(app.cut_scope)

        app.select_cut(1)
        assert app.video_audio_section.winfo_manager() == "pack"
        assert app.video_audio_var.get()
        app.video_audio_var.set(False)
        app._on_video_audio_toggle()
        assert not project.cuts[1].use_source_audio
        app.video_audio_volume_var.set(35)
        app._on_video_audio_volume_changed(35)
        assert project.cuts[1].source_audio_volume == 0.35

        app.select_cut(1)
        app.select_cut(3, additive=True)
        app.select_cut(4, additive=True)
        assert app.selected_index == 4
        selected_ids = {project.cuts[index].id for index in (1, 3, 4)}
        assert app.selected_cut_ids == selected_ids
        app.preview_path.touch()
        app.preview_generated_signature = app._project_signature()
        entry = app.card_duration_entries[4]
        entry.delete(0, "end")
        entry.insert(0, "1.9")
        app.card_duration_plus_buttons[4].invoke()
        root.update()
        actual_durations = [project.cuts[index].duration for index in (1, 3, 4)]
        assert actual_durations == [2.0, 1.2, 2.0], actual_durations
        assert app.preview_state_var.get() == "このプレビューは現在の編集内容と異なります"
        assert app.status_var.get() == "3カットの表示時間を2.0秒に変更しました（動画は素材尺まで）"
        assert project.cut_start_time(4) == sum(cut.effective_duration() for cut in project.cuts[:4])

        project_path = folder / "phase2a.minilog"
        project.save(project_path)
        restored = Project.load(project_path)
        assert [cut.type for cut in restored.cuts] == [cut.type for cut in project.cuts]
        assert not restored.cuts[1].use_source_audio
        assert restored.cuts[1].source_audio_volume == 0.35
        assert restored.cuts[3].duration == 1.2

        app.preview_temp.cleanup()
        root.destroy()

    print("Phase 2A UI smoke: PASS (video audio controls, Preview fold, multi-Cut Duration, save/load)")


if __name__ == "__main__":
    main()
