"""Phase 0.5 acceptance: all motions plus a Phase 0 pan comparison."""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageStat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.exporter import FPS, HEIGHT, WIDTH, export_project, find_ffmpeg
from app.models import Cut, Project
from tests.human_acceptance import extract_frame, make_inputs


ARTIFACTS = ROOT / "output" / "phase05-acceptance"


def render_legacy_pan(source: Path, output: Path) -> None:
    ffmpeg = find_ffmpeg()
    frames = 3 * FPS
    video_filter = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},setsar=1,"
        f"zoompan=z='1.08':x='(iw-iw/zoom)*on/{frames - 1}':"
        f"y='(ih-ih/zoom)/2':d=1:s={WIDTH}x{HEIGHT}:fps={FPS},"
        "format=yuv420p"
    )
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-loop",
            "1",
            "-framerate",
            str(FPS),
            "-i",
            str(source),
            "-vf",
            video_filter,
            "-frames:v",
            str(frames),
            "-an",
            "-c:v",
            "libx264",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            str(output),
        ],
        check=True,
    )


def line_centroids(video: Path) -> list[float]:
    ffmpeg = find_ffmpeg()
    result = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video),
            "-vf",
            "crop=1080:24:0:948,format=gray",
            "-f",
            "rawvideo",
            "-",
        ],
        stdout=subprocess.PIPE,
        check=True,
    )
    frame_size = WIDTH * 24
    values = []
    for offset in range(0, len(result.stdout), frame_size):
        frame = result.stdout[offset : offset + frame_size]
        if len(frame) != frame_size:
            continue
        column_means = [sum(frame[row * WIDTH + x] for row in range(24)) / 24 for x in range(WIDTH)]
        weights = [max(0.0, value - 125.0) for value in column_means]
        total = sum(weights)
        values.append(sum(x * weight for x, weight in enumerate(weights)) / total)
    return values


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    inputs = make_inputs()
    all_motion = ARTIFACTS / "all-motion-types.mp4"
    project = Project(
        cuts=[
            Cut(str(inputs[0]), type="Motion", duration=3.0, motion_type="Zoom In"),
            Cut(str(inputs[1]), type="Motion", duration=3.0, motion_type="Zoom Out"),
            Cut(str(inputs[2]), type="Motion", duration=3.0, motion_type="Pan Left"),
            Cut(str(inputs[3]), type="Motion", duration=3.0, motion_type="Pan Right"),
        ],
        style="Natural",
    )
    export_project(project, all_motion, lambda message, value: print(f"{value:5.0%} {message}"))

    edge_means = []
    motion_differences = []
    for index in range(4):
        start = extract_frame(all_motion, index * 3 + 0.10, ARTIFACTS / f"motion-{index}-start.png")
        end = extract_frame(all_motion, index * 3 + 2.85, ARTIFACTS / f"motion-{index}-end.png")
        edges = [
            start.crop((0, 0, WIDTH, 4)),
            start.crop((0, HEIGHT - 4, WIDTH, HEIGHT)),
            start.crop((0, 0, 4, HEIGHT)),
            start.crop((WIDTH - 4, 0, WIDTH, HEIGHT)),
        ]
        edge_means.append(min(sum(ImageStat.Stat(edge).mean) for edge in edges))
        difference = sum(abs(a - b) for a, b in zip(start.tobytes(), end.tobytes())) / len(start.tobytes())
        motion_differences.append(difference)

    comparison_source = ARTIFACTS / "pan-comparison-source.png"
    image = Image.new("RGB", (WIDTH, HEIGHT), (105, 105, 105))
    draw = ImageDraw.Draw(image)
    draw.rectangle((294, 0, 305, HEIGHT), fill=(245, 245, 245))
    image.save(comparison_source)

    legacy = ARTIFACTS / "phase0-pan-right.mp4"
    improved = ARTIFACTS / "phase05-pan-right.mp4"
    render_legacy_pan(comparison_source, legacy)
    export_project(
        Project(cuts=[Cut(str(comparison_source), type="Motion", duration=3.0, motion_type="Pan Right")]),
        improved,
    )
    old_positions = line_centroids(legacy)
    new_positions = line_centroids(improved)
    old_steps = [abs(b - a) for a, b in zip(old_positions[15:74], old_positions[16:75])]
    new_steps = [abs(b - a) for a, b in zip(new_positions[15:74], new_positions[16:75])]
    old_zero_steps = sum(step < 0.05 for step in old_steps)
    new_zero_steps = sum(step < 0.05 for step in new_steps)

    results = {
        "size": [WIDTH, HEIGHT],
        "fps": FPS,
        "duration": 12.0,
        "motion_types_checked": ["Zoom In", "Zoom Out", "Pan Left", "Pan Right"],
        "minimum_edge_rgb_sum_mean": round(min(edge_means), 2),
        "motion_start_end_mean_differences": [round(value, 3) for value in motion_differences],
        "phase0_mid_motion_zero_steps": old_zero_steps,
        "phase05_mid_motion_zero_steps": new_zero_steps,
        "phase0_step_stdev": round(statistics.pstdev(old_steps), 4),
        "phase05_step_stdev": round(statistics.pstdev(new_steps), 4),
    }
    (ARTIFACTS / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    assert min(edge_means) > 10
    assert all(value > 0.5 for value in motion_differences)
    assert new_zero_steps <= old_zero_steps
    print(f"PASS: {all_motion}")


if __name__ == "__main__":
    main()
