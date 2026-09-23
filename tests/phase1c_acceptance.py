"""Generate and inspect Phase 1C BGM preview, final, loop, and no-BGM outputs."""

from __future__ import annotations

import array
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.exporter import FINAL_RENDER, PREVIEW_RENDER, export_project, find_ffmpeg
from app.models import Cut, Project
from tests.phase1b_acceptance import make_inputs


ARTIFACTS = ROOT / "output" / "phase1c-acceptance"


def make_bgm(path: Path, duration: float, frequency: int) -> None:
    command = [
        find_ffmpeg(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency={frequency}:sample_rate=48000:duration={duration}",
        "-c:a",
        "libmp3lame",
        "-q:a",
        "3",
        str(path),
    ]
    subprocess.run(command, check=True)


def metadata(path: Path) -> dict:
    reader = imageio_ffmpeg.read_frames(str(path), pix_fmt="rgb24")
    result = next(reader)
    reader.close()
    return result


def probe_text(path: Path) -> str:
    result = subprocess.run(
        [find_ffmpeg(), "-hide_banner", "-i", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stderr


def audio_rms(path: Path, at_seconds: float, sample_duration: float = 0.20) -> float:
    result = subprocess.run(
        [
            find_ffmpeg(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{at_seconds:.3f}",
            "-i",
            str(path),
            "-vn",
            "-t",
            f"{sample_duration:.3f}",
            "-ac",
            "1",
            "-ar",
            "8000",
            "-f",
            "s16le",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    samples = array.array("h")
    samples.frombytes(result.stdout[: len(result.stdout) // 2 * 2])
    if not samples:
        return 0.0
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples))


def six_cut_project(paths: list[Path], bgm: Path) -> Project:
    return Project(
        cuts=[
            Cut(str(paths[0]), type="Motion", motion_type="Zoom In", duration=3.0, caption_text="はじまり。", caption_position="bottom", caption_motion="fade"),
            Cut(str(paths[1]), type="Still", duration=1.5, caption_text="今日の一枚。", caption_position="center", caption_motion="fixed"),
            Cut(str(paths[2]), type="Motion", motion_type="Pan Right", duration=3.0, caption_text="少し移動。", caption_position="top", caption_motion="slide_up"),
            Cut(str(paths[3]), type="Still", duration=1.5),
            Cut(str(paths[4]), type="Motion", motion_type="Zoom Out", duration=3.0, caption_text="もう少しだけ。", caption_position="bottom", caption_motion="soft_zoom"),
            Cut(str(paths[5]), type="Still", duration=2.0, caption_text="おしまい。", caption_position="bottom", caption_motion="fade"),
        ],
        style="Soft",
        caption_text="今日のまとめ。",
        caption_duration=2.0,
        bgm_path=str(bgm),
        bgm_volume=0.7,
    )


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    paths = make_inputs()
    long_bgm = ARTIFACTS / "long-bgm-20s.mp3"
    short_bgm = ARTIFACTS / "short-bgm-5s.mp3"
    make_bgm(long_bgm, 20.5, 440)
    make_bgm(short_bgm, 5.0, 660)

    project = six_cut_project(paths, long_bgm)
    project_file = ARTIFACTS / "phase1c.minilog"
    project.save(project_file)
    project = Project.load(project_file)
    assert Path(project.bgm_path) == long_bgm.resolve()
    assert abs(project.bgm_volume - 0.7) < 0.001

    preview = ARTIFACTS / "preview-with-bgm.mp4"
    final = ARTIFACTS / "final-with-bgm.mp4"
    started = time.perf_counter()
    export_project(project, preview, settings=PREVIEW_RENDER)
    preview_seconds = time.perf_counter() - started
    started = time.perf_counter()
    export_project(project, final, settings=FINAL_RENDER)
    final_seconds = time.perf_counter() - started

    loop_project = Project(
        cuts=[Cut(str(paths[0]), type="Still", duration=18.0)],
        bgm_path=str(short_bgm),
        bgm_volume=0.7,
    )
    loop_output = ARTIFACTS / "loop-18s-with-5s-bgm.mp4"
    export_project(loop_project, loop_output, settings=FINAL_RENDER)

    silent_project = Project(cuts=[Cut(str(paths[1]), type="Still", duration=1.0)])
    silent_output = ARTIFACTS / "no-bgm.mp4"
    export_project(silent_project, silent_output, settings=FINAL_RENDER)
    missing_project = Project(
        cuts=[Cut(str(paths[1]), type="Still", duration=1.0)],
        bgm_path=str(ARTIFACTS / "missing.mp3"),
    )
    missing_output = ARTIFACTS / "missing-bgm-fallback.mp4"
    export_project(missing_project, missing_output, settings=PREVIEW_RENDER)

    preview_meta = metadata(preview)
    final_meta = metadata(final)
    loop_meta = metadata(loop_output)
    preview_probe = probe_text(preview)
    final_probe = probe_text(final)
    silent_probe = probe_text(silent_output)
    missing_probe = probe_text(missing_output)
    preview_rms = {
        "start": round(audio_rms(preview, 0.03), 2),
        "middle": round(audio_rms(preview, 0.70), 2),
        "end_caption": round(audio_rms(preview, 14.5), 2),
        "end": round(audio_rms(preview, 15.85), 2),
    }
    final_rms = {
        "start": round(audio_rms(final, 0.03), 2),
        "middle": round(audio_rms(final, 0.70), 2),
        "end_caption": round(audio_rms(final, 14.5), 2),
        "end": round(audio_rms(final, 15.85), 2),
    }
    loop_rms = [round(audio_rms(loop_output, at), 2) for at in (0.7, 5.2, 10.2, 15.2, 17.85)]
    result = {
        "project_duration": project.total_duration(),
        "preview_size": preview_meta.get("size"),
        "final_size": final_meta.get("size"),
        "preview_duration": preview_meta.get("duration"),
        "final_duration": final_meta.get("duration"),
        "preview_generation_seconds": round(preview_seconds, 3),
        "final_generation_seconds": round(final_seconds, 3),
        "preview_has_aac": "Audio: aac" in preview_probe,
        "final_has_aac": "Audio: aac" in final_probe,
        "preview_rms": preview_rms,
        "final_rms": final_rms,
        "loop_duration": loop_meta.get("duration"),
        "loop_rms": loop_rms,
        "no_bgm_has_audio": "Audio:" in silent_probe,
        "missing_bgm_has_audio": "Audio:" in missing_probe,
    }
    (ARTIFACTS / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    assert preview_meta.get("size") == (360, 640)
    assert final_meta.get("size") == (1080, 1920)
    assert abs(preview_meta.get("duration") - 16.0) < 0.1
    assert abs(final_meta.get("duration") - 16.0) < 0.1
    assert result["preview_has_aac"] and result["final_has_aac"]
    assert "48000 Hz, stereo" in preview_probe and "48000 Hz, stereo" in final_probe
    assert "Video: h264" in preview_probe and "Video: h264" in final_probe
    for values in (preview_rms, final_rms):
        assert 0 < values["start"] < values["middle"]
        assert values["end_caption"] > 0
        assert 0 < values["end"] < values["end_caption"]
    assert abs(loop_meta.get("duration") - 18.0) < 0.1
    assert all(value > 100 for value in loop_rms[:-1])
    assert 0 < loop_rms[-1] < loop_rms[-2]
    assert not result["no_bgm_has_audio"]
    assert not result["missing_bgm_has_audio"]
    print(f"PASS: {preview}")
    print(f"PASS: {final}")
    print(f"PASS: {loop_output}")
    print(f"PASS: {silent_output}")
    print(f"PASS: {missing_output}")


if __name__ == "__main__":
    main()
