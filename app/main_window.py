from __future__ import annotations

import ctypes
import json
import logging
import os
import queue
import subprocess
import tempfile
import threading
from pathlib import Path
from tkinter import (
    BOTH,
    END,
    HORIZONTAL,
    LEFT,
    RIGHT,
    VERTICAL,
    X,
    Y,
    Canvas,
    DoubleVar,
    Frame,
    StringVar,
    Text,
    filedialog,
    messagebox,
    ttk,
)

from PIL import Image, ImageEnhance, ImageTk
from tkinterdnd2 import DND_FILES, TkinterDnD

from .exporter import (
    PREVIEW_RENDER,
    ExportError,
    build_cut_caption_panel,
    cut_caption_y,
    export_project,
    find_ffmpeg,
)
from .models import MAX_CUT_DURATION, MIN_CUT_DURATION, SUPPORTED_AUDIO_SUFFIXES, Cut, Project
from .preview_player import PreviewPlayer
from .resources import ICON_ICO, ICON_PNG
from .themes import THEME_LABELS, THEME_VALUES, Theme, get_theme
from .version import __version__


DEFAULT_THEME = get_theme("autumn")
BG = DEFAULT_THEME.background
PANEL = DEFAULT_THEME.surface
INK = DEFAULT_THEME.text
MUTED = DEFAULT_THEME.text_muted
ACCENT = DEFAULT_THEME.accent
ACCENT_DARK = DEFAULT_THEME.accent_hover
SELECTED = DEFAULT_THEME.selected_background
BORDER = DEFAULT_THEME.border
CONTROL_BG = DEFAULT_THEME.control_background
CONTROL_BORDER = DEFAULT_THEME.control_border
CARD_BG = DEFAULT_THEME.surface
DROP_BG = DEFAULT_THEME.drop_background


def enable_windows_dpi_awareness() -> str:
    """Opt out of Windows bitmap scaling before Tk creates its first window."""
    if os.name != "nt":
        return "not-windows"
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MiniLog.PhotoDiary")
    except (AttributeError, OSError):
        pass
    try:
        user32 = ctypes.windll.user32
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return "per-monitor-v2"
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return "per-monitor"
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
            return "system"
        except (AttributeError, OSError):
            return "unavailable"


def configure_root_dpi(root) -> tuple[float, float]:
    dpi = max(72.0, float(root.winfo_fpixels("1i")))
    root.tk.call("tk", "scaling", dpi / 72.0)
    width, height, min_width, min_height, display_scale = dpi_window_metrics(
        dpi, root.winfo_screenwidth(), root.winfo_screenheight()
    )
    root.geometry(f"{width}x{height}")
    root.minsize(min_width, min_height)
    return dpi, display_scale


def dpi_window_metrics(dpi: float, screen_width: int, screen_height: int) -> tuple[int, int, int, int, float]:
    display_scale = max(0.75, dpi / 96.0)
    max_width = max(960, screen_width - round(64 * display_scale))
    max_height = max(720, screen_height - round(72 * display_scale))
    width = min(round(1180 * display_scale), max_width)
    height = min(round(860 * display_scale), max_height)
    min_width = min(round(960 * display_scale), max_width)
    min_height = min(round(720 * display_scale), max_height)
    return width, height, min_width, min_height, display_scale


def next_available_mp4_name(directory: str | Path, stem: str = "mini-log") -> str:
    folder = Path(directory)
    plain = f"{stem}.mp4"
    if not (folder / plain).exists():
        return plain
    for number in range(1, 10000):
        candidate = f"{stem}-{number:03d}.mp4"
        if not (folder / candidate).exists():
            return candidate
    return f"{stem}-9999.mp4"

CUT_TYPE_LABELS = {"Still": "静止画", "Motion": "動画風"}
MOTION_TYPE_LABELS = {
    "Zoom In": "ズームイン",
    "Zoom Out": "ズームアウト",
    "Pan Left": "左へパン",
    "Pan Right": "右へパン",
}
STYLE_LABELS = {"Natural": "ナチュラル", "Soft": "ソフト", "Film": "フィルム"}
CAPTION_POSITION_LABELS = {"top": "上", "center": "中央", "bottom": "下"}
CAPTION_MOTION_LABELS = {
    "fixed": "固定",
    "fade": "フェード",
    "soft_zoom": "ふわっと拡大",
    "slide_up": "下から表示",
}
CAPTION_FONT_LABELS = {
    "gothic": "ゴシック",
    "rounded": "丸ゴシック",
    "mincho": "明朝",
    "pop": "ポップ",
}
CAPTION_SIZE_LABELS = {"small": "小", "medium": "中", "large": "大"}
NO_MOTION_LABEL = "— 静止画では使用しません"
CUT_TYPE_VALUES = {label: value for value, label in CUT_TYPE_LABELS.items()}
MOTION_TYPE_VALUES = {label: value for value, label in MOTION_TYPE_LABELS.items()}
STYLE_VALUES = {label: value for value, label in STYLE_LABELS.items()}
CAPTION_POSITION_VALUES = {label: value for value, label in CAPTION_POSITION_LABELS.items()}
CAPTION_MOTION_VALUES = {label: value for value, label in CAPTION_MOTION_LABELS.items()}
CAPTION_FONT_VALUES = {label: value for value, label in CAPTION_FONT_LABELS.items()}
CAPTION_SIZE_VALUES = {label: value for value, label in CAPTION_SIZE_LABELS.items()}
DURATION_STEP = 0.1


def clamp_cut_duration(value: float) -> float:
    return round(max(MIN_CUT_DURATION, min(float(value), MAX_CUT_DURATION)), 1)


