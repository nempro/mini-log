"""Render all four Cut Caption styles through Preview and final MP4."""

from __future__ import annotations

import io
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.exporter import FINAL_RENDER, PREVIEW_RENDER, export_project, find_ffmpeg
from app.models import Cut, Project


def frame_at(video: Path, seconds: float) -> Image.Image:
    result = subprocess.run(
        [find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-ss", f"{seconds:.2f}",
         "-i", str(video), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    )
    with Image.open(io.BytesIO(result.stdout)) as opened:
        return opened.convert("RGB")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="mini-log-caption-styles-") as temporary:
        folder = Path(temporary)
        image = folder / "still.png"
        Image.new("RGB", (360, 640), "#9ac2aa").save(image)
        styles = ("band", "soft_band", "outline", "shadow")
        project = Project(
            cuts=[Cut(str(image), duration=0.6, caption_text="今日の記録。", caption_style=style)
                  for style in styles],
            caption_text="おしまい。", caption_duration=0.5,
        )
        saved = folder / "styles.minilog"
        project.save(saved)
        restored = Project.load(saved)
        assert [cut.caption_style for cut in restored.cuts] == list(styles)
        for name, settings in (("preview", PREVIEW_RENDER), ("final", FINAL_RENDER)):
            video = folder / f"{name}.mp4"
            export_project(restored, video, settings=settings)
            frames = [frame_at(video, index * 0.6 + 0.3) for index in range(4)]
            assert len({frame.tobytes() for frame in frames}) == 4, name
            ending = frame_at(video, 2.65)
            assert ending.getpixel((0, 0))[0] < 20  # End Caption stays black
    print("Caption Style acceptance: PASS (4 styles, save/load, Preview and final MP4)")


if __name__ == "__main__":
    main()
