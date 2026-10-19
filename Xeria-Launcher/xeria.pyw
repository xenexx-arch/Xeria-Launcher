#!/usr/bin/env python3
import sys
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, Qt
QCoreApplication.setAttribute(
    Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

HERE = Path(__file__).parent
SRC = HERE / "src"
sys.path.insert(0, str(SRC))

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from core import theme
from core.settings import Settings

_settings = Settings()
theme.apply(_settings.get("theme", "dark"))
theme.apply_accent(_settings.get("accent", "Blue"))

from ui.launcher import MainWindow
from core.worker import _leaked_threads
from integration import http as _http

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(theme.BG))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(theme.FG))
    pal.setColor(QPalette.ColorRole.Base, QColor(theme.BG2))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(theme.BG3))
    pal.setColor(QPalette.ColorRole.Text, QColor(theme.FG))
    pal.setColor(QPalette.ColorRole.Button, QColor(theme.BG3))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(theme.FG))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(theme.ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText,
                 QColor(theme.on_accent()))
    app.setPalette(pal)

    win = MainWindow()
    win.show()
    code = app.exec()

    for w in list(getattr(win, "_workers", [])):
        try:
            if w.isRunning():
                w.quit()
                if not w.wait(2000):
                    _leaked_threads.append(w)
        except Exception:
            pass
    _http.close()
    sys.exit(code)
