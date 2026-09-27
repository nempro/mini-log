"""Generate a short mixed still/video project and verify Preview / export audio."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.exporter import FINAL_RENDER, PREVIEW_RENDER, export_project, find_ffmpeg, probe_video
from app.models import Project


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def stream_info(path: Path) -> str:
    result = subprocess.run(
        [find_ffmpeg(), "-hide_banner", "-i", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stderr


def main() -> None:
    ffmpeg = find_ffmpeg()
    with tempfile.TemporaryDirectory(prefix="minilog-phase2a-") as temporary:
        folder = Path(temporary)
        clip = folder / "clip-with-audio.mp4"
        bgm = folder / "bgm.wav"
        cut_audio = folder / "cut-audio.wav"
        image_a = folder / "still-a.png"
        image_b = folder / "still-b.png"
        Image.new("RGB", (640, 480), (40, 115, 90)).save(image_a)
        image = Image.new("RGB", (640, 480), (45, 80, 135))
        ImageDraw.Draw(image).ellipse((180, 100, 460, 380), fill=(210, 170, 90))
        image.save(image_b)

        run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=480x270:rate=30:duration=2.5",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=48000:duration=2.5",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                str(clip),
            ]
        )
        for target, frequency, duration in ((bgm, 220, 1.2), (cut_audio, 660, 0.8)):
            run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    f"sine=frequency={frequency}:sample_rate=48000:duration={duration}",
                    str(target),
                ]
            )

        duration, has_audio = probe_video(clip)
        assert 2.45 <= duration <= 2.55 and has_audio, (duration, has_audio)
        project = Project()
        image_count, video_count, errors = project.add_materials(
            [str(image_a), str(clip), str(image_b)], probe_video
        )
        assert (image_count, video_count, errors) == (2, 1, [])
        assert [cut.type for cut in project.cuts] == ["Still", "Video", "Still"]
        video_cut = project.cuts[1]
        video_cut.duration = 1.75
        video_cut.caption_text = "動画カット"
        video_cut.caption_motion = "fade"
        video_cut.use_source_audio = True
        video_cut.source_audio_volume = 0.55
        project.cuts[0].duration = 0.75
        project.cuts[0].audio_path = str(cut_audio)
        project.cuts[0].audio_volume = 0.45
        project.cuts[2].duration = 0.75
        project.caption_text = "おしまい"
        project.caption_duration = 0.5
        project.bgm_path = str(bgm)
        project.bgm_volume = 0.25
        assert abs(project.total_duration() - 3.75) < 0.001
        assert project.cut_start_time(1) == 0.75
        project_file = folder / "mixed.minilog"
        project.save(project_file)
        project = Project.load(project_file)
        assert project.cuts[1].type == "Video"
        assert project.cuts[1].source_has_audio and project.cuts[1].use_source_audio
        assert project.cuts[1].caption_text == "動画カット"
        assert abs(project.cuts[1].source_audio_volume - 0.55) < 0.001

        preview = folder / "preview.mp4"
        final = folder / "final.mp4"
        export_project(project, preview, settings=PREVIEW_RENDER)
        export_project(project, final, settings=FINAL_RENDER)
        preview_info = stream_info(preview)
        final_info = stream_info(final)
        assert "Video: h264" in preview_info and "480x360" in preview_info
        assert "Audio: aac" in preview_info and "Audio: aac" in final_info
        assert "Video: h264" in final_info and "1440x1080" in final_info
        assert "30 fps" in final_info

        silent_project = Project.from_dict(
            {
                "cuts": [
                    {
                        **video_cut.__dict__,
                        "duration": 3.5,
                        "caption_text": "",
                        "use_source_audio": False,
                    }
                ]
            }
        )
        silent_project.bgm_path = None
        silent_project.caption_text = ""
        silent = folder / "source-audio-off.mp4"
        export_project(silent_project, silent, settings=PREVIEW_RENDER)
        silent_info = stream_info(silent)
        assert "Video: h264" in silent_info and "Audio:" not in silent_info
        assert abs(silent_project.total_duration() - duration) < 0.08

        missing_project = Project.from_dict(
            {"cuts": [{"source_path": str(folder / "missing.mov"), "type": "Video", "media_duration": 1.0}]}
        )
        assert "動画ファイルが見つかりません" in "\n".join(missing_project.validate_for_export())

    print("Phase 2A media acceptance: PASS (mixed cuts, Preview/Export, mixed audio, source audio OFF)")


if __name__ == "__main__":
    main()
