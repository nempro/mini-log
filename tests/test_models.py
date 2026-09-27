import random
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.models import MOTION_TYPES, Cut, Project


class ProjectTests(unittest.TestCase):
    def test_materials_insert_after_active_in_input_order_and_survive_save(self):
        with tempfile.TemporaryDirectory() as folder:
            base = [Path(folder) / f"base-{index}.png" for index in range(5)]
            additions = [Path(folder) / "A.png", Path(folder) / "B.mp4", Path(folder) / "C.png"]
            for path in base + [additions[0], additions[2]]:
                Image.new("RGB", (300, 400)).save(path)
            additions[1].touch()
            project = Project()
            project.add_materials(map(str, base), lambda _path: (1.0, False))
            project.add_materials(
                map(str, additions), lambda _path: (2.0, True),
                lambda _path: (300, 400), insert_index=3,
            )
            expected = [*base[:3], *additions, *base[3:]]
            self.assertEqual([Path(c.source_path) for c in project.cuts], expected)
            self.assertEqual([c.order for c in project.cuts], list(range(8)))
            self.assertEqual(project.total_duration(), 12.5)
            saved = Path(folder) / "insert.minilog"
            project.save(saved)
            self.assertEqual([Path(c.source_path) for c in Project.load(saved).cuts], expected)

    def test_caption_style_round_trip_and_legacy_default(self):
        project = Project(cuts=[Cut("picture.png", caption_style="shadow")])
        self.assertEqual(Project.from_dict(project.to_dict()).cuts[0].caption_style, "shadow")
        old = project.to_dict()
        del old["cuts"][0]["caption_style"]
        self.assertEqual(Project.from_dict(old).cuts[0].caption_style, "band")
        old["cuts"][0]["caption_style"] = "unknown"
        self.assertEqual(Project.from_dict(old).cuts[0].caption_style, "band")

    def test_first_image_sets_project_ratio_and_later_images_do_not_change_it(self):
        with tempfile.TemporaryDirectory() as folder:
            first = Path(folder) / "first.png"
            second = Path(folder) / "second.png"
            Image.new("RGB", (300, 400)).save(first)
            Image.new("RGB", (90, 160)).save(second)
            project = Project()
            project.add_materials([str(first), str(second)], lambda _path: (1.0, False))
            self.assertEqual(project.aspect_ratio, "3:4")
            self.assertEqual(project.output_dimensions(), (1080, 1440))
            self.assertEqual(project.output_dimensions(360), (360, 480))
            restored = Project.from_dict(project.to_dict())
            self.assertEqual(restored.aspect_ratio, "3:4")
        self.assertEqual(Project.from_dict({"cuts": []}).aspect_ratio, "9:16")

    def test_first_video_sets_ratio_and_output_dimensions_cover_common_shapes(self):
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "first.mp4"
            video.touch()
            project = Project()
            project.add_materials([str(video)], lambda _path: (2.0, True), lambda _path: (1920, 1080))
            self.assertEqual(project.aspect_ratio, "16:9")
            self.assertEqual(project.output_dimensions(), (1920, 1080))
        self.assertEqual(Project(aspect_ratio="1:1").output_dimensions(), (1080, 1080))
        self.assertEqual(Project(aspect_ratio="4:3").output_dimensions(), (1440, 1080))
        self.assertEqual(Project(aspect_ratio="9:16").output_dimensions(), (1080, 1920))
        arbitrary = Project(aspect_ratio="101:137").output_dimensions()
        self.assertTrue(all(edge % 2 == 0 for edge in arbitrary))
        self.assertLess(abs(arbitrary[0] / arbitrary[1] - 101 / 137), 0.001)

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

    def test_video_cut_duration_and_audio_settings_round_trip(self):
        project = Project(
            cuts=[
                Cut(
                    "clip.mp4",
                    type="Video",
                    duration=8.0,
                    media_duration=3.25,
                    source_has_audio=True,
                    use_source_audio=False,
                    source_audio_volume=0.45,
                )
            ]
        )
        project.cuts[0].normalize()
        self.assertEqual(project.cuts[0].duration, 3.25)
        self.assertEqual(project.cuts[0].effective_duration(), 3.25)
        self.assertEqual(project.total_duration(), 3.25)

        restored = Project.from_dict(project.to_dict())
        cut = restored.cuts[0]
        self.assertEqual(cut.type, "Video")
        self.assertEqual(cut.media_duration, 3.25)
        self.assertFalse(cut.use_source_audio)
        self.assertAlmostEqual(cut.source_audio_volume, 0.45)

    def test_video_duration_can_exceed_thirty_seconds_up_to_source_length(self):
        project = Project(cuts=[Cut("long.mp4", type="Video", duration=62.5, media_duration=75.0)])
        project.cuts[0].normalize()
        self.assertEqual(project.cuts[0].duration, 62.5)
        self.assertEqual(Project.from_dict(project.to_dict()).cuts[0].duration, 62.5)
        project.cuts[0].duration = 90.0
        project.cuts[0].normalize()
        self.assertEqual(project.cuts[0].duration, 75.0)

    def test_long_video_is_added_with_full_source_duration(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "long.mp4"
            source.touch()
            project = Project()
            self.assertEqual(project.add_materials([str(source)], lambda _path: (95.4, True))[:2], (0, 1))
            self.assertEqual(project.cuts[0].duration, 95.4)
            self.assertEqual(Project.from_dict(project.to_dict()).cuts[0].duration, 95.4)

    def test_legacy_project_video_audio_fields_default_safely(self):
        project = Project.from_dict({"cuts": [{"source_path": "legacy.jpg"}]})
        cut = project.cuts[0]
        self.assertEqual(cut.type, "Still")
        self.assertIsNone(cut.media_duration)
        self.assertTrue(cut.source_has_audio)
        self.assertTrue(cut.use_source_audio)
        self.assertEqual(cut.source_audio_volume, 1.0)

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

    def test_transition_duration_and_cut_positions_are_accounted_for(self):
        project = Project(
            cuts=[
                Cut("a.jpg", duration=2.0, transition_type="crossfade", transition_duration=0.4),
                Cut("b.jpg", duration=3.0, transition_type="dip_black", transition_duration=0.6),
                Cut("c.jpg", duration=4.0),
            ]
        )
        self.assertAlmostEqual(project.effective_transition_duration(0), 0.4)
        self.assertAlmostEqual(project.video_duration(), 8.8)
        self.assertAlmostEqual(project.cut_start_time(1), 1.6)
        self.assertAlmostEqual(project.cut_start_time(2), 4.8)

    def test_transition_defaults_and_legacy_project_compatibility(self):
        project = Project.from_dict({"cuts": [{"source_path": "legacy.jpg"}]})
        self.assertEqual(project.cuts[0].transition_type, "cut")
        self.assertAlmostEqual(project.cuts[0].transition_duration, 0.4)
        restored = Project.from_dict(project.to_dict())
        self.assertEqual(restored.cuts[0].transition_type, "cut")
        self.assertAlmostEqual(restored.cuts[0].transition_duration, 0.4)

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
