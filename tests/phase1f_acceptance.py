"""Render and inspect Phase 1F Cut Audio timing, mix, and persistence."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.exporter import FINAL_RENDER, PREVIEW_RENDER, export_project, find_ffmpeg
from app.models import Cut, Project
from tests.phase1b_acceptance import make_inputs
from tests.phase1c_acceptance import audio_rms, make_bgm, metadata, probe_text


ARTIFACTS = ROOT / "output" / "phase1f-acceptance"


def make_wav(path: Path, duration: float, frequency: int) -> None:
    subprocess.run(
        [
            find_ffmpeg(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:sample_rate=48000:duration={duration}",
            "-ac",
            "2",
            str(path),
        ],
        check=True,
    )


def build_project(paths: list[Path], bgm: Path | None, short_audio: Path, long_audio: Path) -> Project:
    return Project(
        cuts=[
            Cut(str(paths[0]), duration=1.0, audio_path=str(short_audio), audio_volume=1.0),
            Cut(str(paths[1]), duration=1.0, audio_path=str(long_audio), audio_volume=0.5),
            Cut(str(paths[2]), duration=1.0),
        ],
        caption_text="End",
        caption_duration=0.5,
        bgm_path=str(bgm) if bgm else None,
        bgm_volume=0.35,
    )


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    paths = make_inputs()
    bgm = ARTIFACTS / "bgm-4s.mp3"
    short_audio = ARTIFACTS / "short-0.4s.wav"
    long_audio = ARTIFACTS / "long-3s.wav"
    make_bgm(bgm, 4.0, 220)
    make_wav(short_audio, 0.4, 880)
    make_wav(long_audio, 3.0, 660)

    project = build_project(paths, bgm, short_audio, long_audio)
    with tempfile.TemporaryDirectory(prefix="minilog-phase1f-") as folder:
        project_path = Path(folder) / "phase1f.minilog"
        project.save(project_path)
        restored = Project.load(project_path)
    assert Path(restored.cuts[0].audio_path) == short_audio.resolve()
    assert Path(restored.cuts[1].audio_path) == long_audio.resolve()
    assert restored.cuts[0].audio_volume == 1.0
    assert restored.cuts[1].audio_volume == 0.5

    preview = ARTIFACTS / "preview-bgm-cut-audio.mp4"
    final = ARTIFACTS / "final-bgm-cut-audio.mp4"
    export_project(restored, preview, settings=PREVIEW_RENDER)
    export_project(restored, final, settings=FINAL_RENDER)

    cut_only_project = build_project(paths, None, short_audio, long_audio)
    cut_only = ARTIFACTS / "preview-cut-audio-only.mp4"
    export_project(cut_only_project, cut_only, settings=PREVIEW_RENDER)

    missing_project = Project(
        cuts=[Cut(str(paths[0]), duration=1.0, audio_path=str(ARTIFACTS / "missing.wav"))]
    )
    missing_output = ARTIFACTS / "preview-missing-cut-audio.mp4"
    export_project(missing_project, missing_output, settings=PREVIEW_RENDER)

    preview_rms = {
        "cut1_audio": round(audio_rms(preview, 0.20), 2),
        "cut1_after_short": round(audio_rms(preview, 0.75), 2),
        "cut2_audio": round(audio_rms(preview, 1.20), 2),
        "cut3_after_trim": round(audio_rms(preview, 2.20), 2),
        "end_caption_bgm": round(audio_rms(preview, 3.20), 2),
    }
    cut_only_rms = {
        "cut1_audio": round(audio_rms(cut_only, 0.20), 2),
        "cut1_after_short": round(audio_rms(cut_only, 0.75), 2),
        "cut2_audio": round(audio_rms(cut_only, 1.20), 2),
        "cut3_after_trim": round(audio_rms(cut_only, 2.20), 2),
    }
    preview_probe = probe_text(preview)
    final_probe = probe_text(final)
    cut_only_probe = probe_text(cut_only)
    missing_probe = probe_text(missing_output)
    preview_meta = metadata(preview)
    final_meta = metadata(final)

    result = {
        "duration": restored.total_duration(),
        "preview_duration": preview_meta.get("duration"),
        "final_duration": final_meta.get("duration"),
        "preview_has_aac": "Audio: aac" in preview_probe,
        "final_has_aac": "Audio: aac" in final_probe,
        "cut_only_has_aac": "Audio: aac" in cut_only_probe,
        "missing_audio_falls_back_to_silent": "Audio:" not in missing_probe,
        "preview_rms": preview_rms,
        "cut_only_rms": cut_only_rms,
        "project_roundtrip": True,
    }
    (ARTIFACTS / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

    assert preview_meta.get("size") == (360, 640)
    assert final_meta.get("size") == (1080, 1920)
    assert abs(preview_meta.get("duration") - 3.5) < 0.1
    assert abs(final_meta.get("duration") - 3.5) < 0.1
    assert result["preview_has_aac"] and result["final_has_aac"]
    assert result["cut_only_has_aac"]
    assert result["missing_audio_falls_back_to_silent"]
    assert preview_rms["cut1_audio"] > preview_rms["cut1_after_short"] * 1.3
    assert preview_rms["cut2_audio"] > preview_rms["cut3_after_trim"] * 1.2
    assert preview_rms["end_caption_bgm"] > 0
    assert cut_only_rms["cut1_audio"] > 100
    assert cut_only_rms["cut1_after_short"] < 10
    assert cut_only_rms["cut2_audio"] > 100
    assert 0.4 < cut_only_rms["cut2_audio"] / cut_only_rms["cut1_audio"] < 0.6
    assert cut_only_rms["cut3_after_trim"] < 10
    print(f"PASS: {preview}")
    print(f"PASS: {final}")
    print(f"PASS: {cut_only}")
    print(f"PASS: {missing_output}")


if __name__ == "__main__":
    main()
