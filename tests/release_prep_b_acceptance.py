"""Release Prep B checks for the final ZIP and its extracted runtime."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.version import __version__


RELEASE_NAME = f"MiniLog-{__version__}"
ARCHIVE = ROOT / "release" / f"{RELEASE_NAME}-windows.zip"
ARTIFACTS = ROOT / "output" / "release-prep-b"


def _probe(ffmpeg: Path, path: Path) -> str:
    result = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-i", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stderr


def _decode_all(ffmpeg: Path, path: Path) -> None:
    subprocess.run(
        [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-i", str(path), "-f", "null", "-"],
        check=True,
    )


def _make_audio(ffmpeg: Path, path: Path, duration: float, frequency: int, mp3: bool = False) -> None:
    command = [
        str(ffmpeg),
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
    ]
    if mp3:
        command.extend(["-c:a", "libmp3lame", "-q:a", "3"])
    command.append(str(path))
    subprocess.run(command, check=True)


def main() -> None:
    assert ARCHIVE.is_file(), f"Release ZIPがありません: {ARCHIVE}"
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="mini-log-release-zip-") as folder:
        extract_root = Path(folder)
        with zipfile.ZipFile(ARCHIVE) as archive:
            names = archive.namelist()
            assert f"{RELEASE_NAME}/MiniLog.exe" in names
            assert f"{RELEASE_NAME}/README.txt" in names
            assert f"{RELEASE_NAME}/THIRD_PARTY_NOTICES.txt" in names
            assert f"{RELEASE_NAME}/licenses/ffmpeg/COPYING.GPLv3.txt" in names
            assert f"{RELEASE_NAME}/licenses/ffmpeg/BUILD_INFO.txt" in names
            assert not any("/__pycache__/" in name or "/tests/" in name for name in names)
            archive.extractall(extract_root)

        release = extract_root / RELEASE_NAME
        exe = release / "MiniLog.exe"
        ffmpeg = release / "ffmpeg" / "ffmpeg.exe"
        assert exe.is_file() and ffmpeg.is_file()

        original_executable = sys.executable
        original_frozen = getattr(sys, "frozen", None)
        original_path = os.environ.get("PATH")
        original_override = os.environ.pop("MINILOG_FFMPEG", None)
        sys.executable = str(exe)
        sys.frozen = True
        os.environ["PATH"] = ""
        try:
            from app.exporter import FINAL_RENDER, export_project, find_ffmpeg
            from app.models import Cut, Project
            from tests.phase1b_acceptance import make_inputs

            assert Path(find_ffmpeg()).resolve() == ffmpeg.resolve()
            inputs = make_inputs()
            bgm = ARTIFACTS / "release-candidate-bgm.mp3"
            cut_audio = ARTIFACTS / "release-candidate-cut-audio.wav"
            _make_audio(ffmpeg, bgm, 2.0, 330, mp3=True)
            _make_audio(ffmpeg, cut_audio, 0.8, 660)
            project = Project(
                cuts=[
                    Cut(str(inputs[0]), type="Motion", duration=3.0, motion_type="Zoom In", caption_text="はじまり。", caption_position="bottom", caption_motion="fade"),
                    Cut(str(inputs[1]), duration=2.0, caption_text="今日の一枚。", caption_position="center", caption_motion="fixed"),
                    Cut(str(inputs[2]), type="Motion", duration=3.0, motion_type="Pan Right", caption_text="少し移動。", caption_position="top", caption_motion="slide_up"),
                    Cut(str(inputs[3]), duration=2.0),
                    Cut(str(inputs[4]), type="Motion", duration=3.0, motion_type="Zoom Out", caption_text="もう少しだけ。", caption_position="bottom", caption_motion="soft_zoom"),
                    Cut(str(inputs[5]), duration=2.0, caption_text="おしまい。", caption_position="bottom", caption_motion="fade", audio_path=str(cut_audio), audio_volume=0.6),
                ],
                style="Soft",
                caption_text="今日のまとめ。",
                caption_duration=2.0,
                bgm_path=str(bgm),
                bgm_volume=0.6,
            )
            project_path = ARTIFACTS / "release-candidate.minilog"
            project.save(project_path)
            restored = Project.load(project_path)
            assert restored.to_dict() == project.to_dict()

            final = ARTIFACTS / "mini-log-0.1.0-phone-check.mp4"
            export_project(restored, final, settings=FINAL_RENDER)
            probe = _probe(ffmpeg, final)
            assert "Video: h264" in probe and "1080x1920" in probe and "30 fps" in probe
            assert "yuv420p" in probe and "Audio: aac" in probe and "48000 Hz, stereo" in probe
            _decode_all(ffmpeg, final)

            silent = Project(cuts=[Cut(str(inputs[0]), duration=0.6)])
            silent_output = ARTIFACTS / "mini-log-0.1.0-silent-check.mp4"
            export_project(silent, silent_output, settings=FINAL_RENDER)
            _decode_all(ffmpeg, silent_output)
        finally:
            sys.executable = original_executable
            if original_frozen is None:
                delattr(sys, "frozen")
            else:
                sys.frozen = original_frozen
            if original_path is None:
                os.environ.pop("PATH", None)
            else:
                os.environ["PATH"] = original_path
            if original_override is not None:
                os.environ["MINILOG_FFMPEG"] = original_override

    result = {
        "version": __version__,
        "zip": str(ARCHIVE),
        "zip_extract_checked": True,
        "bundled_ffmpeg_only": True,
        "project_roundtrip": True,
        "phone_check_mp4": str(ARTIFACTS / "mini-log-0.1.0-phone-check.mp4"),
        "h264_aac_1080x1920_30fps_yuv420p": True,
        "silent_mp4_decode": True,
    }
    (ARTIFACTS / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("PASS")


if __name__ == "__main__":
    main()
