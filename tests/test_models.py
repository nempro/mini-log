import random
import tempfile
import unittest
from pathlib import Path

from app.models import MOTION_TYPES, Cut, Project


class ProjectTests(unittest.TestCase):
    def _project(self, count=8):
        return Project(cuts=[Cut(source_path=f"image-{index}.jpg") for index in range(count)])

    def test_move_reindexes(self):
        project = self._project(3)
        original = project.cuts[0].id
        new_index = project.move(0, 1)
        self.assertEqual(new_index, 1)
        self.assertEqual(project.cuts[1].id, original)
        self.assertEqual([cut.order for cut in project.cuts], [0, 1, 2])

    def test_move_to_supports_long_distance_reorder(self):
        project = self._project(6)
        moved_id = project.cuts[5].id
        final_index = project.move_to(5, 1)
        self.assertEqual(final_index, 1)
        self.assertEqual(project.cuts[1].id, moved_id)
        self.assertEqual([cut.order for cut in project.cuts], list(range(6)))

    def test_auto_compose_stays_in_bounds_and_varied(self):
        project = self._project(12)
        project.cuts[0].caption_text = "残す一言"
        project.cuts[0].caption_position = "top"
        project.cuts[0].caption_motion = "slide_up"
        project.cuts[0].caption_font = "mincho"
        project.cuts[0].caption_size = "large"
        project.auto_compose(random.Random(7))
        for cut in project.cuts:
            if cut.type == "Motion":
                self.assertGreaterEqual(cut.duration, 2.5)
                self.assertLessEqual(cut.duration, 3.5)
                self.assertIn(cut.motion_type, MOTION_TYPES)
            else:
                self.assertGreaterEqual(cut.duration, 1.2)
                self.assertLessEqual(cut.duration, 2.0)
        types = [cut.type for cut in project.cuts]
        self.assertFalse(any(types[i] == types[i + 1] == types[i + 2] for i in range(len(types) - 2)))
        motions = [cut.motion_type for cut in project.cuts if cut.type == "Motion"]
        self.assertFalse(any(a == b for a, b in zip(motions, motions[1:])))
        self.assertEqual(
            (
                project.cuts[0].caption_text,
                project.cuts[0].caption_position,
                project.cuts[0].caption_motion,
            ),
            ("残す一言", "top", "slide_up"),
        )
        self.assertEqual((project.cuts[0].caption_font, project.cuts[0].caption_size), ("mincho", "large"))

    def test_project_round_trip(self):
        project = self._project(2)
        project.style = "Soft"
        project.caption_text = "水族館に行った日。"
        project.bgm_path = "C:/music/summer_walk.mp3"
        project.bgm_volume = 0.65
        project.theme = "winter"
        project.cuts[0].caption_text = "今日はここから。"
        project.cuts[0].caption_position = "center"
        project.cuts[0].caption_motion = "soft_zoom"
        project.cuts[0].caption_font = "pop"
        project.cuts[0].caption_size = "large"
        project.cuts[0].audio_path = "C:/audio/laugh.wav"
        project.cuts[0].audio_volume = 0.7
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.minilog"
            project.save(path)
            restored = Project.load(path)
        self.assertEqual(restored.style, "Soft")
        self.assertEqual(restored.caption_text, project.caption_text)
        self.assertEqual(len(restored.cuts), 2)
        self.assertEqual(restored.cuts[0].caption_text, "今日はここから。")
        self.assertEqual(restored.cuts[0].caption_position, "center")
        self.assertEqual(restored.cuts[0].caption_motion, "soft_zoom")
        self.assertEqual(restored.cuts[0].caption_font, "pop")
        self.assertEqual(restored.cuts[0].caption_size, "large")
        self.assertEqual(restored.cuts[0].audio_path, "C:/audio/laugh.wav")
        self.assertAlmostEqual(restored.cuts[0].audio_volume, 0.7)
        self.assertEqual(restored.bgm_path, "C:/music/summer_walk.mp3")
        self.assertAlmostEqual(restored.bgm_volume, 0.65)
        self.assertEqual(restored.theme, "winter")

    def test_total_duration_and_cut_start_time(self):
        project = Project(
            cuts=[Cut("a.jpg", duration=3.0), Cut("b.jpg", duration=1.5), Cut("c.jpg", duration=2.0)],
            caption_text="終了",
            caption_duration=1.8,
        )
        self.assertAlmostEqual(project.cut_start_time(2), 4.5)
        self.assertAlmostEqual(project.total_duration(), 8.3)
        project.caption_text = ""
        self.assertAlmostEqual(project.total_duration(), 6.5)

    def test_legacy_cut_audio_defaults_and_duration_bounds(self):
        project = Project.from_dict({"cuts": [{"source_path": "legacy.jpg", "duration": 0.1}]})
        cut = project.cuts[0]
        self.assertIsNone(cut.audio_path)
        self.assertAlmostEqual(cut.audio_volume, 0.6)
        self.assertAlmostEqual(project.bgm_volume, 0.6)
        cut.normalize()
        self.assertAlmostEqual(cut.duration, 0.5)
        cut.duration = 50
        cut.audio_volume = 4
        cut.normalize()
        self.assertAlmostEqual(cut.duration, 30.0)
        self.assertAlmostEqual(cut.audio_volume, 1.0)

    def test_saved_audio_volumes_are_not_replaced_by_new_defaults(self):
        project = Project.from_dict(
            {
                "cuts": [{"source_path": "saved.jpg", "audio_volume": 1.0}],
                "bgm_volume": 0.7,
            }
        )
        self.assertAlmostEqual(project.cuts[0].audio_volume, 1.0)
        self.assertAlmostEqual(project.bgm_volume, 0.7)


if __name__ == "__main__":
    unittest.main()
