"""Generate and inspect the exact Phase 1B six-cut acceptance project."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.exporter import FINAL_RENDER, PREVIEW_RENDER, export_project
from app.models import Cut, Project
from tests.human_acceptance import extract_frame


ARTIFACTS = ROOT / "output" / "phase1b-acceptance"


def make_inputs() -> list[Path]:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    colors = [(26, 56, 82), (58, 38, 77), (32, 73, 59), (75, 45, 32), (38, 61, 92), (70, 36, 58)]
    paths: list[Path] = []
    for index, color in enumerate(colors, start=1):
        path = ARTIFACTS / f"input-{index}.png"
        image = Image.new("RGB", (1000, 1400), color)
        draw = ImageDraw.Draw(image)
        for offset in range(-1400, 1200, 130):
            accent = tuple(min(175, channel + 35) for channel in color)
            draw.line((offset, 0, offset + 1400, 1400), fill=accent, width=18)
        draw.ellipse((300, 500, 700, 900), outline=tuple(min(190, c + 70) for c in color), width=30)
        image.save(path)
        paths.append(path)
    return paths


def metadata(path: Path) -> dict:
    reader = imageio_ffmpeg.read_frames(str(path), pix_fmt="rgb24")
    value = next(reader)
    reader.close()
    return value


def white_bbox(image: Image.Image, threshold: int = 205) -> tuple[int, int, int, int] | None:
    mask = Image.new("1", image.size)
    mask.putdata([
        1 if red >= threshold and green >= threshold and blue >= threshold else 0
        for red, green, blue in image.getdata()
    ])
    return mask.getbbox()


def white_count(image: Image.Image, threshold: int = 205) -> int:
    return sum(
        1
        for red, green, blue in image.getdata()
        if red >= threshold and green >= threshold and blue >= threshold
    )


def normalized_center_y(box: tuple[int, int, int, int], height: int) -> float:
    return (box[1] + box[3]) / (2 * height)


def inspect_render(video: Path, prefix: str) -> dict:
    starts = [0.0, 3.0, 4.5, 7.5, 9.0, 12.0]
    positions = []
    for index, start in enumerate(starts):
        frame = extract_frame(video, start + 0.75, ARTIFACTS / f"{prefix}-cut-{index + 1}.png")
        box = white_bbox(frame)
        positions.append(None if box is None else round(normalized_center_y(box, frame.height), 3))

    fade_start = extract_frame(video, 0.03, ARTIFACTS / f"{prefix}-fade-start.png")
    fade_middle = extract_frame(video, 0.50, ARTIFACTS / f"{prefix}-fade-middle.png")
    fade_end = extract_frame(video, 2.85, ARTIFACTS / f"{prefix}-fade-end.png")
    fixed_start = extract_frame(video, 3.03, ARTIFACTS / f"{prefix}-fixed-start.png")
    slide_start = extract_frame(video, 4.65, ARTIFACTS / f"{prefix}-slide-start.png")
    slide_middle = extract_frame(video, 4.90, ARTIFACTS / f"{prefix}-slide-middle.png")
    zoom_start = extract_frame(video, 9.27, ARTIFACTS / f"{prefix}-zoom-start.png")
    zoom_middle = extract_frame(video, 9.65, ARTIFACTS / f"{prefix}-zoom-middle.png")
    end_caption = extract_frame(video, 14.6, ARTIFACTS / f"{prefix}-end-caption.png")

    slide_start_box = white_bbox(slide_start, 150)
    slide_middle_box = white_bbox(slide_middle, 150)
    zoom_start_box = white_bbox(zoom_start, 150)
    zoom_middle_box = white_bbox(zoom_middle, 150)
    return {
        "positions": positions,
        "fade_counts": [white_count(fade_start, 150), white_count(fade_middle, 150), white_count(fade_end, 150)],
        "fixed_start_count": white_count(fixed_start),
        "empty_cut_count": white_count(extract_frame(video, 8.0, ARTIFACTS / f"{prefix}-empty.png")),
        "slide_y": [slide_start_box[1], slide_middle_box[1]] if slide_start_box and slide_middle_box else None,
        "zoom_width": [zoom_start_box[2] - zoom_start_box[0], zoom_middle_box[2] - zoom_middle_box[0]]
        if zoom_start_box and zoom_middle_box
        else None,
        "end_caption_count": white_count(end_caption),
    }


def main() -> None:
    paths = make_inputs()
    project = Project(
        cuts=[
            Cut(str(paths[0]), type="Motion", motion_type="Zoom In", duration=3.0, caption_text="はじまり。", caption_position="bottom", caption_motion="fade"),
            Cut(str(paths[1]), type="Still", duration=1.5, caption_text="今日の一枚。", caption_position="center", caption_motion="fixed"),
            Cut(str(paths[2]), type="Motion", motion_type="Pan Right", duration=3.0, caption_text="少し移動。", caption_position="top", caption_motion="slide_up"),
            Cut(str(paths[3]), type="Still", duration=1.5, caption_text=""),
            Cut(str(paths[4]), type="Motion", motion_type="Zoom Out", duration=3.0, caption_text="もう少しだけ。", caption_position="bottom", caption_motion="soft_zoom"),
            Cut(str(paths[5]), type="Still", duration=2.0, caption_text="おしまい。", caption_position="bottom", caption_motion="fade"),
        ],
        style="Soft",
        caption_text="今日のまとめ。",
        caption_duration=2.0,
    )
    project_file = ARTIFACTS / "phase1b.minilog"
    project.save(project_file)
    restored = Project.load(project_file)
    assert [
        (cut.caption_text, cut.caption_position, cut.caption_motion) for cut in restored.cuts
    ] == [
        (cut.caption_text, cut.caption_position, cut.caption_motion) for cut in project.cuts
    ]
    project = restored
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
    preview_result = inspect_render(preview, "preview")
    final_result = inspect_render(final, "final")
    result = {
        "project_duration": project.total_duration(),
        "preview_size": preview_meta.get("size"),
        "final_size": final_meta.get("size"),
        "preview_duration": preview_meta.get("duration"),
        "final_duration": final_meta.get("duration"),
        "preview_generation_seconds": round(preview_seconds, 3),
        "final_generation_seconds": round(final_seconds, 3),
        "preview": preview_result,
        "final": final_result,
    }
    (ARTIFACTS / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    assert preview_meta.get("size") == (360, 640)
    assert final_meta.get("size") == (1080, 1920)
    assert abs(preview_meta.get("duration") - project.total_duration()) < 0.1
    assert abs(preview_meta.get("duration") - final_meta.get("duration")) < 0.05
    for inspected in (preview_result, final_result):
        assert inspected["positions"][0] > 0.65
        assert 0.35 < inspected["positions"][1] < 0.65
        assert inspected["positions"][2] < 0.35
        assert inspected["positions"][3] is None
        assert inspected["positions"][4] > 0.65
        assert inspected["positions"][5] > 0.65
        assert inspected["fade_counts"][1] > inspected["fade_counts"][0]
        assert inspected["fade_counts"][1] > inspected["fade_counts"][2]
        assert inspected["fixed_start_count"] > 0
        assert inspected["empty_cut_count"] == 0
        assert inspected["slide_y"][0] > inspected["slide_y"][1]
        assert inspected["zoom_width"][0] < inspected["zoom_width"][1]
        assert inspected["end_caption_count"] > 0
    for preview_y, final_y in zip(preview_result["positions"], final_result["positions"]):
        if preview_y is not None:
            assert abs(preview_y - final_y) < 0.03
    print(f"PASS: {preview}")
    print(f"PASS: {final}")


if __name__ == "__main__":
    main()
