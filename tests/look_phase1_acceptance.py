"""End-to-end LOOK checks using a generated 3D LUT and mixed media."""

from __future__ import annotations

import sys
import tempfile
import subprocess
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.exporter import (
    FINAL_RENDER, PREVIEW_RENDER, RenderSettings, build_cut_caption_panel, cut_caption_y,
    export_project, find_ffmpeg,
)
from app.look_engine import apply_still_look, validate_cube
from app.models import Cut, Project
from phase2b_acceptance import make_media, verify_output


def write_invert_cube(path: Path) -> None:
    lines = ["TITLE \"Invert for test\"", "LUT_3D_SIZE 2", "DOMAIN_MIN 0 0 0", "DOMAIN_MAX 1 1 1"]
    for blue in range(2):
        for green in range(2):
            for red in range(2):
                lines.append(f"{1-red} {1-green} {1-blue}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def frame(path: Path, seconds: float, width: int, height: int) -> Image.Image:
    result = subprocess.run(
        [
            find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-ss", str(seconds),
            "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
        ],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return Image.frombytes("RGB", (width, height), result.stdout)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="minilog-look-") as temporary:
        folder = Path(temporary)
        images, video, bgm = make_media(folder)
        cube_path = folder / "Invert.cube"
        write_invert_cube(cube_path)
        cube = validate_cube(cube_path)
        still = Image.new("RGB", (1, 1), (64, 128, 192))
        assert apply_still_look(still, cube, 0).getpixel((0, 0)) == (64, 128, 192)
        assert all(abs(a - b) <= 2 for a, b in zip(apply_still_look(still, cube, 1).getpixel((0, 0)), (191, 127, 63)))

        project = Project(
            cuts=[
                Cut(str(images[0]), duration=1, transition_type="crossfade", caption_text="はじまり。"),
                Cut(str(images[1]), type="Motion", duration=1, transition_type="fade", caption_text="動画風。", caption_motion="slide_up"),
                Cut(str(video), type="Video", duration=1, media_duration=1, transition_type="dip_black", transition_duration=0.6),
                Cut(str(images[2]), duration=1, caption_text="おしまい。", caption_motion="soft_zoom"),
            ],
            bgm_path=str(bgm), caption_text="まとめ。", caption_duration=0.4,
        )
        project.cuts[1].normalize()
        project.cuts[2].normalize()
        settings = RenderSettings(160, 284, 10, 2, "ultrafast", 30, True)
        outputs = {}
        for strength in (None, 0.0, 0.5, 1.0):
            project.look_type = "original" if strength is None else "custom_lut"
            project.look_lut_path = None if strength is None else str(cube_path)
            project.look_strength = 1.0 if strength is None else strength
            target = folder / f"look-{strength}.mp4"
            export_project(project, target, settings=settings)
            verify_output(target, project.total_duration())
            outputs[strength] = target

        original = frame(outputs[None], 0.5, 160, 284).getpixel((10, 10))
        zero = frame(outputs[0.0], 0.5, 160, 284).getpixel((10, 10))
        half = frame(outputs[0.5], 0.5, 160, 284).getpixel((10, 10))
        full = frame(outputs[1.0], 0.5, 160, 284).getpixel((10, 10))
        assert max(abs(a-b) for a, b in zip(original, zero)) <= 12, (original, zero)
        assert max(abs(a-b) for a, b in zip(original, full)) >= 35, (original, full)
        assert all(min(a, b)-8 <= middle <= max(a, b)+8 for a, middle, b in zip(zero, half, full)), (zero, half, full)
        panel = build_cut_caption_panel("はじまり。", 160, 284)
        text_pixel = next(
            (x, y) for y in range(panel.height) for x in range(panel.width)
            if min(panel.getpixel((x, y))[:3]) >= 245 and panel.getpixel((x, y))[3] == 255
        )
        caption_x = (160-panel.width)//2 + text_pixel[0]
        caption_y = cut_caption_y("bottom", 284, panel.height) + text_pixel[1]
        assert min(frame(outputs[1.0], 0.5, 160, 284).getpixel((caption_x, caption_y))) >= 180
        assert max(frame(outputs[1.0], 2.7, 160, 284).getpixel((10, 10))) >= 230  # transition black is graded
        assert max(frame(outputs[1.0], 4.0, 160, 284).getpixel((10, 10))) <= 12  # End Caption remains black

        project.look_strength = 0.5
        saved = folder / "look.minilog"
        project.save(saved)
        restored = Project.load(saved)
        assert (restored.look_type, restored.look_lut_path, restored.look_strength) == ("custom_lut", str(cube_path), 0.5)
        legacy = Project.from_dict({"cuts": [{"source_path": str(images[0])}]})
        assert (legacy.look_type, legacy.look_lut_path, legacy.look_strength) == ("original", None, 1.0)

        project.look_strength = 1.0
        final = folder / "final.mp4"
        export_project(project, final, settings=PREVIEW_RENDER)
        verify_output(final, project.total_duration())

        full_project = Project(
            cuts=[Cut(str(images[0]), duration=0.5, caption_text="確認。")],
            look_type="custom_lut", look_lut_path=str(cube_path),
            bgm_path=str(bgm),
        )
        full_output = folder / "full-resolution.mp4"
        export_project(full_project, full_output, settings=FINAL_RENDER)
        verify_output(full_output, full_project.total_duration())
        image = frame(full_output, 0.25, 1080, 1920)
        assert image.size == (1080, 1920)

    print("LOOK Phase 1 acceptance: PASS (Original, 0/50/100%, mixed cuts, transitions, BGM, End Caption, save/load)")


if __name__ == "__main__":
    main()
