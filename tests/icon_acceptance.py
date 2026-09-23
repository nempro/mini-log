"""Inspect the dedicated small icon frames and their exact ICO payloads."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.resources import ICON_ICO


ASSETS = ROOT / "assets"
ARTIFACTS = ROOT / "output" / "icon-small-acceptance"
SMALL_SIZES = (16, 24, 32)


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    previews = []
    results = {}
    with Image.open(ASSETS / "minilog_icon_64.png") as large_image:
        frame64 = large_image.convert("RGBA")
    with Image.open(ICON_ICO) as ico:
        assert set(ico.ico.sizes()) == {(size, size) for size in (16, 24, 32, 48, 64, 128, 256)}
        for size in SMALL_SIZES:
            with Image.open(ASSETS / f"minilog_icon_{size}.png") as image:
                frame = image.convert("RGBA")
            ico_frame = ico.ico.getimage((size, size)).convert("RGBA")
            assert ImageChops.difference(frame, ico_frame).getbbox() is None
            alpha_values = {value for value, count in enumerate(frame.getchannel("A").histogram()) if count}
            assert alpha_values == {0, 255}
            automatic = frame64.resize((size, size), Image.Resampling.NEAREST)
            assert ImageChops.difference(frame, automatic).getbbox() is not None
            preview = frame.resize((256, 256), Image.Resampling.NEAREST)
            preview.save(ARTIFACTS / f"icon-{size}-nearest.png")
            previews.append((size, preview))
            results[str(size)] = {
                "colors": len(frame.getcolors(size * size)),
                "opaque_bbox": list(frame.getchannel("A").getbbox()),
                "alpha_values": sorted(alpha_values),
                "different_from_automatic_resize": True,
                "matches_ico_frame": True,
            }

    sheet = Image.new("RGBA", (len(previews) * 280, 310), (247, 247, 244, 255))
    draw = ImageDraw.Draw(sheet)
    for index, (size, preview) in enumerate(previews):
        x = index * 280 + 12
        sheet.alpha_composite(preview, (x, 38))
        draw.text((x, 12), f"{size} x {size} dedicated", fill=(25, 25, 23, 255))
    sheet.save(ARTIFACTS / "small-size-contact-sheet.png")
    (ARTIFACTS / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("PASS", json.dumps(results, ensure_ascii=True))


if __name__ == "__main__":
    main()
