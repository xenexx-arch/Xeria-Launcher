#!/usr/bin/env python3
import os, sys, platform
from pathlib import Path

# ---------------------------------------------------------------------------
# Hide the console BEFORE any Qt or app imports.
#
# Linux:  redirect fd 1/2 + sys.stdout/sys.stderr to /dev/null
# Windows: hide the console window (works whether launched via
#          python.exe or pythonw.exe)
# ---------------------------------------------------------------------------
_verbose = any(a in ("-v", "--verbose") for a in sys.argv)
_system = platform.system()

if not _verbose:
    if _system == "Linux":
        os.environ.pop("QT_STYLE_OVERRIDE", None)
        os.environ.pop("QT_QPA_PLATFORMTHEME", None)
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
        os.environ["QT_LOGGING_RULES"] = "*.debug=false;*.info=false"
        try:
            _devnull = os.open(os.devnull, os.O_RDWR)
            os.dup2(_devnull, 1)
            os.dup2(_devnull, 2)
            sys.stdout = open(os.devnull, "w")
            sys.stderr = open(os.devnull, "w")
        except Exception:
            pass

    elif _system == "Windows":
        os.environ["QT_LOGGING_RULES"] = "*.debug=false;*.info=false"
        try:
            import ctypes
            # hide the console window if one exists
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)
            # also detach std handles so any C-level writes go nowhere
            kernel32 = ctypes.windll.kernel32
            kernel32.FreeConsole()  # detach from the console entirely
        except Exception:
            pass
        try:
            _devnull = open(os.devnull, "w")
            sys.stdout = _devnull
            sys.stderr = _devnull
        except Exception:
            pass

elif _system == "Linux":
    # verbose mode still respects platform env on Linux
    os.environ.pop("QT_STYLE_OVERRIDE", None)
    os.environ.pop("QT_QPA_PLATFORMTHEME", None)
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

# WebEngine needs this before QApplication exists.
from PyQt5.QtCore import QCoreApplication, Qt
QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)

HERE = Path(__file__).parent
SRC = HERE / "src"
sys.path.insert(0, str(SRC))

from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import QApplication

import theme
from settings import Settings

_settings = Settings()
theme.apply(_settings.get("theme", "dark"))
theme.apply_accent(_settings.get("accent", "Blue"))

from launcher import MainWindow
from worker import _leaked_threads

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(theme.BG))
    pal.setColor(QPalette.WindowText, QColor(theme.FG))
    pal.setColor(QPalette.Base, QColor(theme.BG2))
    pal.setColor(QPalette.AlternateBase, QColor(theme.BG3))
    pal.setColor(QPalette.Text, QColor(theme.FG))
    pal.setColor(QPalette.Button, QColor(theme.BG3))
    pal.setColor(QPalette.ButtonText, QColor(theme.FG))
    pal.setColor(QPalette.Highlight, QColor(theme.ACCENT))
    pal.setColor(QPalette.HighlightedText, QColor(theme.on_accent()))
    app.setPalette(pal)

    win = MainWindow()
    win.show()
    code = app.exec_()

    for w in list(getattr(win, "_workers", [])):
        try:
            if w.isRunning():
                w.quit()
                if not w.wait(2000):
                    _leaked_threads.append(w)
        except Exception:
            pass
    sys.exit(code)
