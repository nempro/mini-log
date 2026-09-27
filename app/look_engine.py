"""Shared .cube LOOK definition for still Preview and FFmpeg rendering."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageFilter


class LookError(ValueError):
    pass


# The IDs are persisted in .minilog files; labels may change independently.
PRESET_LOOKS = (
    ("warm", "暖色", "日常を柔らかく暖かく"),
    ("faded", "色あせ", "淡い日記のような色合い"),
    ("retro", "レトロ", "少し黄緑がかった懐かしい色合い"),
    ("cool", "寒色", "青白くすっきりした空気感"),
    ("film", "フィルム", "柔らかい黒と落ち着いた色合い"),
)
PRESET_IDS = frozenset(preset_id for preset_id, _label, _description in PRESET_LOOKS)
# Earlier development builds stored a generic "preset" type and one of these IDs.
LEGACY_PRESET_IDS = {"sunlit": "warm", "clear_blue": "cool", "nostalgia": "faded"}


@dataclass(frozen=True)
class CubeLut:
    size: int
    table: tuple[float, ...]
    domain_min: tuple[float, float, float]
    domain_max: tuple[float, float, float]


def preset_label(preset_id: str) -> str:
    for candidate, label, _description in PRESET_LOOKS:
        if candidate == preset_id:
            return label
    raise LookError("LOOKプリセットが不正です。")


def preset_description(preset_id: str) -> str:
    for candidate, _label, description in PRESET_LOOKS:
        if candidate == preset_id:
            return description
    raise LookError("LOOKプリセットが不正です。")


def _preset_rgb(preset_id: str, red: float, green: float, blue: float) -> tuple[float, float, float]:
    if preset_id == "warm":
        channels = (red * 1.035 + 0.014, green * 1.008 + 0.006, blue * 0.94 + 0.004)
        saturation, contrast, lift, highlight = 1.035, 1.005, 0.0, 0.015
    elif preset_id == "faded":
        channels = (red, green, blue)
        saturation, contrast, lift, highlight = 0.76, 0.84, 0.055, 0.015
    elif preset_id == "retro":
        channels = (red * 1.04 + 0.012, green * 1.018 + 0.008, blue * 0.885 + 0.010)
        saturation, contrast, lift, highlight = 0.87, 0.97, 0.025, 0.0
    elif preset_id == "cool":
        channels = (red * 0.91 + 0.004, green * 1.015 + 0.005, blue * 1.08 + 0.018)
        saturation, contrast, lift, highlight = 1.01, 1.055, 0.0, 0.0
    elif preset_id == "film":
        channels = (red * 1.012 + 0.012 * red, green * 0.992 + 0.003,
                    blue * 0.98 + 0.018 * (1 - blue))
        saturation, contrast, lift, highlight = 0.87, 0.93, 0.035, 0.02
    else:
        raise LookError("LOOKプリセットが不正です。")
    luminance = sum(weight * value for weight, value in zip((0.2126, 0.7152, 0.0722), channels))
    return tuple(
        max(0.0, min(1.0, ((luminance + (value - luminance) * saturation) - 0.5) * contrast
                     + 0.5 + lift - highlight * max(0.0, value - 0.6)))
        for value in channels
    )


@lru_cache(maxsize=len(PRESET_LOOKS))
def preset_lut(preset_id: str) -> CubeLut:
    if preset_id not in PRESET_IDS:
        raise LookError("LOOKプリセットが不正です。")
    size = 17
    table: list[float] = []
    for blue in range(size):
        for green in range(size):
            for red in range(size):
                table.extend(_preset_rgb(preset_id, red / (size - 1), green / (size - 1), blue / (size - 1)))
    return CubeLut(size, tuple(table), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))


def write_preset_cube(preset_id: str, path: Path) -> None:
    """Materialize a built-in LOOK in the export's temporary directory for FFmpeg."""
    cube = preset_lut(preset_id)
    lines = [f'TITLE "Mini Log {preset_id}"', f"LUT_3D_SIZE {cube.size}"]
    lines.extend(
        f"{cube.table[index]:.6f} {cube.table[index + 1]:.6f} {cube.table[index + 2]:.6f}"
        for index in range(0, len(cube.table), 3)
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_cube(path: str | Path) -> CubeLut:
    source = Path(path)
    if not source.is_file() or source.suffix.lower() != ".cube":
        raise LookError(".cubeファイルが見つかりません。")
    try:
        stat = source.stat()
    except OSError as exc:
        raise LookError("LUTファイルを読み取れません。") from exc
    if not 0 < stat.st_size <= 16 * 1024 * 1024:
        raise LookError("LUTファイルのサイズが不正です。")
    return _parse_cube(str(source.resolve()), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=2)
def _parse_cube(path: str, _modified: int, _bytes: int) -> CubeLut:
    size: int | None = None
    domain_min = (0.0, 0.0, 0.0)
    domain_max = (1.0, 1.0, 1.0)
    table: list[float] = []
    rows = 0
    try:
        with Path(path).open("r", encoding="utf-8-sig") as source:
            for line_number, raw in enumerate(source, start=1):
                line = raw.split("#", 1)[0].strip()
                if not line:
                    continue
                parts = line.split()
                directive = parts[0].upper()
                if directive == "TITLE":
                    if rows:
                        raise LookError(f"{line_number}行目: TITLEの位置が不正です。")
                    continue
                if directive == "LUT_3D_SIZE":
                    if size is not None or rows or len(parts) != 2:
                        raise LookError(f"{line_number}行目: LUT_3D_SIZEが不正です。")
                    try:
                        size = int(parts[1])
                    except ValueError as exc:
                        raise LookError(f"{line_number}行目: LUTサイズが数値ではありません。") from exc
                    if not 2 <= size <= 65:
                        raise LookError("対応するLUTサイズは2〜65です。")
                    continue
                if directive in {"DOMAIN_MIN", "DOMAIN_MAX", "LUT_3D_INPUT_RANGE"}:
                    if rows:
                        raise LookError(f"{line_number}行目: DOMAINの位置が不正です。")
                    expected = 2 if directive == "LUT_3D_INPUT_RANGE" else 3
                    if len(parts) != expected + 1:
                        raise LookError(f"{line_number}行目: {directive}が不正です。")
                    try:
                        values = tuple(float(value) for value in parts[1:])
                    except ValueError as exc:
                        raise LookError(f"{line_number}行目: DOMAINが数値ではありません。") from exc
                    if not all(math.isfinite(value) for value in values):
                        raise LookError(f"{line_number}行目: DOMAINに無効な値があります。")
                    if directive == "DOMAIN_MIN":
                        domain_min = values
                    elif directive == "DOMAIN_MAX":
                        domain_max = values
                    else:
                        domain_min = (values[0],) * 3
                        domain_max = (values[1],) * 3
                    continue
                if size is None or len(parts) != 3:
                    raise LookError(f"{line_number}行目: 3D LUTの構文が不正です。")
                try:
                    rgb = tuple(float(value) for value in parts)
                except ValueError as exc:
                    raise LookError(f"{line_number}行目: RGB値が数値ではありません。") from exc
                if not all(math.isfinite(value) for value in rgb):
                    raise LookError(f"{line_number}行目: RGB値が無効です。")
                table.extend(rgb)
                rows += 1
                if rows > size**3:
                    raise LookError("LUTのRGB行数が多すぎます。")
    except (OSError, UnicodeError) as exc:
        raise LookError("LUTファイルを読み取れません。") from exc
    if size is None or rows != size**3:
        raise LookError("LUTサイズとRGB行数が一致しません。")
    if any(low >= high for low, high in zip(domain_min, domain_max)):
        raise LookError("DOMAIN_MIN / DOMAIN_MAXが不正です。")
    return CubeLut(size, tuple(table), domain_min, domain_max)


def apply_still_look(image: Image.Image, cube: CubeLut, strength: float) -> Image.Image:
    strength = max(0.0, min(float(strength), 1.0))
    original = image.convert("RGB")
    if strength == 0:
        return original
    transformed = original
    if cube.domain_min != (0.0, 0.0, 0.0) or cube.domain_max != (1.0, 1.0, 1.0):
        mapped = []
        for channel, low, high in zip(original.split(), cube.domain_min, cube.domain_max):
            mapped.append(channel.point([
                round(max(0.0, min((value / 255 - low) / (high - low), 1.0)) * 255)
                for value in range(256)
            ]))
        transformed = Image.merge("RGB", tuple(mapped))
    graded = transformed.filter(ImageFilter.Color3DLUT(cube.size, cube.table))
    return graded if strength == 1 else Image.blend(original, graded, strength)


def ffmpeg_look_filter(cube_path: Path, strength: float) -> str:
    """Return a filtergraph suffix for one video stream; path must be a safe local copy."""
    escaped = str(cube_path.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    lut_filter = f"lut3d=file='{escaped}'"
    if strength >= 1:
        return f"[0:v]format=gbrp,{lut_filter},format=yuv420p[v]"
    weight = max(0.0, min(float(strength), 1.0))
    return (
        "[0:v]format=gbrp,split=2[original][lut_input];"
        f"[lut_input]{lut_filter}[graded];"
        f"[original][graded]blend=all_expr='A*{1 - weight:.4f}+B*{weight:.4f}',"
        "format=yuv420p[v]"
    )
