"""Acceptance check for the packaged Mini Log release and bundled FFmpeg."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.version import __version__


RELEASE = ROOT / "release" / f"MiniLog-{__version__}"
EXE = RELEASE / "MiniLog.exe"
FFMPEG = RELEASE / "ffmpeg" / "ffmpeg.exe"
ARCHIVE = ROOT / "release" / f"MiniLog-{__version__}-windows.zip"
ARTIFACTS = ROOT / "output" / "release-prep-a"


def _probe(path: Path) -> str:
    result = subprocess.run(
        [str(FFMPEG), "-hide_banner", "-i", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stderr


def _make_audio(path: Path, duration: float, frequency: int, mp3: bool = False) -> None:
    command = [
        str(FFMPEG),
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


def _release_manifest() -> dict[str, int]:
    return {
        str(path.relative_to(RELEASE)): path.stat().st_size
        for path in RELEASE.rglob("*")
        if path.is_file()
    }


def main() -> None:
    assert EXE.is_file()
    assert FFMPEG.is_file()
    assert ARCHIVE.is_file()
    assert (RELEASE / "README.txt").is_file()
    assert (RELEASE / "THIRD_PARTY_NOTICES.txt").is_file()
    assert (RELEASE / "licenses" / "ffmpeg" / "COPYING.GPLv3.txt").is_file()
    assert (RELEASE / "licenses" / "ffmpeg" / "BUILD_INFO.txt").is_file()
    assert (RELEASE / "_internal" / "assets" / "minilog.ico").is_file()
    assert (RELEASE / "_internal" / "assets" / "minilog_icon.png").is_file()
    assert (RELEASE / "_internal" / "tkinterdnd2" / "tkdnd" / "win-x64").is_dir()
    assert not any((RELEASE / name).exists() for name in ("tests", "output", "__pycache__", ".git"))

    before = _release_manifest()
    original_executable = sys.executable
    original_frozen = getattr(sys, "frozen", None)
    original_path = os.environ.get("PATH")
    original_override = os.environ.pop("MINILOG_FFMPEG", None)
    sys.executable = str(EXE)
    sys.frozen = True
    os.environ["PATH"] = ""
    try:
        from app.exporter import FINAL_RENDER, PREVIEW_RENDER, export_project, find_ffmpeg
        from app.models import Cut, Project
        from tests.phase1b_acceptance import make_inputs

        assert Path(find_ffmpeg()).resolve() == FFMPEG.resolve()
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        inputs = make_inputs()
        bgm = ARTIFACTS / "bundled-bgm.mp3"
        cut_audio = ARTIFACTS / "bundled-cut-audio.wav"
        _make_audio(bgm, 2.0, 330, mp3=True)
        _make_audio(cut_audio, 0.7, 660)

        project = Project(
            cuts=[
                Cut(
                    str(inputs[0]),
                    type="Motion",
                    duration=0.6,
                    motion_type="Zoom In",
                    caption_text="EXE Preview",
                    audio_path=str(cut_audio),
                    audio_volume=0.6,
                ),
                Cut(str(inputs[1]), duration=0.6, caption_text="Export"),
            ],
            style="Soft",
            caption_text="Mini Log 0.1.0",
            caption_duration=0.4,
            bgm_path=str(bgm),
            bgm_volume=0.6,
        )
        with tempfile.TemporaryDirectory(prefix="mini-log-release-project-") as folder:
            project_path = Path(folder) / "release.minilog"
            project.save(project_path)
            restored = Project.load(project_path)
        assert restored.to_dict() == project.to_dict()

        preview = ARTIFACTS / "bundled-preview.mp4"
        final = ARTIFACTS / "bundled-final.mp4"
        export_project(restored, preview, settings=PREVIEW_RENDER)
        export_project(restored, final, settings=FINAL_RENDER)
        preview_probe = _probe(preview)
        final_probe = _probe(final)
        assert "Video: h264" in preview_probe and "360x640" in preview_probe
        assert "Video: h264" in final_probe and "1080x1920" in final_probe
        assert "Audio: aac" in preview_probe and "Audio: aac" in final_probe
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

    after = _release_manifest()
    assert before == after
    result = {
        "version": __version__,
        "executable": str(EXE),
        "bundled_ffmpeg": str(FFMPEG),
        "path_disabled": True,
        "preview": str(preview),
        "preview_h264_aac_360x640": True,
        "final": str(final),
        "final_h264_aac_1080x1920": True,
        "project_roundtrip": True,
        "release_folder_unchanged": True,
        "release_size_bytes": sum(before.values()),
        "zip": str(ARCHIVE),
    }
    (ARTIFACTS / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("PASS")


if __name__ == "__main__":
    main()
