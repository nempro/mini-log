import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import ImageFont

from app.exporter import (
    HEIGHT,
    MOTION_SCALE,
    PREVIEW_RENDER,
    WIDTH,
    _caption_layout,
    _cut_caption_lines,
    _font_path,
    build_cut_caption_filter,
    build_cut_caption_panel,
    build_cut_audio_filter,
    build_bgm_filter,
    build_video_filter,
    cut_caption_y,
    find_ffmpeg,
)
from app.models import Cut


class ExporterTests(unittest.TestCase):
    def test_ffmpeg_is_available(self):
        self.assertTrue(find_ffmpeg())

    def test_bundled_ffmpeg_has_highest_priority(self):
        with tempfile.TemporaryDirectory() as folder:
            bundled = Path(folder) / "ffmpeg.exe"
            bundled.touch()
            with (
                patch("app.exporter.bundled_tool_candidates", return_value=(bundled,)),
                patch.dict(os.environ, {"MINILOG_FFMPEG": str(Path(folder) / "override.exe")}),
                patch("app.exporter.shutil.which", return_value=str(Path(folder) / "path-ffmpeg.exe")),
            ):
                self.assertEqual(find_ffmpeg(), str(bundled))

    def test_still_filter_fills_frame(self):
        value = build_video_filter(Cut("x.jpg"), "Soft", 45)
        self.assertIn(f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase", value)
        self.assertIn(f"crop={WIDTH}:{HEIGHT}", value)
        self.assertNotIn("zoompan", value)

    def test_all_motion_filters_use_zoompan(self):
        for motion in ("Zoom In", "Zoom Out", "Pan Left", "Pan Right"):
            cut = Cut("x.jpg", type="Motion", motion_type=motion, duration=3.0)
            value = build_video_filter(cut, "Natural", 90)
            self.assertIn("zoompan", value)
            self.assertIn(f"s={WIDTH * MOTION_SCALE}x{HEIGHT * MOTION_SCALE}", value)
            self.assertIn(f"scale={WIDTH}:{HEIGHT}:flags=lanczos", value)
            self.assertIn("(3-2*", value)

    def test_long_caption_is_wrapped_to_fit(self):
        text, size = _caption_layout("これはかなり長いキャプションです。" * 20, _font_path())
        self.assertIn("\n", text)
        self.assertGreaterEqual(size, 14)

    def test_preview_filter_uses_fast_low_resolution_settings(self):
        cut = Cut("x.jpg", type="Motion", motion_type="Pan Right", duration=3.0)
        value = build_video_filter(cut, "Film", 90, PREVIEW_RENDER)
        self.assertIn("scale=720:1280", value)
        self.assertIn("scale=360:640:flags=lanczos", value)
        self.assertIn("noise=alls=1.2", value)

    def test_cut_caption_panel_wraps_and_has_readable_artwork(self):
        panel = build_cut_caption_panel("新しい機能を試してみた。" * 8, 360, 640)
        self.assertLessEqual(panel.width, 360)
        self.assertGreater(panel.height, 20)
        self.assertGreater(panel.getchannel("A").getextrema()[1], 0)

    def test_cut_caption_presets_change_font_and_size(self):
        gothic = _font_path("gothic")
        mincho = _font_path("mincho")
        pop = _font_path("pop")
        self.assertNotEqual(gothic.name.lower(), mincho.name.lower())
        self.assertNotEqual(gothic.name.lower(), pop.name.lower())
        small = build_cut_caption_panel("今日はここから。", 360, 640, "gothic", "small")
        large = build_cut_caption_panel("今日はここから。", 360, 640, "gothic", "large")
        self.assertGreater(large.height, small.height)

    def test_cut_caption_long_text_uses_at_most_four_lines(self):
        font = ImageFont.truetype(str(_font_path("gothic")), size=58)
        lines = _cut_caption_lines(
            "PM1:00 また出かけます、紫いいでしょ。今日は少し遠くまで歩いて新しい景色を見に行きます。" * 3,
            font,
            760,
        )
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[-1].endswith("…"))

    def test_cut_caption_positions_keep_safe_margins(self):
        self.assertEqual(cut_caption_y("top", 640, 60), 64)
        self.assertEqual(cut_caption_y("center", 640, 60), 290)
        self.assertEqual(cut_caption_y("bottom", 640, 60), 516)

    def test_all_cut_caption_motion_filters_are_supported(self):
        for motion in ("fixed", "fade", "soft_zoom", "slide_up"):
            cut = Cut("x.jpg", duration=3.0, caption_text="一言", caption_motion=motion)
            value, y = build_cut_caption_filter(cut, PREVIEW_RENDER, 100, 30)
            self.assertIn("format=rgba", value)
            if motion == "fixed":
                self.assertNotIn("fade=", value)
            else:
                self.assertIn("fade=t=in", value)
                self.assertIn("fade=t=out", value)
            if motion == "soft_zoom":
                self.assertIn("scale=", value)
            if motion == "slide_up":
                self.assertIn("min(t/", y)

    def test_bgm_filter_has_volume_format_and_fades(self):
        value = build_bgm_filter(16.0, 0.7)
        self.assertIn("aresample=48000", value)
        self.assertIn("channel_layouts=stereo", value)
        self.assertIn("volume=0.7000", value)
        self.assertIn("afade=t=in:st=0:d=0.300", value)
        self.assertIn("afade=t=out:st=14.500:d=1.500", value)
        self.assertIn("atrim=duration=16.000", value)

    def test_bgm_fade_is_shortened_for_short_video(self):
        value = build_bgm_filter(3.0, 1.0)
        self.assertIn("afade=t=out:st=2.000:d=1.000", value)

    def test_cut_audio_filter_trims_delays_and_applies_volume(self):
        value = build_cut_audio_filter(2.5, 0.7, 4.5)
        self.assertIn("aresample=48000", value)
        self.assertIn("channel_layouts=stereo", value)
        self.assertIn("volume=0.7000", value)
        self.assertIn("atrim=start=0:duration=2.500", value)
        self.assertIn("asetpts=PTS-STARTPTS", value)
        self.assertIn("adelay=4500|4500", value)


if __name__ == "__main__":
    unittest.main()
