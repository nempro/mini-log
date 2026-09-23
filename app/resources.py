from __future__ import annotations

import sys
from pathlib import Path


def resource_path(relative_path: str | Path) -> Path:
    """Resolve assets from source or PyInstaller's bundled data directory."""
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return bundle_root / Path(relative_path)


def application_path(relative_path: str | Path) -> Path:
    """Resolve files shipped beside the executable, such as bundled FFmpeg."""
    if getattr(sys, "frozen", False):
        application_root = Path(sys.executable).resolve().parent
    else:
        application_root = Path(__file__).resolve().parents[1]
    return application_root / Path(relative_path)


def bundled_tool_candidates(filename: str) -> tuple[Path, ...]:
    """Return external and PyInstaller-internal locations for a bundled tool."""
    candidates = (
        application_path(Path("ffmpeg") / filename),
        resource_path(Path("ffmpeg") / filename),
    )
    return tuple(dict.fromkeys(candidates))


ICON_PNG = resource_path("assets/minilog_icon.png")
ICON_ICO = resource_path("assets/minilog.ico")
