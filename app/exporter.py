from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont

from .models import SUPPORTED_AUDIO_SUFFIXES, Cut, Project
from .resources import bundled_tool_candidates


WIDTH = 1080
HEIGHT = 1920
FPS = 30
MOTION_SCALE = 2


@dataclass(frozen=True)
class RenderSettings:
    width: int
    height: int
    fps: int = 30
    motion_scale: int = 2
    preset: str = "medium"
    crf: int = 20
    preview: bool = False


FINAL_RENDER = RenderSettings(WIDTH, HEIGHT, FPS, MOTION_SCALE, "medium", 20, False)
PREVIEW_RENDER = RenderSettings(360, 640, FPS, 2, "ultrafast", 26, True)


class ExportError(RuntimeError):
    pass


def find_ffmpeg() -> str:
    for candidate in bundled_tool_candidates("ffmpeg.exe"):
        if candidate.is_file():
            return str(candidate)

    override = os.environ.get("MINILOG_FFMPEG")
    if override and Path(override).is_file():
        return override

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        pass

    executable = shutil.which("ffmpeg")
    if executable:
        return executable

    if getattr(sys, "frozen", False):
        message = (
            "FFmpegが見つかりません。\n\n"
            "Mini Logの動画作成にはFFmpegが必要です。\n"
            "アプリを再インストールしてください。"
        )
    else:
        message = (
            "FFmpegが見つかりません。imageio-ffmpegをインストールするか、"
            "MINILOG_FFMPEGにffmpeg.exeの場所を設定してください。"
        )
    raise ExportError(message)


def find_ffprobe(ffmpeg_path: str | None = None) -> str | None:
    for candidate in bundled_tool_candidates("ffprobe.exe"):
        if candidate.is_file():
            return str(candidate)
    if ffmpeg_path:
        sibling = Path(ffmpeg_path).with_name("ffprobe.exe")
        if sibling.is_file():
            return str(sibling)
    return shutil.which("ffprobe")


def _style_filter(style: str, settings: RenderSettings = FINAL_RENDER) -> str:
    if style == "Soft":
        return "eq=brightness=0.045:contrast=0.92:saturation=0.90"
    if style == "Film":
        grain = 1.2 if settings.preview else 2.2
        return (
            "eq=brightness=0.025:contrast=0.95:saturation=0.95:"
            f"gamma_r=1.025:gamma_b=0.975,noise=alls={grain}:allf=t"
        )
    return "eq=brightness=0.008:contrast=1.01:saturation=1.0"


def build_video_filter(
    cut: Cut,
    style: str,
    frames: int,
    settings: RenderSettings = FINAL_RENDER,
) -> str:
    denominator = max(frames - 1, 1)
    if cut.type == "Motion":
        work_width = settings.width * settings.motion_scale
        work_height = settings.height * settings.motion_scale
        progress = f"on/{denominator}"
        ease = f"(({progress})*({progress})*(3-2*({progress})))"
        if cut.motion_type == "Zoom Out":
            zoom = f"1.08-0.08*{ease}"
            x = "(iw-iw/zoom)/2"
            y = "(ih-ih/zoom)/2"
        elif cut.motion_type == "Pan Left":
            zoom = "1.08"
            x = f"(iw-iw/zoom)*(1-{ease})"
            y = "(ih-ih/zoom)/2"
        elif cut.motion_type == "Pan Right":
            zoom = "1.08"
            x = f"(iw-iw/zoom)*{ease}"
            y = "(ih-ih/zoom)/2"
        else:
            zoom = f"1+0.08*{ease}"
            x = "(iw-iw/zoom)/2"
            y = "(ih-ih/zoom)/2"
        filters = [
            f"scale={work_width}:{work_height}:force_original_aspect_ratio=increase:flags=lanczos",
            f"crop={work_width}:{work_height}",
            "setsar=1",
            f"zoompan=z='{zoom}':x='{x}':y='{y}':d=1:s={work_width}x{work_height}:fps={settings.fps}",
            f"scale={settings.width}:{settings.height}:flags=lanczos",
            _style_filter(style, settings),
        ]
    else:
        filters = [
            f"scale={settings.width}:{settings.height}:force_original_aspect_ratio=increase:flags=lanczos",
            f"crop={settings.width}:{settings.height}",
            "setsar=1",
            _style_filter(style, settings),
            f"fps={settings.fps}",
        ]
    filters.append("format=yuv420p")
    return ",".join(filters)


