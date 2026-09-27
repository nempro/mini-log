import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.look_engine import (
    PRESET_IDS, PRESET_LOOKS, LookError, apply_still_look, preset_lut, validate_cube,
    write_preset_cube,
)
from app.models import Project


class LookEngineTests(unittest.TestCase):
    def test_phase2_preset_names(self):
        self.assertEqual(
            tuple((preset_id, label) for preset_id, label, _description in PRESET_LOOKS),
            (("warm", "暖色"), ("faded", "色あせ"), ("retro", "レトロ"),
             ("cool", "寒色"), ("film", "フィルム")),
        )

    def test_legacy_project_defaults_to_original(self):
        project = Project.from_dict({"cuts": [{"source_path": "old.jpg"}]})
        self.assertEqual((project.look_type, project.look_lut_path, project.look_strength), ("original", None, 1.0))

    def test_cube_requires_complete_finite_3d_table(self):
        with tempfile.TemporaryDirectory() as temporary:
            cube = Path(temporary) / "look.cube"
            cube.write_text("LUT_3D_SIZE 2\n" + "0 0 0\n" * 8, encoding="utf-8")
            self.assertEqual(validate_cube(cube).size, 2)
            cube.write_text("LUT_3D_SIZE 2\n" + "0 0 0\n" * 7, encoding="utf-8")
            with self.assertRaises(LookError):
                validate_cube(cube)
            cube.write_text("LUT_3D_SIZE 2\n" + "nan 0 0\n" * 8, encoding="utf-8")
            with self.assertRaises(LookError):
                validate_cube(cube)
            with self.assertRaises(LookError):
                validate_cube(Path(temporary) / "missing.cube")

    def test_built_in_presets_are_distinct_and_use_the_cube_pipeline(self):
        source = Image.new("RGB", (1, 1), (80, 135, 190))
        original = source.getpixel((0, 0))
        results = set()
        with tempfile.TemporaryDirectory() as temporary:
            for preset_id in PRESET_IDS:
                generated = preset_lut(preset_id)
                cube_path = Path(temporary) / f"{preset_id}.cube"
                write_preset_cube(preset_id, cube_path)
                parsed = validate_cube(cube_path)
                self.assertEqual(parsed.size, generated.size)
                self.assertEqual(apply_still_look(source, generated, 0).getpixel((0, 0)), original)
                preview = apply_still_look(source, generated, 1).getpixel((0, 0))
                exported = apply_still_look(source, parsed, 1).getpixel((0, 0))
                self.assertTrue(all(abs(a - b) <= 1 for a, b in zip(preview, exported)))
                results.add(preview)
        self.assertEqual(len(results), len(PRESET_IDS))

    def test_preset_project_saves_id_without_a_user_lut_path(self):
        project = Project(look_type="warm", look_strength=0.45)
        with tempfile.TemporaryDirectory() as temporary:
            saved = Path(temporary) / "look.minilog"
            project.save(saved)
            restored = Project.load(saved)
        self.assertEqual((restored.look_type, restored.look_lut_path, restored.look_strength),
                         ("warm", None, 0.45))
        self.assertNotIn("look_preset", restored.to_dict())
        old_preset = Project.from_dict({"look_type": "preset", "look_preset": "clear_blue", "look_strength": 0.6})
        self.assertEqual((old_preset.look_type, old_preset.look_strength), ("cool", 0.6))
        invalid = Project.from_dict({"look_type": "preset", "look_preset": "missing"})
        self.assertEqual(invalid.look_type, "original")


if __name__ == "__main__":
    unittest.main()
