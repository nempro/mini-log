"""Render Phase 1D caption font, size, and long-text acceptance videos."""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import imageio_ffmpeg
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.exporter import FINAL_RENDER, PREVIEW_RENDER, build_cut_caption_panel, export_project
from app.models import Cut, Project
from tests.human_acceptance import extract_frame
from tests.phase1b_acceptance import make_inputs


ARTIFACTS = ROOT / "output" / "phase1d-acceptance"


def metadata(path: Path) -> dict:
    reader = imageio_ffmpeg.read_frames(str(path), pix_fmt="rgb24")
    value = next(reader)
    reader.close()
    return value


def white_bbox(image: Image.Image, threshold: int = 180) -> tuple[int, int, int, int] | None:
    mask = Image.new("1", image.size)
    mask.putdata([
        1 if red >= threshold and green >= threshold and blue >= threshold else 0
        for red, green, blue in image.getdata()
    ])
    return mask.getbbox()


def caption_metrics(video: Path, prefix: str) -> list[dict]:
    starts = [0.0, 3.0, 4.5, 7.5, 9.0, 12.0]
    values: list[dict] = []
    for index, start in enumerate(starts):
        frame = extract_frame(video, start + 0.75, ARTIFACTS / f"{prefix}-cut-{index + 1}.png")
        box = white_bbox(frame)
        assert box is not None
        values.append(
            {
                "width": box[2] - box[0],
                "height": box[3] - box[1],
                "normalized_width": round((box[2] - box[0]) / frame.width, 3),
                "normalized_height": round((box[3] - box[1]) / frame.height, 3),
            }
        )
    return values


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    paths = make_inputs()
    long_caption = "PM1:00\nまた出かけます、紫いいでしょ。今日は少し遠くまで歩いて、新しい景色を見に行きます。"
    project = Project(
        cuts=[
            Cut(str(paths[0]), type="Motion", motion_type="Zoom In", duration=3.0, caption_text="フォント確認", caption_font="gothic", caption_size="medium"),
            Cut(str(paths[1]), type="Still", duration=1.5, caption_text="フォント確認", caption_font="mincho", caption_size="small"),
            Cut(str(paths[2]), type="Motion", motion_type="Pan Right", duration=3.0, caption_text="フォント確認", caption_font="pop", caption_size="large"),
            Cut(str(paths[3]), type="Still", duration=1.5, caption_text=long_caption, caption_font="rounded", caption_size="medium", caption_position="center"),
            Cut(str(paths[4]), type="Motion", motion_type="Zoom Out", duration=3.0, caption_text="もう少しだけ。", caption_font="gothic", caption_size="medium"),
            Cut(str(paths[5]), type="Still", duration=2.0, caption_text="おしまい。", caption_font="mincho", caption_size="medium"),
        ],
        style="Soft",
        caption_text="今日のまとめ。",
        caption_duration=2.0,
    )
    saved = ARTIFACTS / "phase1d.minilog"
    project.save(saved)
    project = Project.load(saved)
    assert [(cut.caption_font, cut.caption_size) for cut in project.cuts[:4]] == [
        ("gothic", "medium"),
        ("mincho", "small"),
        ("pop", "large"),
        ("rounded", "medium"),
    ]

    panels = {}
    for preset in ("gothic", "rounded", "mincho", "pop"):
        panel = build_cut_caption_panel("フォント確認", 1080, 1920, preset, "medium")
        panel.save(ARTIFACTS / f"panel-{preset}.png")
        panels[preset] = hashlib.sha256(panel.tobytes()).hexdigest()
    assert len(set(panels.values())) == 4
    long_panel = build_cut_caption_panel(long_caption, 1080, 1920, "rounded", "medium")
    long_panel.save(ARTIFACTS / "panel-long-caption.png")
    one_line_panel = build_cut_caption_panel("フォント確認", 1080, 1920, "rounded", "medium")
    assert long_panel.height > one_line_panel.height * 2
    assert long_panel.width <= round(1080 * 0.92)
    assert long_panel.height < 1920 * 0.35

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
    preview_metrics = caption_metrics(preview, "preview")
    final_metrics = caption_metrics(final, "final")
    result = {
        "duration": project.total_duration(),
        "preview_size": preview_meta.get("size"),
        "final_size": final_meta.get("size"),
        "preview_duration": preview_meta.get("duration"),
        "final_duration": final_meta.get("duration"),
        "preview_generation_seconds": round(preview_seconds, 3),
        "final_generation_seconds": round(final_seconds, 3),
        "font_panel_hashes_unique": len(set(panels.values())),
        "long_panel_size": long_panel.size,
        "preview_caption_metrics": preview_metrics,
        "final_caption_metrics": final_metrics,
    }
    (ARTIFACTS / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    assert preview_meta.get("size") == (360, 640)
    assert final_meta.get("size") == (1080, 1920)
    assert abs(preview_meta.get("duration") - final_meta.get("duration")) < 0.05
    assert preview_metrics[1]["normalized_height"] < preview_metrics[0]["normalized_height"]
    assert preview_metrics[2]["normalized_height"] > preview_metrics[0]["normalized_height"]
    assert final_metrics[1]["normalized_height"] < final_metrics[0]["normalized_height"]
    assert final_metrics[2]["normalized_height"] > final_metrics[0]["normalized_height"]
    assert preview_metrics[3]["normalized_height"] > preview_metrics[0]["normalized_height"] * 2
    for preview_value, final_value in zip(preview_metrics, final_metrics):
        assert abs(preview_value["normalized_height"] - final_value["normalized_height"]) < 0.025
    print(f"PASS: {preview}")
    print(f"PASS: {final}")


if __name__ == "__main__":
    main()