def _cut_caption_lines(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    max_lines: int = 4,
) -> list[str]:
    lines = [
        wrapped
        for source_line in (text.splitlines() or [text])
        for wrapped in _wrap_cut_caption_line(source_line, font, max_width)
    ]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and font.getlength(lines[-1] + "…") > max_width:
            lines[-1] = lines[-1][:-1]
        lines[-1] = (lines[-1].rstrip("…") + "…") if lines[-1] else "…"
    return lines


def _wrap_cut_caption_line(line: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    if not line:
        return [""]
    prohibited_start = set("、。！？：；，．・…）」』】〉》,.!?)]}")
    prohibited_end = set("（「『【〈《([{“")
    wrapped: list[str] = []
    current = ""
    for character in line:
        candidate = current + character
        if current and font.getlength(candidate) > max_width:
            if character in prohibited_start:
                wrapped.append(candidate.rstrip())
                current = ""
            elif current[-1] in prohibited_end and len(current) > 1:
                wrapped.append(current[:-1].rstrip())
                current = current[-1] + character
            else:
                wrapped.append(current.rstrip())
                current = character.lstrip() if character.isspace() else character
        else:
            current = candidate
    if current or not wrapped:
        wrapped.append(current.rstrip())
    return wrapped


def build_cut_caption_panel(
    text: str,
    frame_width: int,
    frame_height: int,
    caption_font: str = "gothic",
    caption_size: str = "medium",
) -> Image.Image:
    """Build the shared caption artwork used by UI preview and video renders."""
    cleaned = text.strip()
    if not cleaned:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    size_scales = {"small": 0.044, "medium": 0.054, "large": 0.066}
    minimum_sizes = {"small": 14, "medium": 18, "large": 21}
    size_key = caption_size if caption_size in size_scales else "medium"
    font_size = max(minimum_sizes[size_key], round(frame_width * size_scales[size_key]))
    font = ImageFont.truetype(str(_font_path(caption_font)), size=font_size)
    padding_x = max(12, round(frame_width * 0.035))
    padding_y = max(7, round(frame_height * 0.009))
    max_text_width = max(120, round(frame_width * 0.82))
    spacing = max(4, round(font_size * 0.24))
    lines = _cut_caption_lines(cleaned, font, max_text_width)
    rendered = "\n".join(lines)

    measuring = Image.new("RGBA", (frame_width, frame_height), (0, 0, 0, 0))
    measure_draw = ImageDraw.Draw(measuring)
    bounds = measure_draw.multiline_textbbox(
        (0, 0), rendered, font=font, spacing=spacing, align="center", stroke_width=max(1, round(font_size * 0.035))
    )
    text_width = max(1, int(bounds[2] - bounds[0] + 0.999))
    text_height = max(1, int(bounds[3] - bounds[1] + 0.999))
    panel = Image.new(
        "RGBA",
        (min(round(frame_width * 0.92), text_width + padding_x * 2), text_height + padding_y * 2),
        (0, 0, 0, 0),
    )
    draw = ImageDraw.Draw(panel)
    radius = max(8, round(font_size * 0.28))
    draw.rounded_rectangle((0, 0, panel.width - 1, panel.height - 1), radius=radius, fill=(0, 0, 0, 150))
    stroke_width = max(1, round(font_size * 0.035))
    draw.multiline_text(
        ((panel.width - text_width) / 2 - bounds[0], padding_y - bounds[1]),
        rendered,
        font=font,
        fill=(255, 255, 255, 255),
        align="center",
        spacing=spacing,
        stroke_width=stroke_width,
        stroke_fill=(0, 0, 0, 220),
    )
    return panel


def cut_caption_y(position: str, frame_height: int, panel_height: int) -> int:
    margin = round(frame_height * 0.10)
    if position == "top":
        return margin
    if position == "center":
        return max(margin, (frame_height - panel_height) // 2)
    return max(margin, frame_height - panel_height - margin)


def build_cut_caption_filter(
    cut: Cut,
    settings: RenderSettings,
    panel_width: int,
    panel_height: int,
) -> tuple[str, str]:
    """Return caption input filtering and overlay y expression."""
    fade = min(0.25, max(0.08, cut.duration / 4))
    fade_out = max(0.0, cut.duration - fade)
    filters = ["format=rgba"]
    if cut.caption_motion == "soft_zoom":
        grow_frames = max(1, round(min(0.50, cut.duration / 3) * settings.fps))
        filters.append(
            "scale="
            f"w='max(2,trunc(iw*(0.94+0.06*min(n/{grow_frames}\\,1))/2)*2)':"
            "h=-2:eval=frame"
        )
    if cut.caption_motion != "fixed":
        filters.extend(
            [
                f"fade=t=in:st=0:d={fade:.3f}:alpha=1",
                f"fade=t=out:st={fade_out:.3f}:d={fade:.3f}:alpha=1",
            ]
        )

    if cut.caption_position == "top":
        base_y = "main_h*0.10"
    elif cut.caption_position == "center":
        base_y = "(main_h-overlay_h)/2"
    else:
        base_y = "main_h-overlay_h-main_h*0.10"
    if cut.caption_motion == "slide_up":
        distance = max(10, round(settings.height * 0.045))
        base_y = f"({base_y})+{distance}*(1-min(t/{fade:.3f}\\,1))"
    return ",".join(filters), base_y


def _run(command: list[str]) -> None:
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )
    if result.returncode != 0:
        tail = "\n".join(result.stderr.splitlines()[-18:])
        raise ExportError(f"FFmpegの処理に失敗しました。\n{tail}")


def _render_cut(
    ffmpeg: str,
    cut: Cut,
    style: str,
    output: Path,
    settings: RenderSettings,
) -> None:
    frames = max(1, round(cut.duration * settings.fps))
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-loop",
        "1",
        "-framerate",
        str(settings.fps),
        "-i",
        cut.source_path,
    ]
    if cut.caption_text.strip():
        panel = build_cut_caption_panel(
            cut.caption_text,
            settings.width,
            settings.height,
            cut.caption_font,
            cut.caption_size,
        )
        panel_path = output.with_suffix(".caption.png")
        panel.save(panel_path)
        caption_filter, overlay_y = build_cut_caption_filter(
            cut, settings, panel.width, panel.height
        )
        command.extend(
            [
                "-loop",
                "1",
                "-framerate",
                str(settings.fps),
                "-i",
                str(panel_path),
                "-filter_complex",
                (
                    f"[0:v]{build_video_filter(cut, style, frames, settings)}[base];"
                    f"[1:v]{caption_filter}[cap];"
                    f"[base][cap]overlay=x=(main_w-overlay_w)/2:y='{overlay_y}':shortest=1,"
                    "format=yuv420p[v]"
                ),
                "-map",
                "[v]",
            ]
        )
    else:
        command.extend(["-vf", build_video_filter(cut, style, frames, settings)])
    command.extend(
        [
            "-frames:v",
            str(frames),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            settings.preset,
            "-crf",
            str(settings.crf),
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(settings.fps),
            str(output),
        ]
    )
    _run(command)


