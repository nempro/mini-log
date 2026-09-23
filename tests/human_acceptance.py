"""Generate and inspect the Phase 0 acceptance movie.

This intentionally uses synthetic, visually distinct photos so cut order and motion
can be checked deterministically without bundling user media.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.exporter import FPS, HEIGHT, WIDTH, export_project, find_ffmpeg
from app.models import Cut, Project


ARTIFACTS = ROOT / "output" / "acceptance"


def make_inputs() -> list[Path]:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    colors = [
        (219, 91, 73),
        (63, 134, 168),
        (228, 175, 70),
        (74, 147, 107),
        (132, 91, 166),
        (202, 111, 154),
    ]
    font_path = Path("C:/Windows/Fonts/meiryob.ttc")
    font = ImageFont.truetype(str(font_path), 180) if font_path.is_file() else ImageFont.load_default()
    paths = []
    for index, color in enumerate(colors, start=1):
        path = ARTIFACTS / f"input-{index}.png"
        image = Image.new("RGB", (1400, 1000), color)
        draw = ImageDraw.Draw(image)
        for offset in range(-1000, 1600, 180):
            draw.line((offset, 0, offset + 1000, 1000), fill=tuple(max(0, c - 28) for c in color), width=30)
        label = f"{index:02d}"
        bounds = draw.textbbox((0, 0), label, font=font)
        draw.rounded_rectangle((510, 330, 890, 670), radius=60, fill=(248, 244, 235))
        draw.text(
            ((1400 - (bounds[2] - bounds[0])) / 2, (1000 - (bounds[3] - bounds[1])) / 2 - bounds[1]),
            label,
            fill=(35, 35, 35),
            font=font,
        )
        image.save(path)
        paths.append(path)
    return paths


def extract_frame(video: Path, at_seconds: float, output: Path) -> Image.Image:
    ffmpeg = find_ffmpeg()
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{at_seconds:.3f}",
        "-i",
        str(video),
        "-frames:v",
        "1",
        str(output),
    ]
    subprocess.run(command, check=True)
    return Image.open(output).convert("RGB")


def inspect(video: Path) -> dict:
    reader = imageio_ffmpeg.read_frames(str(video), pix_fmt="rgb24")
    metadata = next(reader)
    reader.close()

    cut_starts = [0.0, 3.0, 4.5, 6.0, 9.0, 12.0]
    samples = [extract_frame(video, start + 0.3, ARTIFACTS / f"sample-{i}.png") for i, start in enumerate(cut_starts)]
    edge_minima = []
    for image in samples:
        edge = Image.new("RGB", (image.width, 8))
        edge.paste(image.crop((0, 0, image.width, 4)), (0, 0))
        edge.paste(image.crop((0, image.height - 4, image.width, image.height)), (0, 4))
        edge_minima.append(round(sum(ImageStat.Stat(edge).mean)))

    motion_start = extract_frame(video, 0.10, ARTIFACTS / "motion-start.png")
    motion_end = extract_frame(video, 2.85, ARTIFACTS / "motion-end.png")
    motion_difference = sum(ImageStat.Stat(ImageChops.difference(motion_start, motion_end)).mean) / 3

    still_start = extract_frame(video, 3.10, ARTIFACTS / "still-start.png")
    still_end = extract_frame(video, 4.35, ARTIFACTS / "still-end.png")
    still_difference = sum(ImageStat.Stat(ImageChops.difference(still_start, still_end)).mean) / 3

    caption = extract_frame(video, 14.2, ARTIFACTS / "caption.png")
    caption_stat = ImageStat.Stat(caption)
    caption_has_black_background = sum(caption_stat.mean) / 3 < 15
    caption_has_white_text = max(channel[1] for channel in caption.crop((90, 600, 990, 1320)).getextrema()) > 220

    return {
        "size": metadata.get("size"),
        "fps": metadata.get("fps"),
        "duration": metadata.get("duration"),
        "codec": metadata.get("codec"),
        "pixel_format": metadata.get("pix_fmt"),
        "edge_minimum_rgb_sum": min(edge_minima),
        "motion_mean_difference": round(motion_difference, 3),
        "still_mean_difference": round(still_difference, 3),
        "caption_has_black_background": caption_has_black_background,
        "caption_has_white_text": caption_has_white_text,
    }


def main() -> None:
    paths = make_inputs()
    project = Project(
        cuts=[
            Cut(str(paths[0]), type="Motion", duration=3.0, motion_type="Zoom In"),
            Cut(str(paths[1]), type="Still", duration=1.5),
            Cut(str(paths[2]), type="Still", duration=1.5),
            Cut(str(paths[3]), type="Motion", duration=3.0, motion_type="Pan Right"),
            Cut(str(paths[4]), type="Motion", duration=3.0, motion_type="Zoom Out"),
            Cut(str(paths[5]), type="Still", duration=2.0),
        ],
        style="Soft",
        caption_text="水族館に行った日。",
        caption_duration=2.0,
    )
    output = ARTIFACTS / "mini-log-phase0-acceptance.mp4"
    export_project(project, output, lambda message, value: print(f"{value:5.0%} {message}"))
    results = inspect(output)
    (ARTIFACTS / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    assert results["size"] == (WIDTH, HEIGHT)
    assert abs(results["fps"] - FPS) < 0.01
    assert 15.8 <= results["duration"] <= 16.2
    assert results["edge_minimum_rgb_sum"] > 10
    assert results["motion_mean_difference"] > 0.5
    assert results["still_mean_difference"] < 0.25
    assert results["caption_has_black_background"]
    assert results["caption_has_white_text"]
    print(f"PASS: {output}")


if __name__ == "__main__":
    main()
