"""End-to-end ratio checks for first material, Preview, and final MP4."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.exporter import (
    FINAL_RENDER, PREVIEW_RENDER, export_project, find_ffmpeg,
    probe_video, probe_video_dimensions,
)
from app.models import Project


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="minilog-ratio-") as temporary:
        folder = Path(temporary)
        cases = (
            ("3by4", (300, 400), "3:4", (360, 480), (1080, 1440)),
            ("square", (240, 240), "1:1", (360, 360), (1080, 1080)),
            ("wide", (320, 180), "16:9", (640, 360), (1920, 1080)),
        )
        for name, image_size, ratio, preview_size, final_size in cases:
            source = folder / f"{name}.png"
            Image.new("RGB", image_size, (90, 145, 190)).save(source)
            project = Project()
            project.add_materials([str(source)], probe_video, probe_video_dimensions)
            project.cuts[0].duration = 0.5
            assert project.aspect_ratio == ratio

            if name == "3by4":
                second = folder / "portrait.png"
                Image.new("RGB", (90, 160), (175, 105, 80)).save(second)
                project.add_materials([str(second)], probe_video, probe_video_dimensions)
                project.cuts[1].duration = 0.5
                assert project.aspect_ratio == "3:4"
                saved = folder / "mixed.minilog"
                project.save(saved)
                project = Project.load(saved)
                assert project.aspect_ratio == "3:4"

            preview = folder / f"{name}-preview.mp4"
            final = folder / f"{name}-final.mp4"
            export_project(project, preview, settings=PREVIEW_RENDER)
            export_project(project, final, settings=FINAL_RENDER)
            assert probe_video_dimensions(preview) == preview_size
            assert probe_video_dimensions(final) == final_size

        video = folder / "first-video.mp4"
        subprocess.run(
            [find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=10:duration=0.6",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        video_project = Project()
        image_count, video_count, errors = video_project.add_materials(
            [str(video)], probe_video, probe_video_dimensions
        )
        assert (image_count, video_count, errors) == (0, 1, [])
        assert video_project.aspect_ratio == "16:9"
        video_preview = folder / "first-video-preview.mp4"
        video_final = folder / "first-video-final.mp4"
        export_project(video_project, video_preview, settings=PREVIEW_RENDER)
        export_project(video_project, video_final, settings=FINAL_RENDER)
        assert probe_video_dimensions(video_preview) == (640, 360)
        assert probe_video_dimensions(video_final) == (1920, 1080)
        assert Project.from_dict({"cuts": []}).aspect_ratio == "9:16"
    print("Aspect ratio acceptance: PASS (3:4, 1:1, 16:9 Preview/final MP4, mixed media, first video export, save/load, legacy)")


if __name__ == "__main__":
    main()