def _font_path(preset: str = "gothic") -> Path:
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    preset_candidates = {
        "gothic": [fonts / "meiryo.ttc", fonts / "YuGothM.ttc"],
        "rounded": [fonts / "BIZ-UDGothicR.ttc", fonts / "meiryo.ttc"],
        "mincho": [fonts / "yumin.ttf", fonts / "BIZ-UDMinchoM.ttc", fonts / "msmincho.ttc"],
        "pop": [fonts / "HGRPP1.TTC", fonts / "HGRSMP.TTF", fonts / "meiryob.ttc"],
    }
    candidates = preset_candidates.get(preset, preset_candidates["gothic"]) + [
        fonts / "NotoSansJP-VF.ttf",
        fonts / "meiryo.ttc",
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ExportError("Captionに使えるフォントが見つかりません。")


def _wrap_caption_line(line: str, font: ImageFont.FreeTypeFont, max_width: int = 900) -> list[str]:
    if not line:
        return [""]
    wrapped: list[str] = []
    current = ""
    for character in line:
        candidate = current + character
        if current and font.getlength(candidate) > max_width:
            wrapped.append(current.rstrip())
            current = character.lstrip() if character.isspace() else character
        else:
            current = candidate
    wrapped.append(current.rstrip())
    return wrapped


def _caption_layout(
    text: str,
    font_path: Path,
    max_width: int = 900,
    max_height: int = 1500,
    max_font_size: int = 96,
    min_font_size: int = 14,
    line_spacing: int = 24,
) -> tuple[str, int]:
    source_lines = text.splitlines() or [text]
    for size in range(max_font_size, min_font_size - 1, -2):
        try:
            font = ImageFont.truetype(str(font_path), size=size)
        except OSError as exc:
            raise ExportError(f"Captionフォントを読み込めません: {font_path}") from exc
        lines = [wrapped for line in source_lines for wrapped in _wrap_caption_line(line, font, max_width)]
        bounds = font.getbbox("あAg")
        line_height = bounds[3] - bounds[1]
        if line_height * len(lines) + line_spacing * max(0, len(lines) - 1) <= max_height:
            return "\n".join(lines), size

    # Pathological input is kept on-screen rather than silently overflowing.
    font = ImageFont.truetype(str(font_path), size=min_font_size)
    lines = [wrapped for line in source_lines for wrapped in _wrap_caption_line(line, font, max_width)]
    max_lines = max(1, max_height // ((font.getbbox("あAg")[3] - font.getbbox("あAg")[1]) + line_spacing))
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = (lines[-1][:-1] + "…") if lines[-1] else "…"
    return "\n".join(lines), min_font_size


def _filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def _render_caption(
    ffmpeg: str,
    project: Project,
    workdir: Path,
    output: Path,
    settings: RenderSettings,
) -> None:
    text_path = workdir / "caption.txt"
    font_path = _font_path()
    scale = settings.width / WIDTH
    line_spacing = max(8, round(24 * scale))
    caption_text, font_size = _caption_layout(
        project.caption_text.strip(),
        font_path,
        max_width=round(settings.width * 5 / 6),
        max_height=round(settings.height * 25 / 32),
        max_font_size=max(14, round(96 * scale)),
        min_font_size=max(10, round(14 * scale)),
        line_spacing=line_spacing,
    )
    text_path.write_text(caption_text, encoding="utf-8")
    frames = max(1, round(project.caption_duration * settings.fps))
    drawtext = (
        f"drawtext=fontfile='{_filter_path(font_path)}':"
        f"textfile='{_filter_path(text_path)}':fontcolor=white:fontsize={font_size}:"
        f"line_spacing={line_spacing}:x=(w-text_w)/2:y=(h-text_h)/2"
    )
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s={settings.width}x{settings.height}:r={settings.fps}",
        "-vf",
        f"{drawtext},format=yuv420p",
        "-frames:v",
        str(frames),
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        settings.preset,
        "-crf",
        str(settings.crf),
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(settings.fps),
        str(output),
    ]
    _run(command)


def build_bgm_filter(duration: float, volume: float) -> str:
    duration = max(0.2, float(duration))
    volume = max(0.0, min(float(volume), 1.0))
    fade_in = min(0.3, duration / 4)
    fade_out = min(1.5, max(0.1, duration / 3))
    fade_out_start = max(0.0, duration - fade_out)
    return ",".join(
        [
            "aresample=48000",
            "aformat=sample_fmts=fltp:channel_layouts=stereo",
            f"volume={volume:.4f}",
            f"afade=t=in:st=0:d={fade_in:.3f}",
            f"afade=t=out:st={fade_out_start:.3f}:d={fade_out:.3f}",
            f"atrim=duration={duration:.3f}",
            "asetpts=N/SR/TB",
        ]
    )


def build_cut_audio_filter(cut_duration: float, volume: float, start_time: float) -> str:
    cut_duration = max(0.0, float(cut_duration))
    volume = max(0.0, min(float(volume), 1.0))
    delay_ms = max(0, round(float(start_time) * 1000))
    return ",".join(
        [
            "aresample=48000",
            "aformat=sample_fmts=fltp:channel_layouts=stereo",
            f"volume={volume:.4f}",
            f"atrim=start=0:duration={cut_duration:.3f}",
            "asetpts=PTS-STARTPTS",
            f"adelay={delay_ms}|{delay_ms}",
        ]
    )


def _cut_audio_tracks(project: Project) -> list[tuple[Path, float, float, float]]:
    tracks: list[tuple[Path, float, float, float]] = []
    start_time = 0.0
    for cut in project.cuts:
        audio_path = Path(cut.audio_path) if cut.audio_path else None
        if (
            audio_path is not None
            and audio_path.suffix.lower() in SUPPORTED_AUDIO_SUFFIXES
            and audio_path.is_file()
        ):
            tracks.append((audio_path, start_time, cut.duration, cut.audio_volume))
        start_time += cut.duration
    return tracks


def _mux_project_audio(
    ffmpeg: str,
    video: Path,
    output: Path,
    project: Project,
    bgm: Path | None,
    cut_audio_tracks: list[tuple[Path, float, float, float]],
) -> None:
    duration = project.total_duration()
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video)]
    filters: list[str] = []
    labels: list[str] = []
    input_index = 1
    if bgm is not None:
        command.extend(["-stream_loop", "-1", "-i", str(bgm)])
        filters.append(
            f"[{input_index}:a]{build_bgm_filter(duration, project.bgm_volume)}[bgm]"
        )
        labels.append("bgm")
        input_index += 1
    for track_index, (path, start_time, cut_duration, volume) in enumerate(cut_audio_tracks):
        command.extend(["-i", str(path)])
        label = f"cut_audio_{track_index}"
        filters.append(
            f"[{input_index}:a]{build_cut_audio_filter(cut_duration, volume, start_time)}[{label}]"
        )
        labels.append(label)
        input_index += 1
    mix_inputs = "".join(f"[{label}]" for label in labels)
    filters.append(
        f"{mix_inputs}amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0,"
        f"apad=pad_dur={duration:.3f},atrim=duration={duration:.3f},asetpts=N/SR/TB[audio]"
    )
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "0:v:0",
            "-map",
            "[audio]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-t",
            f"{duration:.3f}",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    _run(command)


