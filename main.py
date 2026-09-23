"""Application entry point.

The bundled Tcl/Tk runtime must be discoverable before importing tkinter.
PyInstaller normally installs these variables through a runtime hook, but
setting them here as well makes the onedir build independent of the Python
development installation.
"""

from __future__ import annotations

import os
import sys

from app.resources import resource_path


def configure_bundled_tcl_tk() -> None:
    """Point frozen builds at their packaged Tcl/Tk data when available."""
    if not getattr(sys, "frozen", False):
        return
    for variable, directory in (
        ("TCL_LIBRARY", resource_path("_tcl_data")),
        ("TK_LIBRARY", resource_path("_tk_data")),
    ):
        if directory.is_dir():
            # A user-wide Tcl/Tk path could point to another Python install.
            # The EXE must always load the runtime shipped beside it.
            os.environ[variable] = str(directory)


configure_bundled_tcl_tk()

from app.main_window import run


if __name__ == "__main__":
    run()
