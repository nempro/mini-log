"""Tk visual-system acceptance for contrast, native scaling, and field styling."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tkinterdnd2 import TkinterDnD

from app.main_window import (
    BG,
    BORDER,
    CONTROL_BORDER,
    INK,
    MUTED,
    PANEL,
    MiniLogApp,
    enable_windows_dpi_awareness,
)


def main() -> None:
    awareness = enable_windows_dpi_awareness()
    root = TkinterDnD.Tk()
    root.withdraw()
    app = MiniLogApp(root)
    root.deiconify()
    root.update()

    style = app.root.tk.call
    tk_scaling = float(style("tk", "scaling"))
    assert abs(tk_scaling - app.dpi / 72.0) < 0.03
    assert app.root.cget("background").upper() == BG
    assert app.right_canvas.cget("background").upper() == PANEL
    assert app.cut_caption_text.cget("background").upper() == PANEL
    assert app.cut_caption_text.cget("foreground").upper() == INK
    assert app.cut_caption_text.cget("highlightbackground").upper() == CONTROL_BORDER
    assert app.root.tk.call("ttk::style", "lookup", "Panel.TFrame", "-background").upper() == PANEL
    assert app.root.tk.call("ttk::style", "lookup", "Surface.TFrame", "-bordercolor").upper() == BORDER
    assert app.root.tk.call("ttk::style", "lookup", "PanelMuted.TLabel", "-foreground").upper() == MUTED

    result = {
        "dpi_awareness": awareness,
        "reported_dpi": round(app.dpi, 2),
        "tk_scaling": round(tk_scaling, 4),
        "display_scale": round(app.display_scale, 3),
        "geometry": root.geometry(),
        "background": BG,
        "panel": PANEL,
        "text": INK,
        "muted_text": MUTED,
        "panel_border": BORDER,
        "control_border": CONTROL_BORDER,
    }
    output = ROOT / "output" / "visual-acceptance.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    app._on_close()
    print("PASS", json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
