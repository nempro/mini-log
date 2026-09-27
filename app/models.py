from __future__ import annotations

import json
import random
import uuid
from dataclasses import asdict, dataclass, field
from math import gcd
from pathlib import Path
from typing import Iterable

from PIL import Image

from .look_engine import LEGACY_PRESET_IDS, PRESET_IDS


SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
SUPPORTED_VIDEO_SUFFIXES = {".mp4", ".mov"}
SUPPORTED_AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac"}
CUT_TYPES = ("Still", "Motion", "Video")
TRANSITION_TYPES = ("cut", "fade", "crossfade", "dip_black")
TRANSITION_DURATIONS = (0.2, 0.4, 0.6)
MOTION_TYPES = ("Zoom In", "Zoom Out", "Pan Left", "Pan Right")
STYLES = ("Natural", "Soft", "Film")
CAPTION_POSITIONS = ("top", "center", "bottom")
CAPTION_MOTIONS = ("fixed", "fade", "soft_zoom", "slide_up")
CAPTION_FONTS = ("gothic", "rounded", "mincho", "pop")
CAPTION_SIZES = ("small", "medium", "large")
CAPTION_STYLES = ("band", "soft_band", "outline", "shadow")
THEMES = ("spring", "summer", "autumn", "winter")
MIN_CUT_DURATION = 0.5
MAX_CUT_DURATION = 30.0


