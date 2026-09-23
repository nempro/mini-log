"""Build size-specific Mini Log PNG frames and a multi-resolution Windows ICO."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SOURCE = ASSETS / "minilog_icon_source.png"
PNG_OUTPUT = ASSETS / "minilog_icon.png"
ICO_OUTPUT = ASSETS / "minilog.ico"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

TRANSPARENT = (0, 0, 0, 0)
DARK = (4, 74, 56, 255)
DEEP = (16, 91, 67, 255)
SAGE = (76, 151, 98, 255)
MINT = (165, 224, 156, 255)
LIGHT_MINT = (190, 238, 181, 255)
CREAM = (255, 252, 224, 255)


def _pixel_badge(draw: ImageDraw.ImageDraw, size: int, inset: int, corner: int) -> None:
    left, top = inset, inset
    right, bottom = size - 1 - inset, size - 1 - inset
    outer = [
        (left + corner, top),
        (right - corner, top),
        (right, top + corner),
        (right, bottom - corner),
        (right - corner, bottom),
        (left + corner, bottom),
        (left, bottom - corner),
        (left, top + corner),
    ]
    draw.polygon(outer, fill=DARK)
    inner_inset = inset + 1
    inner_corner = max(1, corner - 1)
    left, top = inner_inset, inner_inset
    right, bottom = size - 1 - inner_inset, size - 1 - inner_inset
    inner = [
        (left + inner_corner, top),
        (right - inner_corner, top),
        (right, top + inner_corner),
        (right, bottom - inner_corner),
        (right - inner_corner, bottom),
        (left + inner_corner, bottom),
        (left, bottom - inner_corner),
        (left, top + inner_corner),
    ]
    draw.polygon(inner, fill=LIGHT_MINT)


def _draw_phone_16() -> Image.Image:
    """16px: phone only, five opaque colors, no badge or paw."""
    image = Image.new("RGBA", (16, 16), TRANSPARENT)
    draw = ImageDraw.Draw(image)
    draw.polygon(
        [(4, 1), (11, 1), (12, 2), (12, 13), (11, 14), (4, 14), (3, 13), (3, 2)],
        fill=DARK,
    )
    draw.rectangle((4, 2, 11, 13), fill=CREAM)
    draw.rectangle((6, 3, 9, 3), fill=DARK)
    draw.rectangle((5, 5, 10, 10), fill=MINT)
    draw.polygon([(5, 9), (7, 7), (8, 8), (9, 7), (10, 8), (10, 10), (5, 10)], fill=SAGE)
    draw.rectangle((5, 10, 10, 10), fill=DEEP)
    draw.rectangle((7, 12, 8, 12), fill=DARK)
    return image


def _draw_phone_24() -> Image.Image:
    """24px: centered phone and one landscape mark, with no secondary motif."""
    image = Image.new("RGBA", (24, 24), TRANSPARENT)
    draw = ImageDraw.Draw(image)
    _pixel_badge(draw, 24, inset=1, corner=4)
    draw.polygon(
        [(8, 3), (15, 3), (16, 4), (16, 19), (15, 20), (8, 20), (7, 19), (7, 4)],
        fill=DARK,
    )
    draw.rectangle((8, 4, 15, 19), fill=CREAM)
    draw.rectangle((10, 5, 13, 5), fill=DARK)
    draw.rectangle((9, 7, 14, 16), fill=MINT)
    draw.polygon([(9, 14), (11, 11), (12, 13), (14, 12), (14, 16), (9, 16)], fill=SAGE)
    draw.rectangle((9, 15, 14, 16), fill=DEEP)
    draw.rectangle((11, 18, 12, 18), fill=DARK)
    return image


def _draw_phone_32() -> Image.Image:
    """32px: simplified badge, phone landscape, and one readable paw."""
    image = Image.new("RGBA", (32, 32), TRANSPARENT)
    draw = ImageDraw.Draw(image)
    _pixel_badge(draw, 32, inset=1, corner=5)
    draw.polygon(
        [(6, 3), (18, 3), (20, 5), (20, 27), (18, 29), (6, 29), (4, 27), (4, 5)],
        fill=DARK,
    )
    draw.rectangle((6, 5, 18, 27), fill=CREAM)
    draw.rectangle((9, 6, 15, 7), fill=DARK)
    draw.rectangle((7, 9, 17, 23), fill=MINT)
    draw.polygon([(7, 20), (10, 16), (13, 19), (15, 17), (17, 19), (17, 23), (7, 23)], fill=SAGE)
    draw.polygon([(7, 22), (11, 19), (14, 22), (17, 20), (17, 23), (7, 23)], fill=DEEP)
    draw.rectangle((11, 25, 14, 26), fill=DARK)
    draw.rectangle((24, 18, 27, 21), fill=DARK)
    draw.rectangle((22, 15, 23, 16), fill=DARK)
    draw.rectangle((25, 13, 26, 14), fill=DARK)
    draw.rectangle((28, 15, 29, 16), fill=DARK)
    return image


def _prepare_large_mark(source: Image.Image, size: int) -> Image.Image:
    alpha = source.getchannel("A").point(lambda value: 255 if value >= 96 else 0)
    source = source.copy()
    source.putalpha(alpha)
    bounds = alpha.getbbox()
    if bounds is None:
        raise ValueError("Icon source is fully transparent")
    mark = source.crop(bounds)
    mark_size = size - max(4, size // 8)
    scale = min(mark_size / mark.width, mark_size / mark.height)
    resized = mark.resize(
        (max(1, round(mark.width * scale)), max(1, round(mark.height * scale))),
        Image.Resampling.NEAREST,
    )
    resized = resized.quantize(colors=16, method=Image.Quantize.FASTOCTREE).convert("RGBA")
    resized.putalpha(resized.getchannel("A").point(lambda value: 255 if value >= 128 else 0))
    frame = Image.new("RGBA", (size, size), TRANSPARENT)
    frame.alpha_composite(resized, ((size - resized.width) // 2, (size - resized.height) // 2))
    return frame


def build_frames(source_path: Path = SOURCE) -> dict[int, Image.Image]:
    with Image.open(source_path) as source_image:
        source = source_image.convert("RGBA")
    frame64 = _prepare_large_mark(source, 64)
    return {
        16: _draw_phone_16(),
        24: _draw_phone_24(),
        32: _draw_phone_32(),
        48: _prepare_large_mark(source, 48),
        64: frame64,
        128: frame64.resize((128, 128), Image.Resampling.NEAREST),
        256: frame64.resize((256, 256), Image.Resampling.NEAREST),
    }


def build_icon(source_path: Path = SOURCE) -> tuple[Path, Path]:
    frames = build_frames(source_path)
    ASSETS.mkdir(parents=True, exist_ok=True)
    for size in ICO_SIZES:
        frames[size].save(ASSETS / f"minilog_icon_{size}.png", "PNG", optimize=True)
    frames[256].save(PNG_OUTPUT, "PNG", optimize=True)
    frames[256].save(
        ICO_OUTPUT,
        "ICO",
        sizes=[(size, size) for size in ICO_SIZES],
        append_images=[frames[size] for size in ICO_SIZES[:-1]],
    )
    return PNG_OUTPUT, ICO_OUTPUT


if __name__ == "__main__":
    png, ico = build_icon()
    print(png)
    print(ico)
