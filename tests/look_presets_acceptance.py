"""Small real-FFmpeg check for built-in LOOKs and strength blending."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.exporter import FINAL_RENDER, PREVIEW_RENDER, RenderSettings, export_project, find_ffmpeg
from app.look_engine import PRESET_IDS
from app.models import Cut, Project
from look_phase1_acceptance import frame
from phase2b_acceptance import make_media, verify_output


def sample(path: Path, seconds: float) -> tuple[int, int, int]:
    result = subprocess.run(
        [
            find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-ss", str(seconds),
            "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
        ],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return Image.frombytes("RGB", (160, 284), result.stdout).getpixel((10, 10))


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="minilog-presets-") as temporary:
        folder = Path(temporary)
        source = folder / "source.png"
        Image.new("RGB", (160, 284), (80, 135, 190)).save(source)
        project = Project(cuts=[Cut(str(source), duration=0.8)], caption_text="おわり。", caption_duration=0.4)
        settings = RenderSettings(160, 284, 10, 2, "ultrafast", 30, False)
        samples = {}
        for preset_id, strength in ((None, 1.0), *((preset, level) for preset in sorted(PRESET_IDS)
                                                for level in (0.0, 0.5, 1.0))):
            project.look_type = "original" if preset_id is None else preset_id
            project.look_strength = strength
            output = folder / f"{preset_id or 'original'}-{strength}.mp4"
            export_project(project, output, settings=settings)
            assert output.is_file() and output.stat().st_size > 1000
            samples[(preset_id, strength)] = sample(output, 0.3)
            assert max(sample(output, 1.0)) <= 15  # End Caption remains black.

        original = samples[(None, 1.0)]
        for preset_id in PRESET_IDS:
            zero = samples[(preset_id, 0.0)]
            half = samples[(preset_id, 0.5)]
            full = samples[(preset_id, 1.0)]
            assert max(abs(a - b) for a, b in zip(original, zero)) <= 12
            assert max(abs(a - b) for a, b in zip(original, full)) >= 5
            assert all(min(a, b) - 8 <= value <= max(a, b) + 8
                       for a, value, b in zip(original, half, full))
        assert len({samples[(preset_id, 1.0)] for preset_id in PRESET_IDS}) == len(PRESET_IDS)
        preview = folder / "preview.mp4"
        project.look_type = "cool"
        project.look_strength = 0.5
        export_project(project, preview, settings=PREVIEW_RENDER)
        assert preview.is_file() and preview.stat().st_size > 1000

        images, video, bgm = make_media(folder)
        mixed = Project(
            cuts=[
                Cut(str(images[0]), duration=1, transition_type="crossfade", caption_text="記録。"),
                Cut(str(images[1]), type="Motion", duration=1, transition_type="fade", caption_text="移動。"),
                Cut(str(video), type="Video", duration=1, media_duration=1),
            ],
            look_type="film", bgm_path=str(bgm), caption_text="終わり。", caption_duration=0.4,
        )
        for cut in mixed.cuts:
            cut.normalize()
        mixed_output = folder / "mixed-film.mp4"
        export_project(mixed, mixed_output, settings=settings)
        verify_output(mixed_output, mixed.total_duration())
        caption_frame = frame(mixed_output, 0.3, 160, 284)
        white_text_pixels = sum(
            min(caption_frame.getpixel((x, y))) >= 180
            for y in range(185, 260) for x in range(20, 140)
        )
        assert white_text_pixels >= 5, white_text_pixels
        assert max(frame(mixed_output, mixed.total_duration() - 0.2, 160, 284).getpixel((10, 10))) <= 15
        saved = folder / "film.minilog"
        mixed.look_strength = 0.7
        mixed.save(saved)
        restored = Project.load(saved)
        assert (restored.look_type, restored.look_lut_path, restored.look_strength) == ("film", None, 0.7)
        final_project = Project(
            cuts=[Cut(str(images[0]), duration=0.5)], look_type="retro", bgm_path=str(bgm),
        )
        final = folder / "retro-final.mp4"
        export_project(final_project, final, settings=FINAL_RENDER)
        verify_output(final, final_project.total_duration())
        assert frame(final, 0.2, 1080, 1920).size == (1080, 1920)
    print("LOOK Phase 2 presets acceptance: PASS (5 presets, 0/50/100%, mixed cuts, audio, Preview/final MP4, End Caption, save/load)")


if __name__ == "__main__":
    main()
