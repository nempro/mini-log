"""Small end-to-end export check for Phase 2B transitions and audio timing."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.exporter import PREVIEW_RENDER, RenderSettings, export_project, find_ffmpeg
from app.models import Cut, Project


def make_media(folder: Path) -> tuple[list[Path], Path, Path]:
    images: list[Path] = []
    for index, color in enumerate(((70, 150, 100), (70, 115, 190), (180, 115, 70))):
        path = folder / f"still-{index}.png"
        Image.new("RGB", (160, 90), color).save(path)
        images.append(path)

    ffmpeg = find_ffmpeg()
    video = folder / "source-video.mp4"
    subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=purple:s=160x90:r=10:d=1",
            "-f", "lavfi", "-i", "sine=frequency=660:sample_rate=48000:duration=1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(video),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    bgm = folder / "bgm.wav"
    subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=1.2",
            "-ac", "2", str(bgm),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    return images, video, bgm


def verify_output(path: Path, expected_duration: float) -> None:
    ffmpeg = find_ffmpeg()
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    details = result.stderr
    assert "Video: h264" in details, details
    assert "Audio: aac" in details, details
    import re

    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", details)
    assert match, details
    actual_duration = int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))
    assert abs(actual_duration - expected_duration) <= 0.15, (actual_duration, expected_duration)


def verify_dip_to_black(path: Path) -> None:
    ffmpeg = find_ffmpeg()
    frame = subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", "2.7", "-i", str(path),
            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    assert frame and max(frame) <= 8, max(frame) if frame else "no frame"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="minilog-phase2b-") as temporary:
        folder = Path(temporary)
        images, video, bgm = make_media(folder)
        project = Project(
            cuts=[
                Cut(str(images[0]), duration=1.0, transition_type="crossfade", transition_duration=0.4, caption_text="はじまり。"),
                Cut(str(images[1]), type="Motion", duration=1.0, transition_type="fade", transition_duration=0.4, caption_text="ゆっくり。"),
                Cut(str(video), type="Video", duration=1.0, media_duration=1.0, transition_type="dip_black", transition_duration=0.6, caption_text="動画も。"),
                Cut(str(images[2]), duration=1.0),
            ],
            caption_text="今日のまとめ。",
            caption_duration=0.4,
            bgm_path=str(bgm),
        )
        project.cuts[1].normalize()
        project.cuts[2].normalize()
        expected_duration = project.total_duration()
        assert abs(project.video_duration() - 3.8) < 0.001
        assert abs(expected_duration - 4.2) < 0.001

        preview = folder / "preview.mp4"
        final = folder / "final.mp4"
        final_settings = RenderSettings(160, 284, 10, 2, "ultrafast", 30, False)
        export_project(project, preview, settings=PREVIEW_RENDER)
        export_project(project, final, settings=final_settings)
        verify_output(preview, expected_duration)
        verify_output(final, expected_duration)
        verify_dip_to_black(preview)
        verify_dip_to_black(final)

        saved = folder / "roundtrip.minilog"
        project.save(saved)
        restored = Project.load(saved)
        assert [cut.transition_type for cut in restored.cuts] == ["crossfade", "fade", "dip_black", "cut"]
        assert [cut.transition_duration for cut in restored.cuts] == [0.4, 0.4, 0.6, 0.4]
        assert abs(restored.total_duration() - expected_duration) < 0.001

    print("Phase 2B acceptance: PASS (Cut/Fade/Crossfade/Dip, video cut, captions, BGM, Preview/Export, project round-trip)")


if __name__ == "__main__":
    main()
