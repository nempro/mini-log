"""Windows Tk acceptance for seasonal themes, icon, DPI, and preview layout."""

from __future__ import annotations

import ctypes
import json
import sys
import tempfile
from pathlib import Path
from ctypes import wintypes

from PIL import Image, ImageGrab
from tkinter import ttk
from tkinterdnd2 import TkinterDnD

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main_window import MiniLogApp, enable_windows_dpi_awareness
from app.models import Cut, Project
from app.resources import ICON_ICO, ICON_PNG
from app.themes import THEMES
from tests.phase1b_acceptance import make_inputs


ARTIFACTS = ROOT / "output" / "phase1e-acceptance"


def _window_icon_handles(root) -> list[int]:
    if sys.platform != "win32":
        return []
    user32 = ctypes.windll.user32
    window = root.winfo_id()
    windows = [window]
    parent = int(user32.GetParent(window))
    if parent:
        windows.append(parent)
    wm_geticon = 0x007F
    handles = [
        int(user32.SendMessageW(candidate, wm_geticon, size, 0))
        for candidate in windows
        for size in (0, 1, 2)
    ]
    if hasattr(user32, "GetClassLongPtrW"):
        handles.extend(
            int(user32.GetClassLongPtrW(candidate, index))
            for candidate in windows
            for index in (-14, -34)
        )
    return handles


def _native_window_rect(root) -> tuple[int, int, int, int] | None:
    if sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32
    window = int(user32.GetParent(root.winfo_id())) or root.winfo_id()
    rect = wintypes.RECT()
    if not user32.GetWindowRect(window, ctypes.byref(rect)):
        return None
    return rect.left, rect.top, rect.right, rect.bottom


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    awareness = enable_windows_dpi_awareness()
    root = TkinterDnD.Tk()
    root.withdraw()
    app = MiniLogApp(root)
    paths = make_inputs()
    app.project = Project(
        cuts=[
            Cut(str(path), type="Motion" if index % 2 == 0 else "Still", caption_text=f"今日の記録 {index + 1}")
            for index, path in enumerate(paths)
        ],
        theme="autumn",
    )
    app.selected_index = 0
    app._refresh_all()
    root.deiconify()
    root.lift()
    root.attributes("-topmost", True)
    root.update_idletasks()
    root.update()

    assert ICON_PNG.is_file() and ICON_ICO.is_file()
    assert app.window_icon is not None
    icon_handles = _window_icon_handles(root)
    assert any(icon_handles), icon_handles
    assert not hasattr(app, "notebook_decoration")
    render_signature = app._project_signature()
    app.preview_state_var.set("プレビューの準備ができました")
    preview_state = app.preview_state_var.get()
    style = ttk.Style(root)
    theme_results: dict[str, dict] = {}
    layout_size: tuple[int, int] | None = None

    for key, theme in THEMES.items():
        app.theme_var.set(theme.label)
        app._on_theme_changed()
        root.update_idletasks()
        root.update()
        current_size = (root.winfo_width(), root.winfo_height())
        if layout_size is None:
            layout_size = current_size
        assert current_size == layout_size
        assert app.project.theme == key
        assert app._project_signature() == render_signature
        assert app.preview_state_var.get() == preview_state
        assert style.lookup("Accent.TButton", "background") == theme.accent
        assert style.lookup("SelectionBar.TFrame", "background") == theme.accent
        assert style.lookup("SelectedCard.TFrame", "background") == theme.selected_background
        assert style.lookup("DropZone.TFrame", "background") == theme.drop_background
        assert style.lookup("Horizontal.TProgressbar", "background") == theme.accent
        assert app.cut_caption_text.cget("highlightcolor") == theme.accent

        x, y = root.winfo_rootx(), root.winfo_rooty()
        width, height = current_size
        screenshot = ImageGrab.grab(bbox=(x, y, x + width, y + height), all_screens=True)
        screenshot.save(ARTIFACTS / f"theme-{key}.png")
        if key == "autumn":
            native_rect = _native_window_rect(root)
            if native_rect is not None:
                ImageGrab.grab(bbox=native_rect, all_screens=True).save(
                    ARTIFACTS / "window-autumn-with-icon.png"
                )
        theme_results[key] = {
            "label": theme.label,
            "accent": theme.accent,
            "background": theme.background,
            "selected_background": theme.selected_background,
            "window_size": list(current_size),
        }

    with tempfile.TemporaryDirectory(prefix="minilog-phase1e-") as folder:
        project_path = Path(folder) / "theme.minilog"
        app.project.save(project_path)
        restored = Project.load(project_path)
    assert restored.theme == "winter"

    with Image.open(ICON_ICO) as ico:
        icon16 = ico.ico.getimage((16, 16)).convert("RGBA")
        assert icon16.getchannel("A").getbbox() is not None
        icon16.resize((256, 256), Image.Resampling.NEAREST).save(ARTIFACTS / "icon-16-nearest.png")

    scaling = float(root.tk.call("tk", "scaling"))
    result = {
        "dpi_awareness": awareness,
        "dpi": round(app.dpi, 2),
        "tk_scaling": round(scaling, 3),
        "display_scale": round(app.display_scale, 3),
        "window_icon_handles": icon_handles,
        "iconbitmap": root.iconbitmap(),
        "notebook_decoration_removed": not hasattr(app, "notebook_decoration"),
        "theme_does_not_stale_preview": app._project_signature() == render_signature,
        "project_theme_roundtrip": restored.theme,
        "themes": theme_results,
    }
    (ARTIFACTS / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    root.attributes("-topmost", False)
    app._on_close()
    print("PASS", json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
