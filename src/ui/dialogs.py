from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QEvent, QObject,
)
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QComboBox,
    QCheckBox, QGridLayout, QTabWidget, QPlainTextEdit,
    QMessageBox, QInputDialog, QFileDialog, QFrame,
    QGraphicsOpacityEffect,
)
from pathlib import Path
from core import theme
from core.worker import Worker
from ui.helpers import (
    s_btn, s_btn_accent, s_entry, s_combo, s_textedit, s_spin, s_tabs,
)
from core.jvm import default_jvm_flags
from core.java import find_javas, best_java
from core.paths import IS_WIN


class _EscCloseFilter(QObject):
    """Intercepts Esc inside a line edit so it clears the field first,
    and only closes the dialog if the field was already empty."""
    def __init__(self, dialog, field):
        super().__init__(dialog)
        self._dialog = dialog
        self._field = field

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and \
           event.key() == Qt.Key.Key_Escape:
            try:
                if self._field.text():
                    self._field.clear()
                else:
                    self._dialog.reject()
            except Exception:
                pass
            return True
        return super().eventFilter(obj, event)


def fade_in(dialog, duration=120):
    effect = QGraphicsOpacityEffect(dialog)
    effect.setOpacity(0.0)
    dialog.setGraphicsEffect(effect)

    anim = QPropertyAnimation(effect, b"opacity", dialog)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _cleanup():
        dialog.setGraphicsEffect(None)

    anim.finished.connect(_cleanup)
    anim.start()
    dialog._fade_anim = anim


class _ChoiceCard(QFrame):
    def __init__(self, title, subtitle, accent, on_click, parent=None):
        super().__init__(parent)
        self._on_click = on_click
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(72)
        self._accent = accent
        self._base = theme.ACCENT if accent else theme.BG3
        self._hover = theme.ACCENT2 if accent else theme.BORDER

        fg_title = theme.on_accent() if accent else theme.FG
        fg_sub = "#000000" if accent else theme.GRAY
        border = "none" if accent else f"1px solid {theme.BORDER}"

        self._normal_css = f"""
            _ChoiceCard, QFrame {{
                background: {self._base};
                border: {border};
                border-radius: 0;
            }}
        """
        self._hover_css = f"""
            _ChoiceCard, QFrame {{
                background: {self._hover};
                border: {border};
                border-radius: 0;
            }}
        """
        self.setStyleSheet(self._normal_css)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(2)

        t = QLabel(title)
        t.setStyleSheet(
            f"background:transparent;border:none;color:{fg_title};"
            f"font-size:12pt;font-weight:bold;"
            f"font-family:'{theme.UI_FONT}'")
        lay.addWidget(t)

        s = QLabel(subtitle)
        s.setStyleSheet(
            f"background:transparent;border:none;color:{fg_sub};"
            f"font-size:9pt;font-family:'{theme.UI_FONT}'")
        s.setWordWrap(True)
        lay.addWidget(s)

    def enterEvent(self, event):
        self.setStyleSheet(self._hover_css)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet(self._normal_css)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if callable(self._on_click):
                self._on_click()
        super().mousePressEvent(event)


class ChooseInstallDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.choice = None
        self.setWindowTitle("Add New")
        self.setFixedSize(480, 380)
        self.setSizeGripEnabled(False)
        self.setStyleSheet(
            f"QDialog{{background:{theme.BG};color:{theme.FG}}}")

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)

        title = QLabel("Add New")
        title.setStyleSheet(
            f"background:transparent;color:{theme.FG};"
            f"font-size:16pt;font-weight:bold;"
            f"font-family:'{theme.UI_FONT}'")
        v.addWidget(title)

        subtitle = QLabel("Choose what to create or install.")
        subtitle.setStyleSheet(
            f"background:transparent;color:{theme.GRAY};"
            f"font-size:9pt;font-family:'{theme.UI_FONT}'")
        v.addWidget(subtitle)

        v.addSpacing(6)

        for label, sub, key, accent in (
            ("Modrinth Modpack",
             "Search and install from the Modrinth catalog",
             "modrinth", True),
            ("Blank Profile",
             "Pick a Minecraft version and loader",
             "blank", False),
            ("Local file",
             "Import a .mrpack, .zip or .xerpack pack",
             "local", False),
        ):
            card = _ChoiceCard(
                label, sub, accent,
                on_click=lambda k=key: self._pick(k),
                parent=self)
            v.addWidget(card)

        v.addStretch(1)
        fade_in(self)

    def _pick(self, c):
        self.choice = c
        self.accept()


