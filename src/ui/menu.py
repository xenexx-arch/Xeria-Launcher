import platform
from pathlib import Path

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QGridLayout, QTabWidget,
    QPlainTextEdit, QMessageBox, QInputDialog, QFileDialog,
)
from core import theme
from core.paths import IS_WIN, MC_ROOT, XERIA_ROOT
from core.java import find_javas, best_java
from ui.helpers import s_btn, s_tabs, s_combo, s_textedit


class MenuView(QWidget):
    back_requested = pyqtSignal()
    theme_changed = pyqtSignal(str, str)

    def __init__(self, parent, settings):
        super().__init__(parent)
        self.settings = settings
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)

        self.tabs = QTabWidget(self)
        self.tabs.setStyleSheet(s_tabs())
        v.addWidget(self.tabs, 1)

        gen = QWidget(); gg = QGridLayout(gen)
        gg.setContentsMargins(14, 14, 14, 14); gg.setSpacing(8)
        gg.addWidget(QLabel("Theme"), 0, 0)
        self.theme_box = QComboBox()
        self.theme_box.addItems(["Dark", "Light"])
        cur = str(self.settings.get("theme", "dark")).capitalize()
        if cur not in ("Dark", "Light"):
            cur = "Dark"
        self.theme_box.setCurrentText(cur)
        gg.addWidget(self.theme_box, 0, 1)

        gg.addWidget(QLabel("Accent color"), 1, 0)
        self.accent_box = QComboBox()
        self.accent_box.addItems(
            ["White", "Blue", "Purple", "Green", "Orange",
             "Red", "Pink", "Cyan"])
        self.accent_box.setCurrentText(self.settings.get("accent", "White"))
        gg.addWidget(self.accent_box, 1, 1)

        gg.setRowStretch(2, 1)
        self.tabs.addTab(gen, "General")

        jv = QWidget(); gj = QGridLayout(jv)
        gj.setContentsMargins(14, 14, 14, 14); gj.setSpacing(8)

        gj.addWidget(QLabel("Java"), 0, 0)
        jrow = QHBoxLayout()
        self.java_path = QLineEdit(self.settings.get("java_path", ""))
        try:
            resolved = best_java(
                "1.20.1", log=None,
                override=self.settings.get("java_path", ""))
        except Exception:
            resolved = None
        self.java_path.setPlaceholderText(
            f"auto-detected: {resolved}" if resolved else "auto-detect")
        jrow.addWidget(self.java_path, 1)
        find_btn = QPushButton("Auto")
        find_btn.setToolTip("Auto-detect")
        find_btn.setStyleSheet(s_btn(theme.BG2, theme.FG, theme.BG3))
        find_btn.clicked.connect(self._find_java); jrow.addWidget(find_btn)
        br_btn = QPushButton("Browse")
        br_btn.setStyleSheet(s_btn(theme.BG2, theme.FG, theme.BG3))
        br_btn.clicked.connect(self._browse_java); jrow.addWidget(br_btn)
        gj.addLayout(jrow, 0, 1)

        gj.addWidget(QLabel("Default JVM flags"), 1, 0)
        self.default_flags = QPlainTextEdit(
            self.settings.get("default_jvm_flags", ""))
        self.default_flags.setPlaceholderText(
            "flags applied to every instance unless overridden")
        gj.addWidget(self.default_flags, 2, 0, 1, 2)
        gj.setRowStretch(3, 1)
        self.tabs.addTab(jv, "JVM")

        pf = QWidget(); gp = QGridLayout(pf)
        gp.setContentsMargins(14, 14, 14, 14); gp.setSpacing(8)
        gp.addWidget(QLabel("Default GC"), 0, 0)
        self.gc_box = QComboBox(); self.gc_box.addItems(
            ["G1GC", "ZGC", "Parallel", "Serial"])
        self.gc_box.setCurrentText(self.settings.get("gc", "G1GC"))
        gp.addWidget(self.gc_box, 0, 1)
        gp.addWidget(QLabel("JVM flags"), 1, 0)
        self.jvm = QPlainTextEdit(self.settings.get("jvm_flags", ""))
        gp.addWidget(self.jvm, 2, 0, 1, 2)
        gp.setRowStretch(3, 1)
        self.tabs.addTab(pf, "Performance")

        ev = QWidget(); gv = QVBoxLayout(ev)
        gv.setContentsMargins(14, 14, 14, 14); gv.setSpacing(8)
        gv.addWidget(QLabel("Environment overrides global"))
        self.env = QPlainTextEdit()
        self.env.setPlaceholderText("MANGOHUD=1")
        self.env.setPlainText(self.settings.get("env_vars", ""))
        gv.addWidget(self.env, 1)
        self.tabs.addTab(ev, "Environment")

        wp = QWidget(); gw = QGridLayout(wp)
        gw.setContentsMargins(14, 14, 14, 14); gw.setSpacing(8)
        gw.addWidget(QLabel("Wrapper command"), 0, 0)
        self.wrapper = QLineEdit(self.settings.get("wrapper_command", ""))
        self.wrapper.setPlaceholderText("mangohud --dlsym")
        gw.addWidget(self.wrapper, 0, 1)
        gw.setRowStretch(1, 1)
        self.tabs.addTab(wp, "Wrapper")

        ab = QWidget(); ga = QVBoxLayout(ab)
        ga.setContentsMargins(14, 14, 14, 14); ga.setSpacing(6)
        for label, value in (
            ("Launcher", "Xeria 2.1"),
            ("Platform", f"{platform.system()} {platform.release()}"),
            ("Python", platform.python_version()),
            ("Minecraft root", str(MC_ROOT)),
            ("Config", str(XERIA_ROOT)),
        ):
            ga.addWidget(QLabel(f"<b>{label}:</b> {value}"))
        ga.addStretch()
        self.tabs.addTab(ab, "About")

        self.theme_box.currentTextChanged.connect(self._save_all)
        self.accent_box.currentTextChanged.connect(self._save_all)
        self.java_path.textChanged.connect(self._save_all)
        self.default_flags.textChanged.connect(self._save_all)
        self.gc_box.currentTextChanged.connect(self._save_all)
        self.jvm.textChanged.connect(self._save_all)
        self.env.textChanged.connect(self._save_all)
        self.wrapper.textChanged.connect(self._save_all)

    def restyle(self):
        from core import theme as _theme
        self.tabs.setStyleSheet(s_tabs())
        for w in self.findChildren(QPushButton):
            ss = w.styleSheet()
            if ss and "QPushButton" in ss:
                w.setStyleSheet(s_btn(_theme.BG2, _theme.FG, _theme.BG3))
        for w in self.findChildren(QComboBox):
            w.setStyleSheet(s_combo())
        for w in self.findChildren(QPlainTextEdit):
            w.setStyleSheet(s_textedit())
        for w in self.findChildren(QLineEdit):
            w.setStyleSheet(
                f"QLineEdit{{background:{_theme.BG3};color:{_theme.FG};"
                f"border:none;padding:6px;"
                f"font-family:\"{_theme.UI_FONT}\";font-size:10pt}}")

    def _save_all(self, *a):
        self.settings.set("theme", self.theme_box.currentText().lower())
        self.settings.set("accent", self.accent_box.currentText())
        self.settings.set("java_path", self.java_path.text().strip())
        self.settings.set("default_jvm_flags",
                          self.default_flags.toPlainText().strip())
        self.settings.set("gc", self.gc_box.currentText())
        self.settings.set("jvm_flags", self.jvm.toPlainText().strip())
        self.settings.set("env_vars", self.env.toPlainText().strip())
        self.settings.set("wrapper_command", self.wrapper.text().strip())
        self.settings.save()
        self.theme_changed.emit(self.theme_box.currentText().lower(),
                                self.accent_box.currentText())

    def _find_java(self):
        javas = find_javas()
        if not javas:
            QMessageBox.information(self, "No Java",
                                    "No Java installations detected.")
            return
        items = [f"{label}  —  {path}" for path, (label, _) in javas]
        choice, ok = QInputDialog.getItem(self, "Select Java",
                                          "Detected Java installations:",
                                          items, 0, False)
        if ok and choice:
            idx = items.index(choice)
            self.java_path.setText(javas[idx][0])

    def _browse_java(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Java executable", str(Path.home()),
            "Java (java)" if not IS_WIN else "Java (*.exe)")
        if path: self.java_path.setText(path)
