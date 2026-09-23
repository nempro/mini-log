"""Generate the Phase 1A preview and matching final MP4, then compare them."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont, ImageStat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.exporter import FINAL_RENDER, PREVIEW_RENDER, export_project
from app.models import Cut, Project
from tests.human_acceptance import extract_frame, make_inputs


ARTIFACTS = ROOT / "output" / "phase1a-acceptance"


def metadata(path: Path) -> dict:
    reader = imageio_ffmpeg.read_frames(str(path), pix_fmt="rgb24")
    result = next(reader)
    reader.close()
    return result


def make_seventh_image() -> Path:
    path = ARTIFACTS / "input-7.png"
    image = Image.new("RGB", (1400, 1000), (74, 132, 192))
    draw = ImageDraw.Draw(image)
    for offset in range(-1000, 1600, 180):
        draw.line((offset, 0, offset + 1000, 1000), fill=(46, 104, 164), width=30)
    font_path = Path("C:/Windows/Fonts/meiryob.ttc")
    font = ImageFont.truetype(str(font_path), 180) if font_path.is_file() else ImageFont.load_default()
    draw.rounded_rectangle((510, 330, 890, 670), radius=60, fill=(248, 244, 235))
    draw.text((585, 390), "07", fill=(35, 35, 35), font=font)
    image.save(path)
    return path


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    inputs = make_inputs() + [make_seventh_image()]
    project = Project(
        cuts=[
            Cut(str(inputs[0]), type="Motion", duration=3.0, motion_type="Zoom In"),
            Cut(str(inputs[1]), type="Still", duration=1.5),
            Cut(str(inputs[2]), type="Still", duration=1.5),
            Cut(str(inputs[3]), type="Motion", duration=3.0, motion_type="Pan Right"),
            Cut(str(inputs[4]), type="Motion", duration=3.0, motion_type="Zoom Out"),
            Cut(str(inputs[5]), type="Still", duration=1.5),
            Cut(str(inputs[6]), type="Motion", duration=3.0, motion_type="Pan Left"),
        ],
        style="Film",
        caption_text="今日のまとめ。",
        caption_duration=1.8,
    )
    assert abs(project.total_duration() - 18.3) < 0.001

    preview = ARTIFACTS / "preview.mp4"
    final = ARTIFACTS / "final.mp4"
    started = time.perf_counter()
    export_project(project, preview, settings=PREVIEW_RENDER)
    preview_seconds = time.perf_counter() - started
    started = time.perf_counter()
    export_project(project, final, settings=FINAL_RENDER)
    final_seconds = time.perf_counter() - started

    preview_meta = metadata(preview)
    final_meta = metadata(final)
    cut_starts = [0.0, 3.0, 4.5, 6.0, 9.0, 12.0, 13.5]
    preview_motion_differences = []
    for index in (0, 3, 4, 6):
        start = extract_frame(preview, cut_starts[index] + 0.1, ARTIFACTS / f"preview-{index}-start.png")
        end = extract_frame(preview, cut_starts[index] + project.cuts[index].duration - 0.15, ARTIFACTS / f"preview-{index}-end.png")
        difference = sum(abs(a - b) for a, b in zip(start.tobytes(), end.tobytes())) / len(start.tobytes())
        preview_motion_differences.append(difference)

    caption = extract_frame(preview, 17.2, ARTIFACTS / "preview-caption.png")
    caption_mean = sum(ImageStat.Stat(caption).mean) / 3
    caption_white = max(channel[1] for channel in caption.getextrema())

    results = {
        "project_duration": project.total_duration(),
        "preview_size": preview_meta.get("size"),
        "preview_fps": preview_meta.get("fps"),
        "preview_duration": preview_meta.get("duration"),
        "preview_codec": preview_meta.get("codec"),
        "preview_pixel_format": preview_meta.get("pix_fmt"),
        "final_size": final_meta.get("size"),
        "final_duration": final_meta.get("duration"),
        "preview_generation_seconds": round(preview_seconds, 3),
        "final_generation_seconds": round(final_seconds, 3),
        "speed_ratio": round(final_seconds / preview_seconds, 2),
        "motion_differences": [round(value, 3) for value in preview_motion_differences],
        "caption_background_mean": round(caption_mean, 3),
        "caption_white_max": caption_white,
    }
    (ARTIFACTS / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    assert preview_meta.get("size") == (360, 640)
    assert final_meta.get("size") == (1080, 1920)
    assert abs(preview_meta.get("fps") - 30) < 0.01
    assert 18.1 <= preview_meta.get("duration") <= 18.5
    assert abs(preview_meta.get("duration") - final_meta.get("duration")) < 0.05
    assert preview_seconds < final_seconds
    assert all(value > 0.5 for value in preview_motion_differences)
    assert caption_mean < 20
    assert caption_white > 220
    print(f"PASS: {preview}")


if __name__ == "__main__":
    main()