class MiniLogApp:
    def __init__(self, root) -> None:
        self.root = root
        self.project = Project()
        self.theme: Theme = get_theme(self.project.theme)
        self.project_path: Path | None = None
        self.selected_index: int | None = None
        self.selected_cut_ids: set[str] = set()
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.cut_photos: list[ImageTk.PhotoImage] = []
        self.card_widgets: list[ttk.Frame] = []
        self.card_body_widgets: list[Frame] = []
        self.card_motion_combos: list[ttk.Combobox] = []
        self.card_selection_bars: list[ttk.Frame] = []
        self.card_duration_entries: list[ttk.Entry] = []
        self.card_duration_minus_buttons: list[ttk.Button] = []
        self.card_duration_plus_buttons: list[ttk.Button] = []
        self.card_duration_frames: list[Frame] = []
        self.drag_source_index: int | None = None
        self.drag_target_index: int | None = None
        self.drag_start_y: int | None = None
        self.drag_active = False
        self.drag_control_pressed = False
        self.export_queue: queue.Queue = queue.Queue()
        self.preview_queue: queue.Queue = queue.Queue()
        self.exporting = False
        self.preview_generating = False
        self.last_export: Path | None = None
        self.preview_temp = tempfile.TemporaryDirectory(prefix="mini-log-preview-", ignore_cleanup_errors=True)
        self.preview_path = Path(self.preview_temp.name) / "preview.mp4"
        self.preview_log_path = Path(tempfile.gettempdir()) / "mini-log-preview.log"
        self.preview_logger = logging.getLogger("mini_log.preview")
        if not self.preview_logger.handlers:
            handler = logging.FileHandler(self.preview_log_path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            self.preview_logger.addHandler(handler)
            self.preview_logger.setLevel(logging.ERROR)
        self.preview_generated_signature: str | None = None
        self.preview_generation_signature: str | None = None
        self.preview_generation_project: Project | None = None
        self.preview_project_snapshot: Project | None = None
        self._suspend_dirty = False
        self._suspend_cut_caption = False
        self._suspend_cut_audio = False
        self._suspend_theme = False
        self.raw_text_widgets: list[Text] = []
        self.window_icon: ImageTk.PhotoImage | None = None
        self.player = PreviewPlayer(
            self.root,
            self._show_preview_frame,
            self._update_playback_position,
            self._on_playback_state,
        )

        self.root.title("Mini Log — Photo Vlog Maker")
        self.dpi, self.display_scale = configure_root_dpi(self.root)
        self.root.configure(bg=self.theme.background)
        self._apply_window_icon()
        self._configure_style()
        self._build_ui()
        self._apply_theme_to_widgets()
        self._register_drop_target(self.root)
        self._register_drop_target(self.cut_canvas)
        self._register_drop_target(self.cut_list)
        self._register_drop_target(self.preview_label)
        self._refresh_all()
        self.root.bind("<Delete>", self._on_delete_key, add="+")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _apply_window_icon(self) -> None:
        try:
            if ICON_PNG.is_file():
                with Image.open(ICON_PNG) as icon_image:
                    self.window_icon = ImageTk.PhotoImage(icon_image.convert("RGBA"))
                self.root.iconphoto(True, self.window_icon)
        except (OSError, ValueError):
            self.window_icon = None
        try:
            if os.name == "nt" and ICON_ICO.is_file():
                self.root.iconbitmap(str(ICON_ICO))
        except (OSError, ValueError):
            pass

    def _configure_style(self) -> None:
        theme = self.theme
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", font=("Yu Gothic UI", 10), foreground=theme.text)
        style.configure("TFrame", background=theme.background)
        style.configure("TPanedwindow", background=theme.background, sashwidth=10)
        style.configure("Header.TFrame", background=theme.surface_alt)
        style.configure("Panel.TFrame", background=theme.surface)
        style.configure("Surface.TFrame", background=theme.surface, relief="solid", borderwidth=1, bordercolor=theme.border)
        style.configure("Card.TFrame", background=theme.surface, relief="solid", borderwidth=1, bordercolor=theme.border)
        style.configure("SelectedCard.TFrame", background=theme.selected_background, relief="solid", borderwidth=1, bordercolor=theme.selected_border)
        style.configure("DropTargetCard.TFrame", background=theme.accent_soft, relief="solid", borderwidth=2, bordercolor=theme.accent)
        style.configure("DropZone.TFrame", background=theme.drop_background, relief="solid", borderwidth=1, bordercolor=theme.control_border)
        style.configure("TLabel", background=theme.background, foreground=theme.text)
        style.configure("Header.TLabel", background=theme.surface_alt, foreground=theme.text)
        style.configure("HeaderMuted.TLabel", background=theme.surface_alt, foreground=theme.text_muted)
        style.configure("Panel.TLabel", background=theme.surface, foreground=theme.text)
        style.configure("Card.TLabel", background=theme.surface, foreground=theme.text)
        style.configure("CardMuted.TLabel", background=theme.surface, foreground=theme.text_muted)
        style.configure("DropZone.TLabel", background=theme.drop_background, foreground=theme.text)
        style.configure("DropZoneMuted.TLabel", background=theme.drop_background, foreground=theme.text_muted)
        style.configure("SelectedCard.TLabel", background=theme.selected_background, foreground=theme.text)
        style.configure("SelectedCardMuted.TLabel", background=theme.selected_background, foreground=theme.text_muted)
        style.configure("SelectionBar.TFrame", background=theme.accent)
        style.configure("SelectionBarOff.TFrame", background=theme.surface)
        style.configure("DragHandle.TLabel", background=theme.surface, foreground=theme.text_muted, font=("Yu Gothic UI", 15))
        style.configure("SelectedDragHandle.TLabel", background=theme.selected_background, foreground=theme.accent_hover, font=("Yu Gothic UI", 15))
        style.configure("Muted.TLabel", background=theme.background, foreground=theme.text_muted)
        style.configure("PanelMuted.TLabel", background=theme.surface, foreground=theme.text_muted)
        style.configure("AccentMuted.TLabel", background=theme.surface, foreground=theme.stale_text)
        style.configure("Title.TLabel", font=("Yu Gothic UI", 23, "bold"), background=theme.surface_alt, foreground=theme.text)
        style.configure("Section.TLabel", font=("Yu Gothic UI", 12, "bold"), background=theme.surface, foreground=theme.text)
        style.configure(
            "TButton",
            background=theme.control_background,
            foreground=theme.text,
            bordercolor=theme.control_border,
            lightcolor=theme.control_background,
            darkcolor=theme.control_background,
            relief="solid",
            borderwidth=1,
            padding=(10, 7),
        )
        style.map(
            "TButton",
            background=[("active", theme.accent_soft), ("pressed", theme.surface_alt), ("disabled", theme.control_background)],
            foreground=[("disabled", theme.text_muted)],
            bordercolor=[("focus", theme.accent)],
        )
        style.configure(
            "Accent.TButton",
            background=theme.accent,
            foreground="white",
            bordercolor=theme.accent_hover,
            lightcolor=theme.accent,
            darkcolor=theme.accent,
            padding=(16, 9),
        )
        style.map("Accent.TButton", background=[("active", theme.accent_hover), ("disabled", theme.border)])
        style.configure(
            "TCombobox",
            padding=4,
            fieldbackground=theme.surface,
            background=theme.surface,
            foreground=theme.text,
            bordercolor=theme.control_border,
            lightcolor=theme.surface,
            darkcolor=theme.surface,
            arrowcolor=theme.text,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", theme.surface), ("disabled", theme.control_background)],
            foreground=[("readonly", theme.text), ("disabled", theme.text_muted)],
            bordercolor=[("focus", theme.accent)],
        )
        style.configure(
            "TSpinbox",
            fieldbackground=theme.surface,
            foreground=theme.text,
            bordercolor=theme.control_border,
            lightcolor=theme.surface,
            darkcolor=theme.surface,
            arrowcolor=theme.text,
        )
        style.map("TSpinbox", bordercolor=[("focus", theme.accent)])
        style.configure("Horizontal.TScale", troughcolor=theme.progress_trough, background=theme.accent, bordercolor=theme.surface)
        style.configure("Horizontal.TProgressbar", troughcolor=theme.progress_trough, background=theme.accent)
        style.configure("Strong.Horizontal.TSeparator", background=theme.border)

    def _apply_theme_to_widgets(self) -> None:
        theme = self.theme
        self.root.configure(bg=theme.background)
        if hasattr(self, "cut_canvas"):
            self.cut_canvas.configure(bg=theme.surface)
        if hasattr(self, "right_canvas"):
            self.right_canvas.configure(bg=theme.surface)
        for widget in self.raw_text_widgets:
            widget.configure(
                background=theme.surface,
                foreground=theme.text,
                insertbackground=theme.text,
                selectbackground=theme.accent_soft,
                selectforeground=theme.text,
                highlightbackground=theme.control_border,
                highlightcolor=theme.accent,
            )
        for index, widget in enumerate(self.card_body_widgets):
            selected = (
                index < len(self.project.cuts)
                and self.project.cuts[index].id in self.selected_cut_ids
            )
            widget.configure(
                background=theme.selected_background if selected else theme.surface
            )
        for index, widget in enumerate(self.card_duration_frames):
            selected = (
                index < len(self.project.cuts)
                and self.project.cuts[index].id in self.selected_cut_ids
            )
            widget.configure(
                background=theme.selected_background if selected else theme.surface
            )

    def _apply_theme(self, key: str) -> None:
        self.theme = get_theme(key)
        self._configure_style()
        self._apply_theme_to_widgets()

    def _on_theme_changed(self, _event=None) -> None:
        if self._suspend_theme:
            return
        key = THEME_VALUES.get(self.theme_var.get(), "autumn")
        self.project.theme = key
        self._apply_theme(key)
        self.status_var.set(f"テーマを「{self.theme.label}」に変更しました")

    def _build_ui(self) -> None:
        header = ttk.Frame(self.root, style="Header.TFrame", padding=(24, 17, 24, 14))
        header.pack(fill=X)
        title_box = ttk.Frame(header, style="Header.TFrame")
        title_box.pack(side=LEFT)
        ttk.Label(title_box, text="Mini Log", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="写真を並べて、一日の小さな記録に。", style="HeaderMuted.TLabel").pack(anchor="w")

        actions = ttk.Frame(header, style="Header.TFrame")
        actions.pack(side=RIGHT)
        ttk.Button(actions, text="このアプリについて", command=self.show_about).pack(side=LEFT, padx=3)
        ttk.Button(actions, text="プロジェクトを開く", command=self.open_project).pack(side=LEFT, padx=3)
        ttk.Button(actions, text="プロジェクトを保存", command=self.save_project).pack(side=LEFT, padx=3)
        ttk.Button(actions, text="画像を追加", style="Accent.TButton", command=self.add_images).pack(side=LEFT, padx=(12, 3))

        theme_box = ttk.Frame(header, style="Header.TFrame")
        theme_box.pack(side=RIGHT, padx=(0, 16))
        ttk.Label(theme_box, text="テーマ", style="HeaderMuted.TLabel").pack(side=LEFT, padx=(0, 7))
        self.theme_var = StringVar(value=THEME_LABELS[self.project.theme])
        self.theme_combo = ttk.Combobox(
            theme_box,
            textvariable=self.theme_var,
            values=tuple(THEME_LABELS.values()),
            state="readonly",
            width=5,
        )
        self.theme_combo.pack(side=LEFT)
        self.theme_combo.bind("<<ComboboxSelected>>", self._on_theme_changed)

        self.paned = ttk.Panedwindow(self.root, orient=HORIZONTAL)
        self.paned.pack(fill=BOTH, expand=True, padx=24, pady=(0, 14))

        left = ttk.Frame(self.paned, style="Surface.TFrame", padding=14)
        right_shell = ttk.Frame(self.paned, style="Surface.TFrame")
        self.paned.add(left, weight=3)
        self.paned.add(right_shell, weight=2)
        right_footer = ttk.Frame(right_shell, style="Panel.TFrame", padding=(18, 8, 18, 18))
        right_footer.pack(side="bottom", fill=X)

        left_head = ttk.Frame(left, style="Panel.TFrame")
        left_head.pack(fill=X, pady=(0, 10))
        ttk.Label(left_head, text="カット", style="Section.TLabel").pack(side=LEFT)
        self.cut_count_label = ttk.Label(left_head, text="0カット / 0.0秒", style="PanelMuted.TLabel")
        self.cut_count_label.pack(side=LEFT, padx=8)
        ttk.Button(left_head, text="おまかせで作る", command=self.auto_compose).pack(side=RIGHT)

        self.cut_canvas = Canvas(left, bg=PANEL, highlightthickness=0)
        scrollbar = ttk.Scrollbar(left, orient=VERTICAL, command=self.cut_canvas.yview)
        self.cut_list = ttk.Frame(self.cut_canvas, style="Panel.TFrame")
        self.cut_window = self.cut_canvas.create_window((0, 0), window=self.cut_list, anchor="nw")
        self.cut_canvas.configure(yscrollcommand=scrollbar.set)
        self.cut_list.bind("<Configure>", lambda _event: self.cut_canvas.configure(scrollregion=self.cut_canvas.bbox("all")))
        self.cut_canvas.bind("<Configure>", lambda event: self.cut_canvas.itemconfigure(self.cut_window, width=event.width))
        self.cut_canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.cut_canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        self.right_canvas = Canvas(right_shell, bg=PANEL, highlightthickness=0)
        right_scrollbar = ttk.Scrollbar(right_shell, orient=VERTICAL, command=self.right_canvas.yview)
        right = ttk.Frame(self.right_canvas, style="Panel.TFrame", padding=18)
        self.right_window = self.right_canvas.create_window((0, 0), window=right, anchor="nw")
        right.bind(
            "<Configure>",
            lambda _event: self.right_canvas.configure(scrollregion=self.right_canvas.bbox("all")),
        )
        self.right_canvas.bind(
            "<Configure>",
            lambda event: self.right_canvas.itemconfigure(self.right_window, width=event.width),
        )
        self.right_canvas.configure(yscrollcommand=right_scrollbar.set)
        self.right_canvas.pack(side=LEFT, fill=BOTH, expand=True)
        right_scrollbar.pack(side=RIGHT, fill=Y)
        self._build_right_panel(right)
        self._build_export_panel(right_footer)

        footer = ttk.Frame(self.root, padding=(24, 0, 24, 18))
        footer.pack(fill=X)
        self.status_var = StringVar(value="画像を追加して始めましょう")
        ttk.Label(footer, textvariable=self.status_var, style="Muted.TLabel").pack(side=LEFT)
        self.progress_box = ttk.Frame(footer)
        self.progress_text_var = StringVar(value="処理中…")
        ttk.Label(
            self.progress_box,
            textvariable=self.progress_text_var,
            style="Muted.TLabel",
        ).pack(side=LEFT, padx=(0, 8))
        self.progress = ttk.Progressbar(self.progress_box, length=220, maximum=100)
        self.progress.pack(side=RIGHT)

    def show_about(self) -> None:
        messagebox.showinfo(
            "Mini Logについて",
            f"Mini Log\nVersion {__version__}\n\n写真を並べて、一日の小さな記録に。",
            parent=self.root,
        )

    def _show_progress(self, text: str = "処理中…") -> None:
        self.progress_text_var.set(text)
        self.progress["value"] = 0
        if not self.progress_box.winfo_manager():
            self.progress_box.pack(side=RIGHT, padx=(10, 0))

    def _hide_progress(self) -> None:
        self.progress_box.pack_forget()

    def _build_right_panel(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="プレビュー", style="Section.TLabel").pack(anchor="w")
        self.preview_label = ttk.Label(
            parent,
            text="カットを選ぶとここに表示されます\n画像のドロップでも追加できます",
            anchor="center",
            justify="center",
            style="PanelMuted.TLabel",
        )
        self.preview_label.pack(fill=BOTH, expand=True, pady=(8, 8))
        self.preview_meta = ttk.Label(parent, text="", style="PanelMuted.TLabel")
        self.preview_meta.pack(anchor="center", pady=(0, 6))

        self.preview_state_var = StringVar(value="プレビューはまだありません")
        self.preview_state_label = ttk.Label(
            parent,
            textvariable=self.preview_state_var,
            style="AccentMuted.TLabel",
        )
        self.preview_state_label.pack(anchor="center")
        self.preview_time_var = StringVar(value="00:00 / 00:00")
        ttk.Label(parent, textvariable=self.preview_time_var, style="Panel.TLabel").pack(anchor="center", pady=(2, 7))

        self.preview_create_button = ttk.Button(parent, text="プレビューを作成", command=self.start_preview)
        self.preview_create_button.pack(fill=X, pady=(0, 6))
        playback = ttk.Frame(parent, style="Panel.TFrame")
        playback.pack(fill=X, pady=(0, 12))
        self.preview_play_button = ttk.Button(playback, text="▶ 再生", command=self.play_preview, state="disabled")
        self.preview_play_button.pack(side=LEFT, fill=X, expand=True, padx=(0, 3))
        self.preview_stop_button = ttk.Button(playback, text="■ 停止", command=self.stop_preview, state="disabled")
        self.preview_stop_button.pack(side=LEFT, fill=X, expand=True, padx=3)
        self.preview_from_cut_button = ttk.Button(
            playback,
            text="ここから再生",
            command=lambda: self.play_preview(from_selected=True),
            state="disabled",
        )
        self.preview_from_cut_button.pack(side=LEFT, fill=X, expand=True, padx=(3, 0))

        self.total_duration_var = StringVar(value="動画の長さ：0.0秒")
        ttk.Label(parent, textvariable=self.total_duration_var, style="Panel.TLabel").pack(anchor="w", pady=(0, 10))
        ttk.Separator(parent, orient=HORIZONTAL, style="Strong.Horizontal.TSeparator").pack(
            fill=X, pady=(0, 12)
        )
        ttk.Label(parent, text="カットキャプション", style="Section.TLabel").pack(anchor="w", pady=(0, 5))
        cut_caption = ttk.Frame(parent, style="Panel.TFrame")
        cut_caption.pack(fill=X, pady=(0, 8))
        ttk.Label(cut_caption, text="テキスト", style="Panel.TLabel").grid(row=0, column=0, sticky="nw", pady=4)
        self.cut_caption_text = Text(
            cut_caption,
            height=2,
            wrap="word",
            font=("Yu Gothic UI", 10),
            background=self.theme.surface,
            foreground=self.theme.text,
            insertbackground=self.theme.text,
            selectbackground=self.theme.accent_soft,
            selectforeground=self.theme.text,
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.theme.control_border,
            highlightcolor=self.theme.accent,
        )
        self.raw_text_widgets.append(self.cut_caption_text)
        self.cut_caption_text.grid(row=0, column=1, columnspan=3, sticky="ew", padx=(12, 0), pady=4)
        self.cut_caption_text.bind("<KeyRelease>", self._on_cut_caption_text_edited)

        ttk.Label(cut_caption, text="位置", style="Panel.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        self.cut_caption_position_var = StringVar(value=CAPTION_POSITION_LABELS["bottom"])
        self.cut_caption_position_combo = ttk.Combobox(
            cut_caption,
            textvariable=self.cut_caption_position_var,
            values=tuple(CAPTION_POSITION_LABELS.values()),
            state="readonly",
            width=8,
        )
        self.cut_caption_position_combo.grid(row=1, column=1, sticky="w", padx=(12, 10), pady=4)
        self.cut_caption_position_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._on_cut_caption_style_edited("caption_position"),
        )
        ttk.Label(cut_caption, text="表示", style="Panel.TLabel").grid(row=1, column=2, sticky="w", pady=4)
        self.cut_caption_motion_var = StringVar(value=CAPTION_MOTION_LABELS["fade"])
        self.cut_caption_motion_combo = ttk.Combobox(
            cut_caption,
            textvariable=self.cut_caption_motion_var,
            values=tuple(CAPTION_MOTION_LABELS.values()),
            state="readonly",
            width=12,
        )
        self.cut_caption_motion_combo.grid(row=1, column=3, sticky="ew", padx=(8, 0), pady=4)
        self.cut_caption_motion_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._on_cut_caption_style_edited("caption_motion"),
        )

        ttk.Label(cut_caption, text="フォント", style="Panel.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        self.cut_caption_font_var = StringVar(value=CAPTION_FONT_LABELS["gothic"])
        self.cut_caption_font_combo = ttk.Combobox(
            cut_caption,
            textvariable=self.cut_caption_font_var,
            values=tuple(CAPTION_FONT_LABELS.values()),
            state="readonly",
            width=8,
        )
        self.cut_caption_font_combo.grid(row=2, column=1, sticky="w", padx=(12, 10), pady=4)
        self.cut_caption_font_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._on_cut_caption_style_edited("caption_font"),
        )
        ttk.Label(cut_caption, text="文字サイズ", style="Panel.TLabel").grid(row=2, column=2, sticky="w", pady=4)
        self.cut_caption_size_var = StringVar(value=CAPTION_SIZE_LABELS["medium"])
        self.cut_caption_size_combo = ttk.Combobox(
            cut_caption,
            textvariable=self.cut_caption_size_var,
            values=tuple(CAPTION_SIZE_LABELS.values()),
            state="readonly",
            width=8,
        )
        self.cut_caption_size_combo.grid(row=2, column=3, sticky="ew", padx=(8, 0), pady=4)
        self.cut_caption_size_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._on_cut_caption_style_edited("caption_size"),
        )
        cut_caption.columnconfigure(3, weight=1)

        ttk.Separator(parent, orient=HORIZONTAL, style="Strong.Horizontal.TSeparator").pack(
            fill=X, pady=(6, 12)
        )
        ttk.Label(parent, text="カット音声", style="Section.TLabel").pack(anchor="w", pady=(0, 5))
        cut_audio = ttk.Frame(parent, style="Panel.TFrame")
        cut_audio.pack(fill=X, pady=(0, 8))
        self.cut_audio_name_var = StringVar(value="未設定")
        self.cut_audio_name_label = ttk.Label(
            cut_audio,
            textvariable=self.cut_audio_name_var,
            style="PanelMuted.TLabel",
        )
        self.cut_audio_name_label.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        self.cut_audio_timing_label = ttk.Label(
            cut_audio,
            text="カット開始と同時に再生します",
            style="PanelMuted.TLabel",
        )
        self.cut_audio_timing_label.grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 6))
        self.cut_audio_select_button = ttk.Button(
            cut_audio,
            text="音声を選択",
            command=self.choose_cut_audio,
            state="disabled",
        )
        self.cut_audio_select_button.grid(row=2, column=0, sticky="w")
        self.cut_audio_remove_button = ttk.Button(
            cut_audio,
            text="削除",
            command=self.remove_cut_audio,
            state="disabled",
        )
        self.cut_audio_remove_button.grid(row=2, column=1, sticky="w", padx=(7, 0))
        volume_row = ttk.Frame(cut_audio, style="Panel.TFrame")
        volume_row.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Label(volume_row, text="音量", style="Panel.TLabel").pack(side=LEFT)
        self.cut_audio_volume_var = DoubleVar(value=60.0)
        self.cut_audio_volume_scale = ttk.Scale(
            volume_row,
            from_=0,
            to=100,
            variable=self.cut_audio_volume_var,
            command=self._on_cut_audio_volume_changed,
            state="disabled",
        )
        self.cut_audio_volume_scale.pack(side=LEFT, fill=X, expand=True, padx=(12, 8))
        self.cut_audio_volume_label_var = StringVar(value="60%")
        ttk.Label(
            volume_row,
            textvariable=self.cut_audio_volume_label_var,
            style="Panel.TLabel",
            width=5,
        ).pack(side=RIGHT)
        cut_audio.columnconfigure(2, weight=1)

        ttk.Separator(parent, orient=HORIZONTAL, style="Strong.Horizontal.TSeparator").pack(
            fill=X, pady=(6, 12)
        )
        ttk.Label(parent, text="全体設定", style="Section.TLabel").pack(anchor="w", pady=(0, 5))
        settings = ttk.Frame(parent, style="Panel.TFrame")
        settings.pack(fill=X)
        ttk.Label(settings, text="スタイル", style="Panel.TLabel").grid(row=0, column=0, sticky="w", pady=5)
        self.style_var = StringVar(value=STYLE_LABELS["Natural"])
        style_combo = ttk.Combobox(
            settings,
            textvariable=self.style_var,
            values=tuple(STYLE_LABELS.values()),
            state="readonly",
            width=15,
        )
        style_combo.grid(row=0, column=1, sticky="ew", padx=(14, 0), pady=5)
        style_combo.bind("<<ComboboxSelected>>", self._on_style_changed)

        ttk.Label(settings, text="終了キャプション", style="Panel.TLabel").grid(row=1, column=0, sticky="nw", pady=5)
        self.caption_text = Text(
            settings,
            height=3,
            wrap="word",
            font=("Yu Gothic UI", 10),
            background=self.theme.surface,
            foreground=self.theme.text,
            insertbackground=self.theme.text,
            selectbackground=self.theme.accent_soft,
            selectforeground=self.theme.text,
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.theme.control_border,
            highlightcolor=self.theme.accent,
        )
        self.raw_text_widgets.append(self.caption_text)
        self.caption_text.grid(row=1, column=1, sticky="ew", padx=(14, 0), pady=5)
        self.caption_text.bind("<KeyRelease>", self._on_project_settings_edited)

        ttk.Label(settings, text="表示時間", style="Panel.TLabel").grid(row=2, column=0, sticky="w", pady=5)
        self.caption_duration_var = StringVar(value="2.0")
        duration = ttk.Spinbox(settings, from_=0.2, to=60, increment=0.1, textvariable=self.caption_duration_var, width=8)
        duration.grid(row=2, column=1, sticky="w", padx=(14, 0), pady=5)
        duration.bind("<FocusOut>", self._on_project_settings_edited)
        duration.bind("<KeyRelease>", self._on_project_settings_edited)
        self.caption_duration_var.trace_add("write", lambda *_args: self._on_project_settings_edited())
        settings.columnconfigure(1, weight=1)

        ttk.Separator(parent, orient=HORIZONTAL, style="Strong.Horizontal.TSeparator").pack(
            fill=X, pady=(12, 12)
        )
        ttk.Label(parent, text="BGM", style="Section.TLabel").pack(anchor="w", pady=(0, 5))
        self.bgm_box = ttk.Frame(parent, style="DropZone.TFrame", padding=10)
        self.bgm_box.pack(fill=X)
        self.bgm_name_var = StringVar(value="未設定")
        self.bgm_name_label = ttk.Label(
            self.bgm_box,
            textvariable=self.bgm_name_var,
            style="DropZoneMuted.TLabel",
            justify="left",
        )
        self.bgm_name_label.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 7))
        self.bgm_select_button = ttk.Button(self.bgm_box, text="ファイルを選択", command=self.choose_bgm)
        self.bgm_select_button.grid(row=1, column=0, sticky="w")
        self.bgm_remove_button = ttk.Button(self.bgm_box, text="削除", command=self.remove_bgm, state="disabled")
        self.bgm_remove_button.grid(row=1, column=1, sticky="w", padx=(7, 0))
        ttk.Label(self.bgm_box, text="音声ファイルをここにドロップ", style="DropZoneMuted.TLabel").grid(
            row=1, column=2, sticky="e"
        )
        self.bgm_box.columnconfigure(2, weight=1)
        volume_row = ttk.Frame(parent, style="Panel.TFrame")
        volume_row.pack(fill=X, pady=(7, 0))
        ttk.Label(volume_row, text="音量", style="Panel.TLabel").pack(side=LEFT)
        self.bgm_volume_var = DoubleVar(value=60.0)
        self.bgm_volume_scale = ttk.Scale(
            volume_row,
            from_=0,
            to=100,
            variable=self.bgm_volume_var,
            command=self._on_bgm_volume_changed,
        )
        self.bgm_volume_scale.pack(side=LEFT, fill=X, expand=True, padx=(12, 8))
        self.bgm_volume_label_var = StringVar(value="60%")
        ttk.Label(volume_row, textvariable=self.bgm_volume_label_var, style="Panel.TLabel", width=5).pack(side=RIGHT)
        for widget in (self.bgm_box, self.bgm_name_label):
            self._register_bgm_drop_target(widget)

    def _build_export_panel(self, parent: ttk.Frame) -> None:
        ttk.Separator(parent, orient=HORIZONTAL, style="Strong.Horizontal.TSeparator").pack(
            fill=X, pady=(0, 10)
        )
        export_box = ttk.Frame(parent, style="Panel.TFrame")
        export_box.pack(fill=X)
        ttk.Label(export_box, text="書き出し", style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            export_box,
            text="すべてのカットと全体設定を1本の動画にします",
            style="PanelMuted.TLabel",
        ).pack(anchor="w", pady=(2, 8))
        self.export_button = ttk.Button(export_box, text="MP4を書き出す", style="Accent.TButton", command=self.start_export)
        self.export_button.pack(fill=X)
        self.result_actions = ttk.Frame(export_box, style="Panel.TFrame")
        ttk.Button(self.result_actions, text="再生", command=self.play_export).pack(side=LEFT, fill=X, expand=True, padx=(0, 4))
        ttk.Button(self.result_actions, text="保存場所を開く", command=self.open_export_folder).pack(side=LEFT, fill=X, expand=True, padx=(4, 0))

    def _on_mousewheel(self, event) -> None:
        if (
            self.right_canvas.winfo_rootx()
            <= event.x_root
            < self.right_canvas.winfo_rootx() + self.right_canvas.winfo_width()
            and self.right_canvas.winfo_rooty()
            <= event.y_root
            < self.right_canvas.winfo_rooty() + self.right_canvas.winfo_height()
        ):
            self.right_canvas.yview_scroll(int(-event.delta / 120), "units")
            return
        if self.cut_canvas.winfo_exists():
            self.cut_canvas.yview_scroll(int(-event.delta / 120), "units")

    @staticmethod
    def _format_time(seconds: float, decimal: bool = False) -> str:
        seconds = max(0.0, seconds)
        minutes = int(seconds // 60)
        remainder = seconds - minutes * 60
        if decimal:
            return f"{minutes:02d}:{remainder:04.1f}"
        return f"{minutes:02d}:{int(remainder):02d}"

    def _project_signature(self) -> str:
        render_data = self.project.to_dict()
        render_data.pop("theme", None)
        return json.dumps(render_data, ensure_ascii=False, sort_keys=True)

    def _update_duration_display(self, position: float | None = None) -> None:
        total = self.project.total_duration()
        self.total_duration_var.set(f"動画の長さ：{total:.1f}秒")
        self.cut_count_label.configure(
            text=f"{len(self.project.cuts)}カット / {sum(cut.duration for cut in self.project.cuts):.1f}秒"
        )
        if position is not None:
            playback_total = self.player.duration if self.player.playing else total
            self.preview_time_var.set(
                f"{self._format_time(position)} / {self._format_time(playback_total, decimal=True)}"
            )
        elif not self.player.playing:
            self.preview_time_var.set(f"00:00 / {self._format_time(total, decimal=True)}")

    def _mark_preview_stale(self) -> None:
        if self._suspend_dirty:
            return
        self._update_duration_display()
        if self.preview_generating:
            self.preview_state_var.set("プレビューを作成中…（編集内容が変更されました）")
            return
        if self.preview_generated_signature is not None and self.preview_path.is_file():
            self.preview_state_var.set("このプレビューは現在の編集内容と異なります")
            self.preview_create_button.configure(text="プレビューを更新")
        else:
            self.preview_state_var.set("プレビューはまだありません")
            self.preview_create_button.configure(text="プレビューを作成")

    def _on_project_settings_edited(self, _event=None) -> None:
        if self._suspend_dirty:
            return
        self._sync_project_settings()
        self._mark_preview_stale()

    def _load_selected_cut_caption(self) -> None:
        self._refresh_cut_audio_display()
        self._suspend_cut_caption = True
        try:
            self.cut_caption_text.configure(state="normal")
            self.cut_caption_text.delete("1.0", END)
            if self.selected_index is None or not (0 <= self.selected_index < len(self.project.cuts)):
                self.cut_caption_position_var.set(CAPTION_POSITION_LABELS["bottom"])
                self.cut_caption_motion_var.set(CAPTION_MOTION_LABELS["fade"])
                self.cut_caption_font_var.set(CAPTION_FONT_LABELS["gothic"])
                self.cut_caption_size_var.set(CAPTION_SIZE_LABELS["medium"])
                self.cut_caption_text.configure(state="disabled")
                self.cut_caption_position_combo.configure(state="disabled")
                self.cut_caption_motion_combo.configure(state="disabled")
                self.cut_caption_font_combo.configure(state="disabled")
                self.cut_caption_size_combo.configure(state="disabled")
                return
            cut = self.project.cuts[self.selected_index]
            self.cut_caption_text.insert("1.0", cut.caption_text)
            self.cut_caption_position_var.set(
                CAPTION_POSITION_LABELS.get(cut.caption_position, CAPTION_POSITION_LABELS["bottom"])
            )
            self.cut_caption_motion_var.set(
                CAPTION_MOTION_LABELS.get(cut.caption_motion, CAPTION_MOTION_LABELS["fade"])
            )
            self.cut_caption_font_var.set(
                CAPTION_FONT_LABELS.get(cut.caption_font, CAPTION_FONT_LABELS["gothic"])
            )
            self.cut_caption_size_var.set(
                CAPTION_SIZE_LABELS.get(cut.caption_size, CAPTION_SIZE_LABELS["medium"])
            )
            self.cut_caption_position_combo.configure(state="readonly")
            self.cut_caption_motion_combo.configure(state="readonly")
            self.cut_caption_font_combo.configure(state="readonly")
            self.cut_caption_size_combo.configure(state="readonly")
        finally:
            self._suspend_cut_caption = False

    def _on_cut_caption_text_edited(self, _event=None) -> None:
        if self._suspend_cut_caption:
            return
        if self.selected_index is None or not (0 <= self.selected_index < len(self.project.cuts)):
            return
        cut = self.project.cuts[self.selected_index]
        updated = self.cut_caption_text.get("1.0", END).rstrip("\n")
        if updated != cut.caption_text:
            cut.caption_text = updated
            self._mark_preview_stale()
            self._refresh_preview()

    def _selected_caption_cuts(self) -> list[Cut]:
        selected = [cut for cut in self.project.cuts if cut.id in self.selected_cut_ids]
        if selected:
            return selected
        if self.selected_index is not None and 0 <= self.selected_index < len(self.project.cuts):
            return [self.project.cuts[self.selected_index]]
        return []

    def _on_cut_caption_style_edited(self, field: str, _event=None) -> None:
        if self._suspend_cut_caption:
            return
        values = {
            "caption_position": CAPTION_POSITION_VALUES.get(
                self.cut_caption_position_var.get(), "bottom"
            ),
            "caption_motion": CAPTION_MOTION_VALUES.get(
                self.cut_caption_motion_var.get(), "fade"
            ),
            "caption_font": CAPTION_FONT_VALUES.get(
                self.cut_caption_font_var.get(), "gothic"
            ),
            "caption_size": CAPTION_SIZE_VALUES.get(
                self.cut_caption_size_var.get(), "medium"
            ),
        }
        if field not in values:
            return
        targets = self._selected_caption_cuts()
        value = values[field]
        changed = False
        for cut in targets:
            if getattr(cut, field) != value:
                setattr(cut, field, value)
                changed = True
        if changed:
            self._mark_preview_stale()
            self._refresh_preview()
            labels = {
                "caption_position": "位置",
                "caption_motion": "表示",
                "caption_font": "フォント",
                "caption_size": "文字サイズ",
            }
            self.status_var.set(f"{len(targets)}カットのCaption {labels[field]}を変更しました")

    def _on_cut_caption_edited(self, _event=None) -> None:
        """Compatibility helper for tests and callers that update all Caption controls."""
        self._on_cut_caption_text_edited(_event)
        for field in ("caption_position", "caption_motion", "caption_font", "caption_size"):
            self._on_cut_caption_style_edited(field, _event)

    def _active_cut(self) -> Cut | None:
        if self.selected_index is None or not (0 <= self.selected_index < len(self.project.cuts)):
            return None
        return self.project.cuts[self.selected_index]

    def _refresh_cut_audio_display(self) -> None:
        cut = self._active_cut()
        self._suspend_cut_audio = True
        try:
            if cut is None:
                self.cut_audio_name_var.set("カットを選択してください")
                self.cut_audio_select_button.configure(text="音声を選択", state="disabled")
                self.cut_audio_remove_button.configure(state="disabled")
                self.cut_audio_volume_scale.configure(state="disabled")
                self.cut_audio_volume_var.set(60.0)
                self.cut_audio_volume_label_var.set("60%")
                return
            percent = max(0, min(round(cut.audio_volume * 100), 100))
            self.cut_audio_volume_var.set(percent)
            self.cut_audio_volume_label_var.set(f"{percent}%")
            self.cut_audio_select_button.configure(state="normal")
            if cut.audio_path:
                path = Path(cut.audio_path)
                if path.is_file():
                    self.cut_audio_name_var.set(path.name)
                else:
                    self.cut_audio_name_var.set(f"{path.name}（カット音声ファイルが見つかりません）")
                self.cut_audio_select_button.configure(text="変更")
                self.cut_audio_remove_button.configure(state="normal")
                self.cut_audio_volume_scale.configure(state="normal")
            else:
                self.cut_audio_name_var.set("未設定")
                self.cut_audio_select_button.configure(text="音声を選択")
                self.cut_audio_remove_button.configure(state="disabled")
                self.cut_audio_volume_scale.configure(state="disabled")
        finally:
            self._suspend_cut_audio = False

    def choose_cut_audio(self) -> None:
        if self._active_cut() is None:
            return
        path = filedialog.askopenfilename(
            title="カット音声を選択",
            filetypes=[
                ("音声", "*.wav *.mp3 *.m4a *.aac"),
                ("すべてのファイル", "*.*"),
            ],
        )
        if path:
            self._set_cut_audio_path(Path(path))

    def _set_cut_audio_path(self, path: Path) -> None:
        cut = self._active_cut()
        if cut is None:
            return
        if path.suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES or not path.is_file():
            messagebox.showerror(
                "カット音声を設定できません",
                "WAV / MP3 / M4A / AACファイルを選択してください。",
            )
            return
        cut.audio_path = str(path.resolve())
        self._refresh_cut_audio_display()
        self._mark_preview_stale()
        self.status_var.set(f"カット {self.selected_index + 1:02d} に音声を設定しました: {path.name}")

    def remove_cut_audio(self) -> None:
        cut = self._active_cut()
        if cut is None or not cut.audio_path:
            return
        cut.audio_path = None
        self._refresh_cut_audio_display()
        self._mark_preview_stale()
        self.status_var.set(f"カット {self.selected_index + 1:02d} の音声を削除しました")

    def _on_cut_audio_volume_changed(self, value=None) -> None:
        if self._suspend_cut_audio:
            return
        cut = self._active_cut()
        if cut is None:
            return
        try:
            percent = max(
                0,
                min(round(float(value if value is not None else self.cut_audio_volume_var.get())), 100),
            )
        except (TypeError, ValueError):
            return
        self.cut_audio_volume_label_var.set(f"{percent}%")
        volume = percent / 100
        if abs(cut.audio_volume - volume) > 0.0001:
            cut.audio_volume = volume
            self._mark_preview_stale()

    def _register_drop_target(self, widget) -> None:
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", self._on_files_dropped)

    def _on_files_dropped(self, event):
        try:
            paths = list(self.root.tk.splitlist(event.data))
        except Exception:
            paths = [event.data]
        if paths and all(Path(path).suffix.lower() in SUPPORTED_AUDIO_SUFFIXES for path in paths):
            self.status_var.set("音声ファイルは右側のBGM欄へドロップしてください")
        else:
            self._add_image_paths(paths, source="ドロップ")
        return getattr(event, "action", None)

    def _register_bgm_drop_target(self, widget) -> None:
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", self._on_bgm_dropped)

    def _on_bgm_dropped(self, event):
        try:
            paths = list(self.root.tk.splitlist(event.data))
        except Exception:
            paths = [event.data]
        selected = next(
            (
                Path(path)
                for path in paths
                if Path(path).suffix.lower() in SUPPORTED_AUDIO_SUFFIXES and Path(path).is_file()
            ),
            None,
        )
        if selected is None:
            self.status_var.set("MP3 / WAV / M4A / AACをドロップしてください")
        else:
            self._set_bgm_path(selected)
        return getattr(event, "action", None)

    def choose_bgm(self) -> None:
        path = filedialog.askopenfilename(
            title="BGMを選択",
            filetypes=[
                ("音声", "*.mp3 *.wav *.m4a *.aac"),
                ("すべてのファイル", "*.*"),
            ],
        )
        if path:
            self._set_bgm_path(Path(path))

    def _set_bgm_path(self, path: Path) -> None:
        if path.suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES or not path.is_file():
            messagebox.showerror("BGMを設定できません", "MP3 / WAV / M4A / AACファイルを選択してください。")
            return
        self.project.bgm_path = str(path.resolve())
        self._refresh_bgm_display()
        self._mark_preview_stale()
        self.status_var.set(f"BGMを設定しました: {path.name}")

    def remove_bgm(self) -> None:
        if not self.project.bgm_path:
            return
        self.project.bgm_path = None
        self._refresh_bgm_display()
        self._mark_preview_stale()
        self.status_var.set("BGMを削除しました")

    def _refresh_bgm_display(self) -> None:
        if not self.project.bgm_path:
            self.bgm_name_var.set("未設定")
            self.bgm_select_button.configure(text="ファイルを選択")
            self.bgm_remove_button.configure(state="disabled")
            return
        path = Path(self.project.bgm_path)
        if path.is_file():
            self.bgm_name_var.set(path.name)
        else:
            self.bgm_name_var.set(f"{path.name}\nBGMファイルが見つかりません")
        self.bgm_select_button.configure(text="変更")
        self.bgm_remove_button.configure(state="normal")

    def _on_bgm_volume_changed(self, value=None) -> None:
        if self._suspend_dirty:
            return
        try:
            percent = max(0, min(round(float(value if value is not None else self.bgm_volume_var.get())), 100))
        except (TypeError, ValueError):
            return
        self.bgm_volume_label_var.set(f"{percent}%")
        volume = percent / 100
        if abs(self.project.bgm_volume - volume) > 0.0001:
            self.project.bgm_volume = volume
            self._mark_preview_stale()

    def _add_image_paths(self, paths, source: str = "選択") -> int:
        first_new_index = len(self.project.cuts)
        count = self.project.add_images(paths)
        if count:
            self.selected_index = first_new_index
            self.selected_cut_ids = {self.project.cuts[first_new_index].id}
            self.status_var.set(f"{source}した画像を{count}枚追加しました")
            self._mark_preview_stale()
            self._refresh_all()
        else:
            self.status_var.set("追加できる新しい画像はありませんでした")
        return count

    def add_images(self) -> None:
        paths = filedialog.askopenfilenames(
            title="画像を追加",
            filetypes=[("画像", "*.jpg *.jpeg *.png *.webp"), ("すべてのファイル", "*.*")],
        )
        if not paths:
            return
        self._add_image_paths(paths)

    @staticmethod
    def _apply_preview_style(image: Image.Image, style: str) -> Image.Image:
        if style == "Soft":
            image = ImageEnhance.Brightness(image).enhance(1.05)
            image = ImageEnhance.Contrast(image).enhance(0.92)
            return ImageEnhance.Color(image).enhance(0.90)
        if style == "Film":
            image = ImageEnhance.Contrast(image).enhance(0.95)
            image = ImageEnhance.Color(image).enhance(0.95)
            red, green, blue = image.split()
            red = red.point(lambda value: min(255, int(value * 0.98 + 8)))
            green = green.point(lambda value: min(255, int(value * 0.96 + 7)))
            blue = blue.point(lambda value: min(255, int(value * 0.93 + 6)))
            image = Image.merge("RGB", (red, green, blue))
            grain_layer = Image.new("L", image.size)
            grain_layer.putdata([
                128 + ((x * 17 + y * 31) % 9) - 4
                for y in range(image.height)
                for x in range(image.width)
            ])
            grain = Image.merge("RGB", (grain_layer, grain_layer, grain_layer))
            return Image.blend(image, grain, 0.018)
        return image

    def _make_thumbnail(
        self,
        path: str,
        size: tuple[int, int],
        style: str | None = None,
        cut: Cut | None = None,
    ) -> ImageTk.PhotoImage:
        with Image.open(path) as image:
            image = image.convert("RGB")
            target_ratio = size[0] / size[1]
            source_ratio = image.width / image.height
            if source_ratio > target_ratio:
                crop_width = int(image.height * target_ratio)
                left = (image.width - crop_width) // 2
                image = image.crop((left, 0, left + crop_width, image.height))
            else:
                crop_height = int(image.width / target_ratio)
                top = (image.height - crop_height) // 2
                image = image.crop((0, top, image.width, top + crop_height))
            image.thumbnail(size, Image.Resampling.LANCZOS)
            if style:
                image = self._apply_preview_style(image, style)
            if cut is not None and cut.caption_text.strip():
                image = image.convert("RGBA")
                panel = build_cut_caption_panel(
                    cut.caption_text,
                    image.width,
                    image.height,
                    cut.caption_font,
                    cut.caption_size,
                )
                x = (image.width - panel.width) // 2
                y = cut_caption_y(cut.caption_position, image.height, panel.height)
                image.alpha_composite(panel, (x, y))
                image = image.convert("RGB")
            return ImageTk.PhotoImage(image)

    def _refresh_all(self) -> None:
        self._normalize_cut_selection()
        self._suspend_theme = True
        try:
            self.theme_var.set(THEME_LABELS.get(self.project.theme, THEME_LABELS["autumn"]))
            self._apply_theme(self.project.theme)
        finally:
            self._suspend_theme = False
        self._suspend_dirty = True
        try:
            self.style_var.set(STYLE_LABELS.get(self.project.style, STYLE_LABELS["Natural"]))
            self.caption_text.delete("1.0", END)
            self.caption_text.insert("1.0", self.project.caption_text)
            self.caption_duration_var.set(f"{self.project.caption_duration:.1f}")
            self.bgm_volume_var.set(self.project.bgm_volume * 100)
            self.bgm_volume_label_var.set(f"{round(self.project.bgm_volume * 100)}%")
        finally:
            self._suspend_dirty = False
        self._refresh_bgm_display()
        self._refresh_cut_list()
        self._load_selected_cut_caption()
        self._refresh_preview()
        self._update_duration_display()

    def _refresh_cut_list(self) -> None:
        for child in self.cut_list.winfo_children():
            child.destroy()
        self.cut_photos.clear()
        self.card_widgets.clear()
        self.card_body_widgets.clear()
        self.card_motion_combos.clear()
        self.card_selection_bars.clear()
        self.card_duration_entries.clear()
        self.card_duration_minus_buttons.clear()
        self.card_duration_plus_buttons.clear()
        self.card_duration_frames.clear()
        self.cut_count_label.configure(
            text=f"{len(self.project.cuts)}カット / {sum(cut.duration for cut in self.project.cuts):.1f}秒"
        )

        if not self.project.cuts:
            empty = ttk.Frame(self.cut_list, style="DropZone.TFrame", padding=(24, 90))
            empty.pack(fill=BOTH, expand=True, padx=3, pady=3)
            ttk.Label(
                empty,
                text="画像をここにドロップ",
                font=("Yu Gothic UI", 15, "bold"),
                style="DropZone.TLabel",
            ).pack()
            ttk.Label(empty, text="または", style="DropZoneMuted.TLabel").pack(pady=(8, 4))
            ttk.Button(empty, text="画像を選択", command=self.add_images).pack()
            self._register_drop_target(empty)
            return

        for index, cut in enumerate(self.project.cuts):
            self._build_cut_card(index, cut)

    def _build_cut_card(self, index: int, cut: Cut) -> None:
        selected = cut.id in self.selected_cut_ids
        active = index == self.selected_index
        frame_style = "SelectedCard.TFrame" if selected else "Card.TFrame"
        body_background = self.theme.selected_background if selected else self.theme.surface
        label_style = "SelectedCard.TLabel" if selected else "Card.TLabel"
        muted_style = "SelectedCardMuted.TLabel" if selected else "CardMuted.TLabel"
        card = ttk.Frame(self.cut_list, padding=9, style=frame_style)
        card.pack(fill=X, pady=(0, 8))
        self.card_widgets.append(card)
        selection_bar = ttk.Frame(
            card,
            width=4,
            style="SelectionBar.TFrame" if active else "SelectionBarOff.TFrame",
        )
        selection_bar.pack(side=LEFT, fill=Y, padx=(0, 8))
        self.card_selection_bars.append(selection_bar)
        inner = Frame(card, background=body_background, borderwidth=0, highlightthickness=0)
        inner.pack(side=LEFT, fill=X, expand=True)
        self.card_body_widgets.append(inner)

        handle = ttk.Label(
            inner,
            text="⠿",
            width=2,
            cursor="fleur",
            style="SelectedDragHandle.TLabel" if selected else "DragHandle.TLabel",
        )
        handle.grid(row=0, column=0, rowspan=4, sticky="ns", padx=(0, 3))
        number = ttk.Label(inner, text=f"{index + 1:02d}", width=3, style=label_style)
        number.grid(row=0, column=1, rowspan=4, sticky="n", padx=(0, 5))
        try:
            photo = self._make_thumbnail(cut.source_path, (68, 88))
            self.cut_photos.append(photo)
            thumb = ttk.Label(inner, image=photo, style=label_style)
        except Exception:
            thumb = ttk.Label(inner, text="画像なし", width=9, style=muted_style)
        thumb.grid(row=0, column=2, rowspan=4, padx=(0, 12))

        type_label = ttk.Label(inner, text="種類", style=muted_style)
        type_label.grid(row=0, column=3, sticky="w", padx=(0, 5))
        type_var = StringVar(value=CUT_TYPE_LABELS.get(cut.type, CUT_TYPE_LABELS["Still"]))
        type_combo = ttk.Combobox(
            inner,
            values=tuple(CUT_TYPE_LABELS.values()),
            textvariable=type_var,
            state="readonly",
            width=10,
        )
        type_combo.grid(row=0, column=4, sticky="w", pady=2)

        duration_label = ttk.Label(inner, text="表示時間", style=muted_style)
        duration_label.grid(row=1, column=3, sticky="w", padx=(0, 5))
        duration_var = StringVar(value=f"{cut.duration:.1f}")
        duration_controls = Frame(
            inner,
            background=body_background,
            borderwidth=0,
            highlightthickness=0,
        )
        duration_controls.grid(row=1, column=4, columnspan=2, sticky="w", pady=2)
        self.card_duration_frames.append(duration_controls)
        duration_minus = ttk.Button(
            duration_controls,
            text="−",
            width=3,
            cursor="arrow",
            command=lambda: adjust_duration(-DURATION_STEP),
        )
        duration_minus.pack(side=LEFT)
        duration_entry = ttk.Entry(
            duration_controls,
            textvariable=duration_var,
            width=6,
            justify="center",
            cursor="xterm",
        )
        duration_entry.pack(side=LEFT, padx=(5, 4))
        ttk.Label(duration_controls, text="秒", style=muted_style).pack(side=LEFT, padx=(0, 5))
        duration_plus = ttk.Button(
            duration_controls,
            text="＋",
            width=3,
            cursor="arrow",
            command=lambda: adjust_duration(DURATION_STEP),
        )
        duration_plus.pack(side=LEFT)
        self.card_duration_entries.append(duration_entry)
        self.card_duration_minus_buttons.append(duration_minus)
        self.card_duration_plus_buttons.append(duration_plus)

        motion_label = ttk.Label(inner, text="動き", style=muted_style)
        motion_label.grid(row=2, column=3, sticky="w", padx=(0, 5))
        motion_var = StringVar(
            value=(
                MOTION_TYPE_LABELS.get(cut.motion_type, MOTION_TYPE_LABELS["Zoom In"])
                if cut.type == "Motion"
                else NO_MOTION_LABEL
            )
        )
        motion_combo = ttk.Combobox(
            inner,
            values=tuple(MOTION_TYPE_LABELS.values()) if cut.type == "Motion" else (NO_MOTION_LABEL,),
            textvariable=motion_var,
            state="readonly",
            width=21,
        )
        motion_combo.grid(row=2, column=4, columnspan=2, sticky="w", pady=2)
        self.card_motion_combos.append(motion_combo)
        if cut.type == "Still":
            motion_combo.configure(state="disabled")

        ttk.Button(inner, text="削除", width=5, command=lambda i=index: self.remove_cut(i)).grid(
            row=0,
            column=6,
            rowspan=4,
            sticky="ne",
            padx=(12, 0),
        )
        inner.columnconfigure(6, weight=1)

        def update_cut(_event=None) -> None:
            before = (cut.type, cut.duration, cut.motion_type)
            previous_type = cut.type
            cut.type = CUT_TYPE_VALUES.get(type_var.get(), "Still")
            if cut.type == "Motion":
                cut.motion_type = MOTION_TYPE_VALUES.get(motion_var.get(), cut.motion_type)
            if cut.type != previous_type:
                cut.duration = 3.0 if cut.type == "Motion" else 1.5
                self._refresh_cut_list()
            self.selected_index = index
            self.selected_cut_ids.add(cut.id)
            if before != (cut.type, cut.duration, cut.motion_type):
                self._mark_preview_stale()
            self._load_selected_cut_caption()
            self._refresh_preview()

        def commit_duration(_event=None):
            try:
                value = clamp_cut_duration(float(duration_var.get()))
            except ValueError:
                duration_var.set(f"{cut.duration:.1f}")
                return "break"
            duration_var.set(f"{value:.1f}")
            if abs(cut.duration - value) > 0.0001:
                cut.duration = value
                self.selected_index = index
                self.selected_cut_ids.add(cut.id)
                self._mark_preview_stale()
                self._load_selected_cut_caption()
                self._refresh_preview()
                self.status_var.set(f"カット {index + 1:02d} の表示時間を {value:.1f}秒に変更しました")
            return "break" if _event is not None and getattr(_event, "keysym", "") == "Return" else None

        def adjust_duration(delta: float) -> None:
            try:
                base = float(duration_var.get())
            except ValueError:
                base = cut.duration
            duration_var.set(f"{clamp_cut_duration(base + delta):.1f}")
            commit_duration()

        type_combo.bind("<<ComboboxSelected>>", update_cut)
        motion_combo.bind("<<ComboboxSelected>>", update_cut)
        duration_entry.bind("<FocusOut>", commit_duration)
        duration_entry.bind("<Return>", commit_duration)
        drag_widgets = (
            card,
            selection_bar,
            inner,
            handle,
            number,
            thumb,
            type_label,
            duration_label,
            motion_label,
        )
        for widget in drag_widgets:
            widget.configure(cursor="fleur")
            widget.bind("<ButtonPress-1>", lambda event, i=index: self._begin_card_drag(event, i))
            widget.bind("<B1-Motion>", self._continue_card_drag)
            widget.bind("<ButtonRelease-1>", self._end_card_drag)

    def _begin_card_drag(self, event, index: int) -> None:
        self.drag_source_index = index
        self.drag_target_index = index
        self.drag_start_y = event.y_root
        self.drag_active = False
        self.drag_control_pressed = bool(getattr(event, "state", 0) & 0x0004)

    def _drag_insertion_index(self, pointer_y: int) -> int:
        for index, card in enumerate(self.card_widgets):
            midpoint = card.winfo_rooty() + card.winfo_height() / 2
            if pointer_y < midpoint:
                return index
        return len(self.card_widgets)

    def _continue_card_drag(self, event) -> None:
        if self.drag_source_index is None:
            return
        if not self.drag_active:
            if self.drag_start_y is None or abs(event.y_root - self.drag_start_y) < 7:
                return
            self.drag_active = True
            self._select_single_cut(self.drag_source_index, refresh=False)
            self.status_var.set(f"カット {self.drag_source_index + 1:02d} を移動中…")
        insertion = self._drag_insertion_index(event.y_root)
        target = insertion
        if target > self.drag_source_index:
            target -= 1
        target = max(0, min(target, len(self.card_widgets) - 1))
        if target == self.drag_target_index:
            return
        self.drag_target_index = target
        for index, card in enumerate(self.card_widgets):
            if index == target:
                card.configure(style="DropTargetCard.TFrame")
            elif self.project.cuts[index].id in self.selected_cut_ids:
                card.configure(style="SelectedCard.TFrame")
            else:
                card.configure(style="Card.TFrame")

    def _end_card_drag(self, event) -> None:
        if self.drag_source_index is None:
            return
        source = self.drag_source_index
        was_dragged = self.drag_active
        control_pressed = self.drag_control_pressed
        self.drag_source_index = None
        self.drag_target_index = None
        self.drag_start_y = None
        self.drag_active = False
        self.drag_control_pressed = False
        if not was_dragged:
            self.select_cut(source, additive=control_pressed)
            return
        insertion = self._drag_insertion_index(event.y_root)
        if insertion > source:
            insertion -= 1
        self.selected_index = self.project.move_to(source, insertion)
        self.status_var.set(f"カットを {self.selected_index + 1:02d} 番へ移動しました")
        self._mark_preview_stale()
        self._refresh_cut_list()
        self._load_selected_cut_caption()
        self._refresh_preview()

    def _normalize_cut_selection(self) -> None:
        existing_ids = {cut.id for cut in self.project.cuts}
        self.selected_cut_ids.intersection_update(existing_ids)
        if self.selected_index is not None and not (0 <= self.selected_index < len(self.project.cuts)):
            self.selected_index = None
        if self.selected_index is not None:
            self.selected_cut_ids.add(self.project.cuts[self.selected_index].id)
        elif self.selected_cut_ids:
            self.selected_index = next(
                index for index, cut in enumerate(self.project.cuts) if cut.id in self.selected_cut_ids
            )

    def _select_single_cut(self, index: int, refresh: bool = True) -> None:
        if not (0 <= index < len(self.project.cuts)):
            return
        self.selected_index = index
        self.selected_cut_ids = {self.project.cuts[index].id}
        if refresh:
            self._refresh_cut_list()
            self._load_selected_cut_caption()
            self._refresh_preview()

    def _nearest_selected_index(self, origin: int) -> int | None:
        selected_indices = [
            index for index, cut in enumerate(self.project.cuts) if cut.id in self.selected_cut_ids
        ]
        if not selected_indices:
            return None
        return min(selected_indices, key=lambda index: (abs(index - origin), index < origin, index))

    def select_cut(self, index: int, additive: bool = False) -> None:
        if not (0 <= index < len(self.project.cuts)):
            return
        cut_id = self.project.cuts[index].id
        if not additive:
            self.selected_cut_ids = {cut_id}
            self.selected_index = index
        elif cut_id in self.selected_cut_ids:
            self.selected_cut_ids.remove(cut_id)
            if self.selected_index == index:
                self.selected_index = self._nearest_selected_index(index)
        else:
            self.selected_cut_ids.add(cut_id)
            self.selected_index = index
        self._refresh_cut_list()
        self._load_selected_cut_caption()
        self._refresh_preview()
        count = len(self.selected_cut_ids)
        if count:
            active_number = self.selected_index + 1 if self.selected_index is not None else index + 1
            self.status_var.set(
                f"カット {active_number:02d} を選択しました"
                if count == 1
                else f"{count}カットを選択中（カット {active_number:02d} が編集対象）"
            )
        else:
            self.status_var.set("カットの選択を解除しました")

    def move_cut(self, index: int, offset: int) -> None:
        cut_id = self.project.cuts[index].id if 0 <= index < len(self.project.cuts) else None
        self.selected_index = self.project.move(index, offset)
        self.selected_cut_ids = {cut_id} if cut_id is not None else set()
        if self.selected_index != index:
            self._mark_preview_stale()
        self._refresh_cut_list()
        self._load_selected_cut_caption()
        self._refresh_preview()

    def remove_cut(self, index: int) -> None:
        if not (0 <= index < len(self.project.cuts)):
            return
        active_id = (
            self.project.cuts[self.selected_index].id
            if self.selected_index is not None and 0 <= self.selected_index < len(self.project.cuts)
            else None
        )
        if self.project.cuts[index].id == active_id and len(self.selected_cut_ids) > 1:
            cut_ids = set(self.selected_cut_ids)
        else:
            cut_ids = {self.project.cuts[index].id}
        self._request_cut_deletion(cut_ids)

    def _request_cut_deletion(self, cut_ids: set[str]) -> bool:
        existing_ids = {cut.id for cut in self.project.cuts}
        cut_ids = set(cut_ids) & existing_ids
        if not cut_ids:
            return False
        if len(cut_ids) > 1 and not messagebox.askokcancel(
            "カットを削除",
            f"{len(cut_ids)}カットを削除しますか？",
            icon="warning",
            parent=self.root,
        ):
            return False
        self._delete_cut_ids(cut_ids)
        return True

    def _delete_cut_ids(self, cut_ids: set[str]) -> None:
        if not cut_ids:
            return
        active_index = self.selected_index if self.selected_index is not None else 0
        next_active_id = next(
            (
                cut.id
                for cut in self.project.cuts[active_index + 1 :]
                if cut.id not in cut_ids
            ),
            None,
        )
        if next_active_id is None:
            next_active_id = next(
                (
                    cut.id
                    for cut in reversed(self.project.cuts[:active_index])
                    if cut.id not in cut_ids
                ),
                None,
            )
        removed_count = sum(cut.id in cut_ids for cut in self.project.cuts)
        self.project.cuts = [cut for cut in self.project.cuts if cut.id not in cut_ids]
        self.project.reindex()
        self.selected_cut_ids = {next_active_id} if next_active_id is not None else set()
        self.selected_index = next(
            (index for index, cut in enumerate(self.project.cuts) if cut.id == next_active_id),
            None,
        )
        self._mark_preview_stale()
        self._refresh_all()
        self.status_var.set(f"{removed_count}カットを削除しました")

    @staticmethod
    def _is_text_editing_widget(widget) -> bool:
        if widget is None:
            return False
        try:
            return widget.winfo_class() in {"Text", "Entry", "TEntry", "TSpinbox", "TCombobox"}
        except Exception:
            return False

    def _on_delete_key(self, _event=None):
        if self._is_text_editing_widget(self.root.focus_get()):
            return None
        if self.selected_index is None or not self.selected_cut_ids:
            return None
        self._request_cut_deletion(set(self.selected_cut_ids))
        return "break"

    def _refresh_preview(self) -> None:
        if self.selected_index is None or not (0 <= self.selected_index < len(self.project.cuts)):
            self.preview_photo = None
            self.preview_label.configure(image="", text="カットを選ぶとここに表示されます\n画像のドロップでも追加できます")
            self.preview_meta.configure(text="")
            return
        cut = self.project.cuts[self.selected_index]
        try:
            photo = self._make_thumbnail(cut.source_path, (180, 320), style=self.project.style, cut=cut)
            self.preview_photo = photo
            self.preview_label.configure(image=photo, text="")
        except Exception as exc:
            self.preview_photo = None
            self.preview_label.configure(image="", text=f"画像を表示できません\n{exc}")
        type_label = CUT_TYPE_LABELS.get(cut.type, cut.type)
        motion = f" · {MOTION_TYPE_LABELS.get(cut.motion_type, cut.motion_type)}" if cut.type == "Motion" else ""
        style = STYLE_LABELS.get(self.project.style, self.project.style)
        self.preview_meta.configure(text=f"{type_label}{motion} · {cut.duration:.1f}秒 · {style}")

    def _on_style_changed(self, _event=None) -> None:
        self._sync_project_settings()
        self._mark_preview_stale()
        self._refresh_preview()
        self.status_var.set(f"スタイルを「{self.style_var.get()}」に変更しました")

    def auto_compose(self) -> None:
        if not self.project.cuts:
            messagebox.showinfo("Mini Log", "先に画像を追加してください。")
            return
        self.project.auto_compose()
        self.selected_index = 0
        self.selected_cut_ids = {self.project.cuts[0].id}
        self.status_var.set("おまかせ構成を適用しました")
        self._mark_preview_stale()
        self._refresh_cut_list()
        self._load_selected_cut_caption()
        self._refresh_preview()

    def _sync_project_settings(self) -> None:
        self.project.style = STYLE_VALUES.get(self.style_var.get(), "Natural")
        self.project.caption_text = self.caption_text.get("1.0", END).rstrip("\n")
        try:
            self.project.caption_duration = float(self.caption_duration_var.get())
        except ValueError:
            pass
        self.project.bgm_volume = max(0.0, min(self.bgm_volume_var.get() / 100, 1.0))

    def start_preview(self) -> None:
        if self.preview_generating or self.exporting:
            return
        self._sync_project_settings()
        errors = self.project.validate_for_export()
        if errors:
            messagebox.showerror("プレビューを作成できません", "\n".join(errors))
            return
        try:
            find_ffmpeg()
        except ExportError as exc:
            messagebox.showerror("FFmpegが必要です", str(exc))
            return

        self.stop_preview()
        snapshot = Project.from_dict(self.project.to_dict())
        self.preview_generation_project = snapshot
        self.preview_generation_signature = self._project_signature()
        self.preview_generating = True
        self.preview_state_var.set("プレビューを作成中…")
        self.preview_create_button.configure(state="disabled", text="プレビューを作成中…")
        self.preview_play_button.configure(state="disabled")
        self.preview_stop_button.configure(state="disabled")
        self.preview_from_cut_button.configure(state="disabled")
        self.export_button.configure(state="disabled")
        self._show_progress("プレビュー作成中…")

        def worker() -> None:
            try:
                result = export_project(
                    snapshot,
                    self.preview_path,
                    progress=lambda message, fraction: self.preview_queue.put(
                        ("progress", message, fraction)
                    ),
                    settings=PREVIEW_RENDER,
                )
                self.preview_queue.put(("done", result))
            except Exception as exc:
                self.preview_queue.put(("error", exc))

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(100, self._poll_preview)

    def _poll_preview(self) -> None:
        try:
            while True:
                item = self.preview_queue.get_nowait()
                if item[0] == "progress":
                    _, message, fraction = item
                    self.status_var.set(f"プレビューを作成中… {message}")
                    self.progress["value"] = fraction * 100
                elif item[0] == "done":
                    self.preview_generating = False
                    self.preview_project_snapshot = self.preview_generation_project
                    self.preview_generated_signature = self.preview_generation_signature
                    self.preview_create_button.configure(state="normal")
                    self.export_button.configure(state="normal")
                    self.preview_play_button.configure(state="normal")
                    self.preview_from_cut_button.configure(state="normal")
                    self.progress["value"] = 100
                    self._hide_progress()
                    if self.preview_generated_signature == self._project_signature():
                        self.preview_state_var.set("プレビューの準備ができました")
                        self.preview_create_button.configure(text="プレビューを更新")
                    else:
                        self.preview_state_var.set("このプレビューは現在の編集内容と異なります")
                        self.preview_create_button.configure(text="プレビューを更新")
                    self.status_var.set("プレビューを作成しました")
                    self._update_duration_display(0.0)
                    return
                elif item[0] == "error":
                    self.preview_generating = False
                    error = item[1]
                    self.preview_logger.error(
                        "Preview generation failed",
                        exc_info=(type(error), error, error.__traceback__),
                    )
                    self.preview_create_button.configure(state="normal", text="プレビューを作成")
                    self.export_button.configure(state="normal")
                    self.preview_state_var.set("プレビューの作成に失敗しました")
                    self.status_var.set("プレビューの作成に失敗しました")
                    self._hide_progress()
                    messagebox.showerror("Mini Log", "プレビューの作成に失敗しました。")
                    return
        except queue.Empty:
            pass
        if self.preview_generating:
            self.root.after(100, self._poll_preview)

    def play_preview(self, from_selected: bool = False) -> None:
        if not self.preview_path.is_file() or self.preview_project_snapshot is None:
            return
        start = 0.0
        if from_selected and self.selected_index is not None:
            start = self.preview_project_snapshot.cut_start_time(self.selected_index)
        self.player.play(self.preview_path, start, self.preview_project_snapshot.total_duration())

    def stop_preview(self) -> None:
        self.player.stop()
        self._update_playback_position(0.0)
        self._refresh_preview()

    def _show_preview_frame(self, data: bytes, width: int, height: int) -> None:
        image = Image.frombytes("RGB", (width, height), data)
        self.preview_photo = ImageTk.PhotoImage(image)
        self.preview_label.configure(image=self.preview_photo, text="")

    def _update_playback_position(self, seconds: float) -> None:
        total = self.player.duration or self.project.total_duration()
        self.preview_time_var.set(
            f"{self._format_time(seconds)} / {self._format_time(total, decimal=True)}"
        )

    def _on_playback_state(self, playing: bool) -> None:
        if playing:
            self.preview_play_button.configure(state="disabled")
            self.preview_stop_button.configure(state="normal")
            self.preview_from_cut_button.configure(state="disabled")
        else:
            has_preview = self.preview_path.is_file()
            self.preview_play_button.configure(state="normal" if has_preview else "disabled")
            self.preview_stop_button.configure(state="disabled")
            self.preview_from_cut_button.configure(state="normal" if has_preview else "disabled")

    def _reset_preview(self) -> None:
        self.player.stop()
        self.preview_generated_signature = None
        self.preview_generation_signature = None
        self.preview_generation_project = None
        self.preview_project_snapshot = None
        try:
            self.preview_path.unlink(missing_ok=True)
        except OSError:
            pass
        self.preview_state_var.set("プレビューはまだありません")
        self.preview_create_button.configure(text="プレビューを作成", state="normal")
        self.preview_play_button.configure(state="disabled")
        self.preview_stop_button.configure(state="disabled")
        self.preview_from_cut_button.configure(state="disabled")
        self._update_duration_display(0.0)
        if not self.preview_generating and not self.exporting:
            self._hide_progress()

    def save_project(self) -> None:
        self._sync_project_settings()
        if not self.project_path:
            path = filedialog.asksaveasfilename(
                title="Mini Logプロジェクトを保存",
                defaultextension=".minilog",
                filetypes=[("Mini Log Project", "*.minilog")],
            )
            if not path:
                return
            self.project_path = Path(path)
        try:
            self.project.save(self.project_path)
            self.status_var.set(f"保存しました: {self.project_path.name}")
        except OSError as exc:
            messagebox.showerror("保存できませんでした", str(exc))

    def open_project(self) -> None:
        path = filedialog.askopenfilename(
            title="Mini Logプロジェクトを開く",
            filetypes=[("Mini Log Project", "*.minilog"), ("JSON", "*.json")],
        )
        if not path:
            return
        try:
            self.project = Project.load(path)
            self._reset_preview()
            self.project_path = Path(path)
            self.selected_index = 0 if self.project.cuts else None
            self.selected_cut_ids = {self.project.cuts[0].id} if self.project.cuts else set()
            self.status_var.set(f"開きました: {self.project_path.name}")
            self._refresh_all()
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showerror("プロジェクトを開けませんでした", str(exc))

    def start_export(self) -> None:
        if self.exporting or self.preview_generating:
            return
        self._sync_project_settings()
        errors = self.project.validate_for_export()
        if errors:
            messagebox.showerror("書き出せません", "\n".join(errors))
            return
        try:
            find_ffmpeg()
        except ExportError as exc:
            messagebox.showerror("FFmpegが必要です", str(exc))
            return
        initial_directory = (
            self.last_export.parent
            if self.last_export is not None
            else self.project_path.parent
            if self.project_path is not None
            else Path.cwd()
        )
        path = filedialog.asksaveasfilename(
            title="MP4を書き出す",
            defaultextension=".mp4",
            initialdir=str(initial_directory),
            initialfile=next_available_mp4_name(initial_directory),
            filetypes=[("MP4 Video", "*.mp4")],
        )
        if not path:
            return
        self.exporting = True
        self.export_button.configure(state="disabled", text="書き出し中…")
        self.preview_create_button.configure(state="disabled")
        self.result_actions.pack_forget()
        self._show_progress("書き出し中…")
        self.status_var.set("書き出しを準備しています…")

        snapshot = Project.from_dict(self.project.to_dict())

        def worker() -> None:
            try:
                result = export_project(
                    snapshot,
                    path,
                    progress=lambda message, fraction: self.export_queue.put(("progress", message, fraction)),
                )
                self.export_queue.put(("done", result))
            except Exception as exc:
                self.export_queue.put(("error", exc))

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(100, self._poll_export)

    def _poll_export(self) -> None:
        try:
            while True:
                item = self.export_queue.get_nowait()
                if item[0] == "progress":
                    _, message, fraction = item
                    self.status_var.set(message)
                    self.progress["value"] = fraction * 100
                elif item[0] == "done":
                    self.exporting = False
                    self.last_export = Path(item[1])
                    self.export_button.configure(state="normal", text="MP4を書き出す")
                    self.preview_create_button.configure(state="normal")
                    self.progress["value"] = 100
                    self._hide_progress()
                    self.status_var.set(f"書き出し完了: {self.last_export}")
                    self.result_actions.pack(fill=X, pady=(8, 0))
                    messagebox.showinfo("書き出し完了", f"MP4を保存しました。\n\n{self.last_export}")
                    return
                elif item[0] == "error":
                    self.exporting = False
                    self.export_button.configure(state="normal", text="MP4を書き出す")
                    self.preview_create_button.configure(state="normal")
                    self.status_var.set("書き出しに失敗しました")
                    self._hide_progress()
                    messagebox.showerror("書き出しに失敗しました", str(item[1]))
                    return
        except queue.Empty:
            pass
        if self.exporting:
            self.root.after(100, self._poll_export)

    def play_export(self) -> None:
        if self.last_export and self.last_export.is_file():
            os.startfile(self.last_export)

    def open_export_folder(self) -> None:
        if self.last_export and self.last_export.is_file():
            subprocess.Popen(["explorer", "/select,", str(self.last_export)])

    def _on_close(self) -> None:
        self.player.close()
        try:
            self.preview_temp.cleanup()
        except OSError:
            pass
        self.root.destroy()


def run() -> None:
    enable_windows_dpi_awareness()
    root = TkinterDnD.Tk()
    MiniLogApp(root)
    root.mainloop()