def export_project(
    project: Project,
    output_path: str | Path,
    progress: Callable[[str, float], None] | None = None,
    settings: RenderSettings = FINAL_RENDER,
) -> Path:
    errors = project.validate_for_export()
    if errors:
        raise ExportError("\n".join(errors))

    ffmpeg = find_ffmpeg()
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    total_segments = len(project.cuts) + (1 if project.caption_text.strip() else 0)
    report = progress or (lambda _message, _fraction: None)

    with tempfile.TemporaryDirectory(prefix="mini-log-") as temporary:
        workdir = Path(temporary)
        segments: list[Path] = []
        for index, cut in enumerate(project.cuts, start=1):
            report(f"カット {index}/{len(project.cuts)} を書き出し中…", (index - 1) / (total_segments + 1))
            segment = workdir / f"cut-{index:04d}.mp4"
            _render_cut(ffmpeg, cut, project.style, segment, settings)
            segments.append(segment)

        if project.caption_text.strip():
            report("終了キャプションを書き出し中…", len(segments) / (total_segments + 1))
            caption = workdir / "caption.mp4"
            _render_caption(ffmpeg, project, workdir, caption, settings)
            segments.append(caption)

        manifest = workdir / "concat.txt"
        manifest.write_text(
            "".join(f"file '{str(path).replace(chr(92), '/')}'\n" for path in segments),
            encoding="utf-8",
        )
        report("1本の動画にまとめています…", total_segments / (total_segments + 1))
        bgm_path = Path(project.bgm_path) if project.bgm_path else None
        has_bgm = bool(bgm_path and bgm_path.is_file())
        cut_audio_tracks = _cut_audio_tracks(project)
        has_audio = has_bgm or bool(cut_audio_tracks)
        video_output = workdir / "video-only.mp4" if has_audio else output
        _run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(manifest),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(video_output),
            ]
        )
        if has_audio:
            report("音声を追加しています…", 0.95)
            _mux_project_audio(
                ffmpeg,
                video_output,
                output,
                project,
                bgm_path if has_bgm else None,
                cut_audio_tracks,
            )
    report("書き出しが完了しました", 1.0)
    return output