class ProfileDialog(QDialog):
    def __init__(self, parent, releases, settings, profile=None):
        super().__init__(parent)
        self.settings = settings
        self.profile = profile
        self.is_new = profile is None
        self.setWindowTitle(
            "New Instance" if self.is_new else f"Edit — {profile.name}")
        self.setFixedSize(700, 640)
        self.setSizeGripEnabled(False)
        self.setStyleSheet(
            f"QDialog{{background:{theme.BG};color:{theme.FG}}}"
            f"QLabel{{background:{theme.BG};color:{theme.FG};"
            f"font-family:\"{theme.UI_FONT}\";font-size:10pt}}"
            + s_entry() + s_combo() + s_spin() + s_textedit() + s_tabs() +
            f"QCheckBox{{background:{theme.BG};color:{theme.FG};"
            f"font-family:\"{theme.UI_FONT}\";font-size:10pt}}"
        )
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(10)
        self.tabs = QTabWidget(self)
        v.addWidget(self.tabs, 1)

        t1 = QWidget()
        g1 = QGridLayout(t1)
        g1.setContentsMargins(14, 14, 14, 14)
        g1.setSpacing(8)
        g1.addWidget(QLabel("Name"), 0, 0)
        self.name = QLineEdit(profile.name if profile else "My Instance")
        g1.addWidget(self.name, 0, 1)
        g1.addWidget(QLabel("Version"), 1, 0)
        self.ver = QComboBox()
        ids = [x["id"] for x in releases]
        self.ver.addItems(ids)
        if profile and profile.version in ids:
            self.ver.setCurrentText(profile.version)
        g1.addWidget(self.ver, 1, 1)
        g1.addWidget(QLabel("Loader"), 2, 0)
        self.loader = QComboBox()
        for k, label in (("vanilla", "Vanilla"), ("fabric", "Fabric"),
                         ("forge", "Forge"), ("neoforge", "NeoForge"),
                         ("quilt", "Quilt")):
            self.loader.addItem(label, k)
        if profile:
            idx = self.loader.findData(profile.loader)
            if idx >= 0:
                self.loader.setCurrentIndex(idx)
        g1.addWidget(self.loader, 2, 1)
        g1.addWidget(QLabel("RAM"), 3, 0)
        self.ram = QComboBox()
        self.ram.addItem("2 GB", "2")
        self.ram.addItem("4 GB", "4")
        self.ram.addItem("8 GB", "8")
        self.ram.addItem("16 GB", "16")
        cur_gb = str(int(profile.ram)) if profile else "4"
        idx = self.ram.findData(cur_gb)
        if idx >= 0:
            self.ram.setCurrentIndex(idx)
        g1.addWidget(self.ram, 3, 1)
        g1.setRowStretch(4, 1)
        self.tabs.addTab(t1, "Basic")

        t2 = QWidget()
        g2 = QVBoxLayout(t2)
        g2.setContentsMargins(14, 14, 14, 14)
        g2.setSpacing(8)
        row = QHBoxLayout()
        row.addWidget(QLabel("GC"))
        self.gc = QComboBox()
        self.gc.addItem(
            f"Use global ({settings.get('gc', 'G1GC')})", "")
        for g in ("G1GC", "ZGC", "Parallel", "Serial"):
            self.gc.addItem(f"Override: {g}", g)
        if profile and profile.override_gc:
            idx = self.gc.findData(profile.override_gc)
            if idx >= 0:
                self.gc.setCurrentIndex(idx)
        row.addWidget(self.gc)
        row.addStretch()
        g2.addLayout(row)
        g2.addWidget(QLabel("JVM flags"))
        self.jvm = QPlainTextEdit()
        auto = " ".join(default_jvm_flags(
            str(int(self.ram.currentData())),
            self.gc.currentData() or settings.get("gc", "G1GC")))
        user = profile.override_jvm_flags if profile else ""
        self.jvm.setPlainText((auto + " " + user).strip())
        g2.addWidget(self.jvm, 1)
        self.ram.currentIndexChanged.connect(self._refresh_jvm)
        self.gc.currentIndexChanged.connect(self._refresh_jvm)
        self._auto_str = auto
        self.tabs.addTab(t2, "JVM")

        t3 = QWidget()
        g3 = QVBoxLayout(t3)
        g3.setContentsMargins(14, 14, 14, 14)
        g3.setSpacing(8)
        g3.addWidget(QLabel("Environment variables (overrides global)"))
        self.env = QPlainTextEdit()
        self.env.setPlaceholderText("MANGOHUD=1")
        self.env.setPlainText(profile.override_env_vars if profile else "")
        g3.addWidget(self.env, 1)
        self.tabs.addTab(t3, "Environment")

        t4 = QWidget()
        g4 = QGridLayout(t4)
        g4.setContentsMargins(14, 14, 14, 14)
        g4.setSpacing(8)
        g4.addWidget(QLabel("Java"), 0, 0)
        jrow = QHBoxLayout()
        self.java_path = QLineEdit(
            profile.override_java_path if profile else "")
        try:
            resolved = best_java(
                "1.20.1", log=None,
                override=settings.get("java_path", ""))
        except Exception:
            resolved = None
        self.java_path.setPlaceholderText(
            f"auto-detected: {resolved}" if resolved else "auto-detect")
        jrow.addWidget(self.java_path, 1)
        find_btn = QPushButton("Auto")
        find_btn.setToolTip("Auto-detect")
        find_btn.setAutoDefault(False)
        find_btn.setDefault(False)
        find_btn.setStyleSheet(s_btn(theme.BG2, theme.FG, theme.BG3))
        find_btn.clicked.connect(self._find_java)
        jrow.addWidget(find_btn)
        browse_btn = QPushButton("Browse")
        browse_btn.setAutoDefault(False)
        browse_btn.setDefault(False)
        browse_btn.setStyleSheet(s_btn(theme.BG2, theme.FG, theme.BG3))
        browse_btn.clicked.connect(self._browse_java)
        jrow.addWidget(browse_btn)
        g4.addLayout(jrow, 0, 1)

        g4.addWidget(QLabel("Wrapper"), 1, 0)
        self.wrapper = QLineEdit(
            profile.override_wrapper if profile else "")
        self.wrapper.setPlaceholderText("mangohud --dlsym")
        g4.addWidget(self.wrapper, 1, 1)

        has_sodium = False
        if profile:
            try:
                mods_dir = profile.dir / "mods"
                if mods_dir.exists():
                    for f in mods_dir.iterdir():
                        if "sodium" in f.name.lower():
                            has_sodium = True
                            break
            except Exception:
                pass

        self.nvidia = QCheckBox(
            "Apply NVIDIA threaded-optimizations fix")
        self.nvidia.setChecked(
            getattr(profile, "override_nvidia_fix", False)
            if profile else False)
        self.nvidia.setEnabled(has_sodium)
        if has_sodium:
            self.nvidia.setToolTip(
                "Only useful with the Sodium mod installed.")
        else:
            self.nvidia.setToolTip(
                "No Sodium mod found in this instance's mods folder. "
                "Install Sodium first to enable this.")
        g4.addWidget(self.nvidia, 2, 0, 1, 2)

        sodium_hint = QLabel(
            "Only useful with the Sodium mod installed."
            if has_sodium else
            "Install Sodium to enable this option.")
        sodium_hint.setStyleSheet(
            f"background:transparent;color:{theme.GRAY};font-size:9pt")
        g4.addWidget(sodium_hint, 3, 0, 1, 2)

        filler = QFrame()
        filler.setStyleSheet(
            f"QFrame{{background:{theme.BG2};border:none}}")
        g4.addWidget(filler, 4, 0, 1, 2)
        g4.setRowStretch(4, 1)
        self.tabs.addTab(t4, "Advanced")

        btns = QHBoxLayout()
        btns.addStretch()
        c = QPushButton("Cancel")
        c.setAutoDefault(False)
        c.setDefault(False)
        c.setStyleSheet(s_btn(theme.BG2, theme.FG, theme.BG3))
        c.clicked.connect(self.reject)
        btns.addWidget(c)
        ok = QPushButton("Create" if self.is_new else "Save")
        ok.setAutoDefault(False)
        ok.setDefault(False)
        ok.setStyleSheet(s_btn_accent())
        ok.clicked.connect(self.accept)
        btns.addWidget(ok)
        v.addLayout(btns)
        self.name.selectAll()
        self.name.setFocus()
        fade_in(self)

    def _refresh_jvm(self):
        auto = " ".join(default_jvm_flags(
            str(int(self.ram.currentData())),
            self.gc.currentData() or self.settings.get("gc", "G1GC")))
        current = self.jvm.toPlainText()
        if getattr(self, "_auto_str", "") and current.startswith(
                self._auto_str):
            user_part = current[len(self._auto_str):].strip()
            self.jvm.setPlainText((auto + " " + user_part).strip())
        self._auto_str = auto

    def _find_java(self):
        javas = find_javas()
        if not javas:
            QMessageBox.information(
                self, "No Java",
                "No Java installations detected.")
            return
        items = [f"{label}  —  {path}" for path, (label, _) in javas]
        choice, ok = QInputDialog.getItem(
            self, "Select Java", "Detected Java installations:",
            items, 0, False)
        if ok and choice:
            idx = items.index(choice)
            self.java_path.setText(javas[idx][0])

    def _browse_java(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select java executable", str(Path.home()),
            "Java (java)" if not IS_WIN else "Java (*.exe)")
        if path:
            self.java_path.setText(path)

    def apply(self, profile):
        profile.version = self.ver.currentText()
        profile.ram = str(int(self.ram.currentData()))
        profile.loader = self.loader.currentData()
        profile.override_gc = self.gc.currentData() or ""
        profile.override_jvm_flags = self.jvm.toPlainText().strip()
        profile.override_env_vars = self.env.toPlainText().strip()
        profile.override_java_path = self.java_path.text().strip()
        profile.override_wrapper = self.wrapper.text().strip()
        profile.override_nvidia_fix = self.nvidia.isChecked()

    def values(self):
        return (self.name.text().strip(), self.ver.currentText(),
                str(int(self.ram.currentData())),
                self.loader.currentData())


# ---- Re-export for callers that do `from ui.dialogs import ModpackSearchDialog`
from browse.modpacks import ModpackSearchDialog  # noqa: E402,F401
