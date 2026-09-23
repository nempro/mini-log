import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from app.main_window import (
    BG,
    BORDER,
    CAPTION_MOTION_LABELS,
    CAPTION_FONT_LABELS,
    CAPTION_POSITION_LABELS,
    CAPTION_SIZE_LABELS,
    CONTROL_BORDER,
    CUT_TYPE_LABELS,
    INK,
    MOTION_TYPE_LABELS,
    MUTED,
    NO_MOTION_LABEL,
    PANEL,
    STYLE_LABELS,
    MiniLogApp,
    clamp_cut_duration,
    dpi_window_metrics,
    next_available_mp4_name,
)
from app.models import Project
from app.resources import ICON_ICO, ICON_PNG
from app.version import __version__
from app.themes import THEMES, Theme, get_theme
from scripts.release_documents import distribution_readme, third_party_notices


class UiLogicTests(unittest.TestCase):
    def test_release_version(self):
        self.assertEqual(__version__, "0.1.0")

    def test_release_text_uses_the_single_version_source(self):
        self.assertIn(f"Mini Log {__version__}", distribution_readme())
        self.assertIn(f"Mini Log {__version__}", third_party_notices())

    @staticmethod
    def _contrast(first: str, second: str) -> float:
        def luminance(color: str) -> float:
            values = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
            linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in values]
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

        light, dark = sorted((luminance(first), luminance(second)), reverse=True)
        return (light + 0.05) / (dark + 0.05)

    def test_user_facing_values_are_japanese(self):
        self.assertEqual(CUT_TYPE_LABELS["Still"], "静止画")
        self.assertEqual(CUT_TYPE_LABELS["Motion"], "動画風")
        self.assertEqual(MOTION_TYPE_LABELS["Pan Right"], "右へパン")
        self.assertEqual(STYLE_LABELS["Film"], "フィルム")
        self.assertEqual(CAPTION_POSITION_LABELS["center"], "中央")
        self.assertEqual(CAPTION_MOTION_LABELS["soft_zoom"], "ふわっと拡大")
        self.assertEqual(CAPTION_FONT_LABELS["mincho"], "明朝")
        self.assertEqual(CAPTION_SIZE_LABELS["large"], "大")
        self.assertIn("静止画", NO_MOTION_LABEL)

    def test_style_previews_are_visibly_distinct_but_subtle(self):
        source = Image.linear_gradient("L").resize((160, 120)).convert("RGB")
        natural = MiniLogApp._apply_preview_style(source.copy(), "Natural")
        soft = MiniLogApp._apply_preview_style(source.copy(), "Soft")
        film = MiniLogApp._apply_preview_style(source.copy(), "Film")
        soft_difference = sum(ImageStat.Stat(ImageChops.difference(natural, soft)).mean) / 3
        film_difference = sum(ImageStat.Stat(ImageChops.difference(natural, film)).mean) / 3
        self.assertGreater(soft_difference, 1.0)
        self.assertGreater(film_difference, 1.0)
        self.assertLess(soft_difference, 25.0)
        self.assertLess(film_difference, 25.0)

    def test_dropped_file_order_is_preserved_by_project(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = []
            for index in range(6):
                path = Path(folder) / f"{index}.jpg"
                path.touch()
                paths.append(str(path))
            project = Project()
            self.assertEqual(project.add_images(paths), 6)
            self.assertEqual([Path(cut.source_path).name for cut in project.cuts], [f"{i}.jpg" for i in range(6)])

    def test_phase_zero_project_values_remain_compatible(self):
        project = Project.from_dict(
            {
                "cuts": [
                    {
                        "source_path": "old.jpg",
                        "id": "legacy-id",
                        "order": 0,
                        "type": "Motion",
                        "duration": 3.0,
                        "motion_type": "Zoom In",
                    }
                ],
                "style": "Soft",
                "caption_text": "Phase 0",
                "caption_duration": 2.0,
                "aspect_ratio": "9:16",
            }
        )
        self.assertEqual(project.cuts[0].type, "Motion")
        self.assertEqual(project.cuts[0].motion_type, "Zoom In")
        self.assertEqual(project.style, "Soft")
        self.assertEqual(project.cuts[0].caption_text, "")
        self.assertEqual(project.cuts[0].caption_position, "bottom")
        self.assertEqual(project.cuts[0].caption_motion, "fade")
        self.assertEqual(project.cuts[0].caption_font, "gothic")
        self.assertEqual(project.cuts[0].caption_size, "medium")
        self.assertIsNone(project.cuts[0].audio_path)
        self.assertAlmostEqual(project.cuts[0].audio_volume, 0.6)
        self.assertIsNone(project.bgm_path)
        self.assertAlmostEqual(project.bgm_volume, 0.6)
        self.assertEqual(project.theme, "autumn")

    def test_high_contrast_palette_defaults_to_autumn(self):
        autumn = get_theme("autumn")
        self.assertEqual(BG, autumn.background)
        self.assertEqual(PANEL, autumn.surface)
        self.assertEqual(BORDER, autumn.border)
        self.assertGreater(self._contrast(INK, PANEL), 12.0)
        self.assertGreater(self._contrast(MUTED, PANEL), 6.0)
        self.assertGreater(self._contrast(CONTROL_BORDER, PANEL), 2.5)
        self.assertGreater(self._contrast(BORDER, BG), 1.8)

    def test_all_seasonal_themes_share_tokens_and_keep_readable_contrast(self):
        self.assertEqual(set(THEMES), {"spring", "summer", "autumn", "winter"})
        self.assertEqual(len({theme.accent for theme in THEMES.values()}), 4)
        expected_fields = set(Theme.__dataclass_fields__)
        for key, theme in THEMES.items():
            self.assertEqual(set(theme.__dataclass_fields__), expected_fields)
            self.assertEqual(theme.key, key)
            self.assertEqual(theme.surface, "#FFFFFF")
            self.assertGreater(self._contrast(theme.text, theme.surface), 12.0)
            self.assertGreater(self._contrast(theme.text_muted, theme.surface), 5.0)
            self.assertGreater(self._contrast(theme.accent, theme.surface), 4.0)
            self.assertNotEqual(theme.background, theme.surface)

    def test_invalid_theme_falls_back_to_autumn(self):
        project = Project.from_dict({"theme": "neon", "cuts": []})
        self.assertEqual(project.theme, "autumn")

    def test_icon_assets_include_all_windows_sizes(self):
        self.assertTrue(ICON_PNG.is_file())
        self.assertTrue(ICON_ICO.is_file())
        with Image.open(ICON_PNG) as png:
            self.assertEqual(png.size, (256, 256))
            self.assertEqual(png.mode, "RGBA")
            self.assertLessEqual(len(png.getcolors(256 * 256)), 17)
        with Image.open(ICON_ICO) as ico:
            expected_sizes = {(size, size) for size in (16, 24, 32, 48, 64, 128, 256)}
            self.assertEqual(set(ico.ico.sizes()), expected_sizes)
            for size in (16, 24, 32, 48, 64, 128, 256):
                asset_path = ICON_PNG.parent / f"minilog_icon_{size}.png"
                self.assertTrue(asset_path.is_file())
                with Image.open(asset_path) as asset:
                    frame = asset.convert("RGBA")
                self.assertIsNone(ImageChops.difference(frame, ico.ico.getimage((size, size))).getbbox())

    def test_small_icons_are_dedicated_opaque_pixel_art(self):
        frames = {}
        for size, max_colors in ((16, 6), (24, 7), (32, 7)):
            with Image.open(ICON_PNG.parent / f"minilog_icon_{size}.png") as image:
                frame = image.convert("RGBA")
            frames[size] = frame
            self.assertLessEqual(len(frame.getcolors(size * size)), max_colors)
            alpha_values = {value for value, count in enumerate(frame.getchannel("A").histogram()) if count}
            self.assertEqual(alpha_values, {0, 255})
        self.assertEqual(frames[16].getchannel("A").getbbox(), (3, 1, 13, 15))
        with Image.open(ICON_PNG.parent / "minilog_icon_64.png") as image:
            automatic_16 = image.convert("RGBA").resize((16, 16), Image.Resampling.NEAREST)
        self.assertIsNotNone(ImageChops.difference(frames[16], automatic_16).getbbox())

    def test_dpi_metrics_scale_and_stay_on_screen(self):
        width, height, min_width, min_height, scale = dpi_window_metrics(144, 2560, 1440)
        self.assertAlmostEqual(scale, 1.5)
        self.assertEqual((width, height), (1770, 1290))
        self.assertEqual((min_width, min_height), (1440, 1080))
        width, height, *_ = dpi_window_metrics(120, 1920, 1080)
        self.assertLessEqual(width, 1920 - 80)
        self.assertLessEqual(height, 1080 - 90)

    def test_export_filename_uses_next_available_number(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            self.assertEqual(next_available_mp4_name(directory), "mini-log.mp4")
            (directory / "mini-log.mp4").touch()
            self.assertEqual(next_available_mp4_name(directory), "mini-log-001.mp4")
            (directory / "mini-log-001.mp4").touch()
            self.assertEqual(next_available_mp4_name(directory), "mini-log-002.mp4")

    def test_cut_duration_is_clamped_to_safe_tenths(self):
        self.assertEqual(clamp_cut_duration(0), 0.5)
        self.assertEqual(clamp_cut_duration(1.56), 1.6)
        self.assertEqual(clamp_cut_duration(50), 30.0)


if __name__ == "__main__":
    unittest.main()
