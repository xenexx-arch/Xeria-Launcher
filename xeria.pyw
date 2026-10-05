#!/usr/bin/env python3
import os, sys, platform
from pathlib import Path

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
