"""Build the distributable Windows version of Mini Log.

Usage from the project root:
    python scripts/build_windows.py
"""

from __future__ import annotations

import os
import shutil
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT / "build" / "pyinstaller"

sys.path.insert(0, str(ROOT))

from app.version import __version__  # noqa: E402
from scripts.release_documents import (  # noqa: E402
    FFMPEG_SHA256,
    sha256sum,
    write_distribution_documents,
)


def _numeric_version(version: str) -> tuple[int, int, int, int]:
    numbers: list[int] = []
    for part in version.split("-")[0].split("."):
        digits = "".join(character for character in part if character.isdigit())
        numbers.append(int(digits or 0))
    return tuple((numbers + [0, 0, 0, 0])[:4])  # type: ignore[return-value]


def _find_ffmpeg_source() -> Path:
    override = os.environ.get("MINILOG_BUILD_FFMPEG")
    if override:
        candidate = Path(override).expanduser().resolve()
        if candidate.is_file():
            if sha256sum(candidate) == FFMPEG_SHA256:
                return candidate
            raise SystemExit(
                "Mini Log 0.1.0は検証済みのFFmpeg 7.1 binaryだけを同梱できます。"
            )
        raise SystemExit(f"MINILOG_BUILD_FFMPEGが見つかりません: {candidate}")

    try:
        import imageio_ffmpeg

        candidate = Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve()
        if candidate.is_file() and sha256sum(candidate) == FFMPEG_SHA256:
            return candidate
    except (ImportError, RuntimeError):
        pass

    executable = shutil.which("ffmpeg")
    if executable:
        candidate = Path(executable).resolve()
        if sha256sum(candidate) == FFMPEG_SHA256:
            return candidate
    raise SystemExit(
        "検証済みのFFmpeg 7.1 binaryが見つかりません。requirements.txtをインストールするか、"
        "MINILOG_BUILD_FFMPEGへ検証済みbinaryを指定してください。"
    )


def _write_version_file(path: Path) -> None:
    file_version = _numeric_version(__version__)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={file_version},
    prodvers={file_version},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('041104B0', [
        StringStruct('FileDescription', 'Mini Log — Photo Vlog Maker'),
        StringStruct('FileVersion', '{__version__}'),
        StringStruct('InternalName', 'MiniLog'),
        StringStruct('OriginalFilename', 'MiniLog.exe'),
        StringStruct('ProductName', 'Mini Log'),
        StringStruct('ProductVersion', '{__version__}')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1041, 1200])])
  ]
)
""",
        encoding="utf-8",
    )


def _safe_replace_directory(source: Path, target: Path) -> None:
    release_root = (ROOT / "release").resolve()
    resolved_target = target.resolve()
    if resolved_target.parent != release_root or not resolved_target.name.startswith("MiniLog-"):
        raise RuntimeError(f"安全でない配布先です: {resolved_target}")
    if resolved_target.exists():
        shutil.rmtree(resolved_target)
    shutil.copytree(source, resolved_target)


def _clean_build_root() -> None:
    resolved = BUILD_ROOT.resolve()
    expected_parent = (ROOT / "build").resolve()
    if resolved.parent != expected_parent or resolved.name != "pyinstaller":
        raise RuntimeError(f"安全でないビルド作業先です: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)


def _safe_replace_zip(path: Path) -> None:
    release_root = (ROOT / "release").resolve()
    resolved = path.resolve()
    if resolved.parent != release_root or not resolved.name.startswith("MiniLog-"):
        raise RuntimeError(f"安全でないZIP出力先です: {resolved}")
    if resolved.exists():
        resolved.unlink()


def _create_release_zip(release: Path) -> Path:
    archive = release.parent / f"MiniLog-{__version__}-windows.zip"
    _safe_replace_zip(archive)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in sorted(release.rglob("*")):
            if path.is_file():
                output.write(path, path.relative_to(release.parent))
    return archive


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Windows版ビルドはWindows上で実行してください。")
    try:
        import PyInstaller.__main__
    except ImportError as exc:
        raise SystemExit(
            "PyInstallerが必要です。python -m pip install -r requirements-build.txt を実行してください。"
        ) from exc

    _clean_build_root()
    icon = ROOT / "assets" / "minilog.ico"
    icon_png = ROOT / "assets" / "minilog_icon.png"
    licenses = ROOT / "licenses"
    for required in (icon, icon_png, licenses / "ffmpeg" / "COPYING.GPLv3.txt"):
        if not required.is_file():
            raise SystemExit(f"必要なAssetが見つかりません: {required}")

    ffmpeg_source = _find_ffmpeg_source()
    version_file = BUILD_ROOT / "version_info.txt"
    dist_root = BUILD_ROOT / "dist"
    _write_version_file(version_file)

    PyInstaller.__main__.run(
        [
            str(ROOT / "main.py"),
            "--name=MiniLog",
            "--onedir",
            "--windowed",
            "--noconfirm",
            "--clean",
            f"--icon={icon}",
            f"--version-file={version_file}",
            f"--distpath={dist_root}",
            f"--workpath={BUILD_ROOT / 'work'}",
            f"--specpath={BUILD_ROOT / 'spec'}",
            f"--paths={ROOT}",
            f"--add-data={icon}{os.pathsep}assets",
            f"--add-data={icon_png}{os.pathsep}assets",
            "--exclude-module=imageio_ffmpeg",
            "--exclude-module=tests",
        ]
    )

    built = dist_root / "MiniLog"
    if not (built / "MiniLog.exe").is_file():
        raise SystemExit("PyInstallerの出力にMiniLog.exeがありません。")

    release = ROOT / "release" / f"MiniLog-{__version__}"
    _safe_replace_directory(built, release)
    ffmpeg_target = release / "ffmpeg" / "ffmpeg.exe"
    ffmpeg_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ffmpeg_source, ffmpeg_target)
    (release / "VERSION.txt").write_text(f"Mini Log {__version__}\n", encoding="utf-8")
    shutil.copytree(licenses, release / "licenses")
    write_distribution_documents(release)
    archive = _create_release_zip(release)

    size = sum(path.stat().st_size for path in release.rglob("*") if path.is_file())
    print(f"Built: {release}")
    print(f"Version: {__version__}")
    print(f"Bundled FFmpeg: {ffmpeg_target}")
    print(f"Release ZIP: {archive}")
    print(f"Size: {size / (1024 * 1024):.1f} MiB")


if __name__ == "__main__":
    main()