def aspect_ratio_from_size(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        raise ValueError("素材の画像サイズが不正です。")
    divisor = gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


def normalize_aspect_ratio(value: str) -> str:
    try:
        width_text, height_text = value.split(":")
        return aspect_ratio_from_size(int(width_text), int(height_text))
    except (AttributeError, TypeError, ValueError):
        return "9:16"


def _image_aspect_ratio(path: Path) -> str | None:
    try:
        with Image.open(path) as image:
            width, height = image.size
            if image.getexif().get(274, 1) in {5, 6, 7, 8}:
                width, height = height, width
            return aspect_ratio_from_size(width, height)
    except (OSError, ValueError):
        return None


@dataclass
class Cut:
    source_path: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    order: int = 0
    type: str = "Still"
    duration: float = 1.5
    transition_type: str = "cut"
    transition_duration: float = 0.4
    motion_type: str = "Zoom In"
    caption_text: str = ""
    caption_position: str = "bottom"
    caption_motion: str = "fade"
    caption_font: str = "gothic"
    caption_size: str = "medium"
    caption_style: str = "band"
    audio_path: str | None = None
    audio_volume: float = 0.6
    media_duration: float | None = None
    source_has_audio: bool = True
    use_source_audio: bool = True
    source_audio_volume: float = 1.0

    def normalize(self) -> None:
        if self.type not in CUT_TYPES:
            self.type = "Still"
        if self.motion_type not in MOTION_TYPES:
            self.motion_type = "Zoom In"
        if self.transition_type not in TRANSITION_TYPES:
            self.transition_type = "cut"
        try:
            transition_duration = float(self.transition_duration)
        except (TypeError, ValueError):
            transition_duration = 0.4
        self.transition_duration = min(TRANSITION_DURATIONS, key=lambda value: abs(value - transition_duration))
        if self.caption_position not in CAPTION_POSITIONS:
            self.caption_position = "bottom"
        if self.caption_motion not in CAPTION_MOTIONS:
            self.caption_motion = "fade"
        if self.caption_font not in CAPTION_FONTS:
            self.caption_font = "gothic"
        if self.caption_size not in CAPTION_SIZES:
            self.caption_size = "medium"
        if self.caption_style not in CAPTION_STYLES:
            self.caption_style = "band"
        try:
            requested_duration = float(self.duration)
            duration = max(
                MIN_CUT_DURATION,
                requested_duration if self.type == "Video" else min(requested_duration, MAX_CUT_DURATION),
            )
        except (TypeError, ValueError):
            duration = 1.5
        if self.type == "Video" and self.media_duration is not None:
            try:
                self.media_duration = max(0.0, float(self.media_duration))
                if self.media_duration > 0:
                    duration = min(duration, self.media_duration)
            except (TypeError, ValueError):
                self.media_duration = None
        else:
            self.media_duration = None
        self.duration = duration
        try:
            self.audio_volume = max(0.0, min(float(self.audio_volume), 1.0))
        except (TypeError, ValueError):
            self.audio_volume = 0.6
        if not self.audio_path:
            self.audio_path = None
        self.source_has_audio = bool(self.source_has_audio)
        self.use_source_audio = bool(self.use_source_audio)
        try:
            self.source_audio_volume = max(0.0, min(float(self.source_audio_volume), 1.0))
        except (TypeError, ValueError):
            self.source_audio_volume = 1.0

    def effective_duration(self) -> float:
        duration = max(0.0, float(self.duration))
        if self.type == "Video" and self.media_duration is not None and self.media_duration > 0:
            return min(duration, self.media_duration)
        return duration


@dataclass
class Project:
    cuts: list[Cut] = field(default_factory=list)
    style: str = "Natural"
    caption_text: str = ""
    caption_duration: float = 2.0
    aspect_ratio: str = "9:16"
    bgm_path: str | None = None
    bgm_volume: float = 0.6
    theme: str = "autumn"
    look_type: str = "original"
    look_lut_path: str | None = None
    look_strength: float = 1.0

    def output_dimensions(self, short_edge: int = 1080) -> tuple[int, int]:
        """Keep the first material's ratio; round the other edge for H.264."""
        width, height = map(int, normalize_aspect_ratio(self.aspect_ratio).split(":"))
        short_edge = max(2, round(short_edge / 2) * 2)
        if width <= height:
            return short_edge, max(2, round(short_edge * height / width / 2) * 2)
        return max(2, round(short_edge * width / height / 2) * 2), short_edge

    def reindex(self) -> None:
        for index, cut in enumerate(self.cuts):
            cut.order = index

    def video_duration(self) -> float:
        total = sum(cut.effective_duration() for cut in self.cuts)
        for index, cut in enumerate(self.cuts[:-1]):
            transition_duration = self.effective_transition_duration(index)
            if cut.transition_type == "crossfade":
                total -= transition_duration
            elif cut.transition_type == "dip_black":
                total += transition_duration / 3
        return total

    def total_duration(self) -> float:
        total = self.video_duration()
        if self.caption_text.strip():
            total += max(0.0, float(self.caption_duration))
        return total

    def effective_transition_duration(self, index: int) -> float:
        """Return the transition duration after constraining it to both adjacent cuts."""
        if not (0 <= index < len(self.cuts) - 1):
            return 0.0
        cut = self.cuts[index]
        if cut.transition_type == "cut":
            return 0.0
        adjacent = min(cut.effective_duration(), self.cuts[index + 1].effective_duration())
        maximum = adjacent / 2 if cut.transition_type == "crossfade" else adjacent
        return min(float(cut.transition_duration), maximum)

    def cut_start_time(self, index: int) -> float:
        index = max(0, min(index, len(self.cuts)))
        start = sum(cut.effective_duration() for cut in self.cuts[:index])
        for cut_index, cut in enumerate(self.cuts[:index]):
            transition_duration = self.effective_transition_duration(cut_index)
            if cut.transition_type == "crossfade":
                start -= transition_duration
            elif cut.transition_type == "dip_black":
                start += transition_duration / 3
        return start

    def add_images(self, paths: Iterable[str]) -> int:
        existing = {str(Path(c.source_path).resolve()).casefold() for c in self.cuts}
        added = 0
        for raw_path in paths:
            path = Path(raw_path)
            if path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES or not path.is_file():
                continue
            key = str(path.resolve()).casefold()
            if key in existing:
                continue
            if not self.cuts:
                self.aspect_ratio = _image_aspect_ratio(path) or self.aspect_ratio
            self.cuts.append(Cut(source_path=str(path.resolve())))
            existing.add(key)
            added += 1
        self.reindex()
        return added

    def add_materials(
        self, paths: Iterable[str], video_probe, video_dimensions_probe=None,
        insert_index: int | None = None,
    ) -> tuple[int, int, list[str]]:
        """Insert media in input order; video_probe returns (duration, has_audio)."""
        existing = {str(Path(c.source_path).resolve()).casefold() for c in self.cuts}
        insertion = len(self.cuts) if insert_index is None else max(0, min(insert_index, len(self.cuts)))
        added_images = 0
        added_videos = 0
        errors: list[str] = []
        for raw_path in paths:
            path = Path(raw_path)
            suffix = path.suffix.lower()
            if suffix not in SUPPORTED_IMAGE_SUFFIXES | SUPPORTED_VIDEO_SUFFIXES or not path.is_file():
                continue
            key = str(path.resolve()).casefold()
            if key in existing:
                continue
            if suffix in SUPPORTED_IMAGE_SUFFIXES:
                if not self.cuts:
                    self.aspect_ratio = _image_aspect_ratio(path) or self.aspect_ratio
                self.cuts.insert(insertion, Cut(source_path=str(path.resolve())))
                insertion += 1
                added_images += 1
            else:
                try:
                    media_duration, has_audio = video_probe(path)
                    media_duration = float(media_duration)
                    if media_duration <= 0:
                        raise ValueError("動画の長さを取得できません")
                    duration = media_duration
                    cut = Cut(
                        source_path=str(path.resolve()),
                        type="Video",
                        duration=duration,
                        media_duration=media_duration,
                        source_has_audio=has_audio,
                        use_source_audio=True,
                    )
                    cut.normalize()
                    if not self.cuts and video_dimensions_probe is not None:
                        try:
                            self.aspect_ratio = aspect_ratio_from_size(*video_dimensions_probe(path))
                        except Exception:
                            pass
                    self.cuts.insert(insertion, cut)
                    insertion += 1
                    added_videos += 1
                except Exception as exc:
                    errors.append(f"{path.name}: {exc}")
                    continue
            existing.add(key)
        self.reindex()
        return added_images, added_videos, errors

    def move(self, index: int, offset: int) -> int:
        target = index + offset
        if not (0 <= index < len(self.cuts) and 0 <= target < len(self.cuts)):
            return index
        self.cuts[index], self.cuts[target] = self.cuts[target], self.cuts[index]
        self.reindex()
        return target

    def move_to(self, source_index: int, target_index: int) -> int:
        """Move one cut directly to a final list position."""
        if not (0 <= source_index < len(self.cuts)):
            return source_index
        cut = self.cuts.pop(source_index)
        target_index = max(0, min(target_index, len(self.cuts)))
        self.cuts.insert(target_index, cut)
        self.reindex()
        return target_index

    def auto_compose(self, rng: random.Random | None = None) -> None:
        """Create a varied, intentionally bounded Vlog rhythm."""
        rng = rng or random.Random()
        motion_cycle = list(MOTION_TYPES)
        last_motion = None
        previous_types: list[str] = []

        for index, cut in enumerate(self.cuts):
            if cut.type == "Video":
                previous_types.append(cut.type)
                continue
            is_first = index == 0
            is_last = index == len(self.cuts) - 1
            motion_probability = 0.78 if is_first else (0.22 if is_last else 0.48)
            cut_type = "Motion" if rng.random() < motion_probability else "Still"

            if len(previous_types) >= 2 and previous_types[-1] == previous_types[-2] == cut_type:
                cut_type = "Still" if cut_type == "Motion" else "Motion"

            cut.type = cut_type
            if cut_type == "Motion":
                candidates = [motion for motion in motion_cycle if motion != last_motion]
                cut.motion_type = rng.choice(candidates)
                last_motion = cut.motion_type
                cut.duration = round(rng.uniform(2.5, 3.5), 1)
            else:
                cut.duration = round(rng.uniform(1.2, 2.0), 1)
            previous_types.append(cut.type)
        self.reindex()

    def validate_for_export(self) -> list[str]:
        errors: list[str] = []
        if not self.cuts:
            errors.append("画像を1枚以上追加してください。")
        for index, cut in enumerate(self.cuts, start=1):
            cut.normalize()
            if not Path(cut.source_path).is_file():
                kind = "動画" if cut.type == "Video" else "画像"
                errors.append(f"カット {index} の{kind}ファイルが見つかりません: {cut.source_path}")
            elif cut.type == "Video" and (cut.media_duration is None or cut.media_duration <= 0):
                errors.append(f"カット {index} の動画情報がありません。動画を追加し直してください。")
        if self.style not in STYLES:
            errors.append("Styleが不正です。")
        try:
            self.caption_duration = max(0.2, min(float(self.caption_duration), 60.0))
        except (TypeError, ValueError):
            errors.append("Caption Durationを数値で入力してください。")
        try:
            self.bgm_volume = max(0.0, min(float(self.bgm_volume), 1.0))
        except (TypeError, ValueError):
            errors.append("BGM音量が不正です。")
        if self.theme not in THEMES:
            self.theme = "autumn"
        self.aspect_ratio = normalize_aspect_ratio(self.aspect_ratio)
        if self.look_type not in {"original", "custom_lut"} | PRESET_IDS:
            self.look_type = "original"
            self.look_lut_path = None
        try:
            self.look_strength = max(0.0, min(float(self.look_strength), 1.0))
        except (TypeError, ValueError):
            self.look_strength = 1.0
        if self.look_type == "custom_lut" and self.look_lut_path and Path(self.look_lut_path).is_file():
            from .look_engine import LookError, validate_cube

            try:
                validate_cube(self.look_lut_path)
            except LookError as exc:
                errors.append(f"LOOKのLUTを読み込めません: {exc}")
        return errors

    def to_dict(self) -> dict:
        self.reindex()
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        theme = data.get("theme", "autumn")
        if theme not in THEMES:
            theme = "autumn"
        lut_path = data.get("look_lut_path")
        if not isinstance(lut_path, str) or not lut_path.strip():
            lut_path = None
        look_type = data.get("look_type", "original")
        if look_type == "preset":
            old_id = data.get("look_preset")
            look_type = LEGACY_PRESET_IDS.get(old_id, old_id) if isinstance(old_id, str) else "original"
        elif isinstance(look_type, str):
            look_type = LEGACY_PRESET_IDS.get(look_type, look_type)
        if not isinstance(look_type, str) or look_type not in {"original", "custom_lut"} | PRESET_IDS:
            look_type = "original"
        project = cls(
            cuts=[Cut(**item) for item in data.get("cuts", [])],
            style=data.get("style", "Natural"),
            caption_text=data.get("caption_text", ""),
            caption_duration=data.get("caption_duration", 2.0),
            aspect_ratio=normalize_aspect_ratio(data.get("aspect_ratio", "9:16")),
            bgm_path=data.get("bgm_path"),
            bgm_volume=data.get("bgm_volume", 0.6),
            theme=theme,
            look_type=look_type,
            look_lut_path=lut_path,
            look_strength=data.get("look_strength", 1.0),
        )
        if project.look_type != "custom_lut":
            project.look_lut_path = None
        try:
            project.look_strength = max(0.0, min(float(project.look_strength), 1.0))
        except (TypeError, ValueError):
            project.look_strength = 1.0
        if project.look_type == "original":
            project.look_strength = 1.0
        for cut in project.cuts:
            cut.normalize()
        project.reindex()
        return project

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "Project":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
