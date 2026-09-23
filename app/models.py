from __future__ import annotations

import json
import random
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
SUPPORTED_AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac"}
CUT_TYPES = ("Still", "Motion")
MOTION_TYPES = ("Zoom In", "Zoom Out", "Pan Left", "Pan Right")
STYLES = ("Natural", "Soft", "Film")
CAPTION_POSITIONS = ("top", "center", "bottom")
CAPTION_MOTIONS = ("fixed", "fade", "soft_zoom", "slide_up")
CAPTION_FONTS = ("gothic", "rounded", "mincho", "pop")
CAPTION_SIZES = ("small", "medium", "large")
THEMES = ("spring", "summer", "autumn", "winter")
MIN_CUT_DURATION = 0.5
MAX_CUT_DURATION = 30.0


@dataclass
class Cut:
    source_path: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    order: int = 0
    type: str = "Still"
    duration: float = 1.5
    motion_type: str = "Zoom In"
    caption_text: str = ""
    caption_position: str = "bottom"
    caption_motion: str = "fade"
    caption_font: str = "gothic"
    caption_size: str = "medium"
    audio_path: str | None = None
    audio_volume: float = 0.6

    def normalize(self) -> None:
        if self.type not in CUT_TYPES:
            self.type = "Still"
        if self.motion_type not in MOTION_TYPES:
            self.motion_type = "Zoom In"
        if self.caption_position not in CAPTION_POSITIONS:
            self.caption_position = "bottom"
        if self.caption_motion not in CAPTION_MOTIONS:
            self.caption_motion = "fade"
        if self.caption_font not in CAPTION_FONTS:
            self.caption_font = "gothic"
        if self.caption_size not in CAPTION_SIZES:
            self.caption_size = "medium"
        self.duration = max(MIN_CUT_DURATION, min(float(self.duration), MAX_CUT_DURATION))
        try:
            self.audio_volume = max(0.0, min(float(self.audio_volume), 1.0))
        except (TypeError, ValueError):
            self.audio_volume = 0.6
        if not self.audio_path:
            self.audio_path = None


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

    def reindex(self) -> None:
        for index, cut in enumerate(self.cuts):
            cut.order = index

    def total_duration(self) -> float:
        total = sum(max(0.0, float(cut.duration)) for cut in self.cuts)
        if self.caption_text.strip():
            total += max(0.0, float(self.caption_duration))
        return total

    def cut_start_time(self, index: int) -> float:
        return sum(max(0.0, float(cut.duration)) for cut in self.cuts[: max(0, index)])

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
            self.cuts.append(Cut(source_path=str(path.resolve())))
            existing.add(key)
            added += 1
        self.reindex()
        return added

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
                errors.append(f"カット {index} の画像が見つかりません: {cut.source_path}")
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
        return errors

    def to_dict(self) -> dict:
        self.reindex()
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        theme = data.get("theme", "autumn")
        if theme not in THEMES:
            theme = "autumn"
        project = cls(
            cuts=[Cut(**item) for item in data.get("cuts", [])],
            style=data.get("style", "Natural"),
            caption_text=data.get("caption_text", ""),
            caption_duration=data.get("caption_duration", 2.0),
            aspect_ratio=data.get("aspect_ratio", "9:16"),
            bgm_path=data.get("bgm_path"),
            bgm_volume=data.get("bgm_volume", 0.6),
            theme=theme,
        )
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
