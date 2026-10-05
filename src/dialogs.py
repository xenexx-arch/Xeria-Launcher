from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QSpinBox, QComboBox,
    QCheckBox, QGridLayout, QTabWidget, QPlainTextEdit,
    QMessageBox, QInputDialog, QFileDialog, QFrame,
)
from pathlib import Path
import theme
from worker import Worker
from ui_helpers import (
    s_btn, s_btn_accent, s_entry, s_combo, s_textedit, s_spin, s_tabs,
)
from jvm import default_jvm_flags
from java import find_javas, best_java
from paths import IS_WIN


def fade_in(dialog, duration=120):
    dialog.setWindowOpacity(0.0)
    a = QPropertyAnimation(dialog, b"windowOpacity", dialog)
    a.setDuration(duration); a.setStartValue(0.0); a.setEndValue(1.0)
    a.setEasingCurve(QEasingCurve.OutCubic)
    a.start()
    dialog._fade_anim = a


class ChooseInstallDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.choice = None
        self.setWindowTitle("Add New")
        self.resize(430, 330)
        self.setStyleSheet(f"""QDialog{{background:{theme.BG};color:{theme.FG}}}
            QLabel{{color:{theme.FG};font-family:"{theme.UI_FONT}"}}
            QPushButton{{background:{theme.BG3};color:{theme.FG};
                border:1px solid {theme.BORDER};border-radius:0;
                padding:14px;font-family:"{theme.UI_FONT}";font-size:11pt;text-align:left}}
            QPushButton:hover{{background:{theme.BORDER}}}""")
        v = QVBoxLayout(self); v.setContentsMargins(20, 20, 20, 20); v.setSpacing(10)
        title = QLabel("Add New")
        title.setStyleSheet(f"color:{theme.FG};font-size:15pt;font-weight:bold")
        v.addWidget(title)
        for label, sub, key, accent in [
            ("Modrinth Modpack", "Search and install from catalog", "modrinth", True),
            ("Blank Profile", "Pick a Minecraft version", "blank", False),
            ("Modpacks (.xerpack, .zip, .mrpack)", "Import from a local file", "local", False),
        ]:
            b = QPushButton(f"  {label}\n  {sub}")
            if accent:
                b.setStyleSheet(
                    f"QPushButton{{background:{theme.ACCENT};color:{theme.on_accent()};"
                    f"border:none;border-radius:0;padding:14px;"
                    f"font-family:{theme.UI_FONT};font-size:11pt;text-align:left;font-weight:bold}}"
                    f"QPushButton:hover{{background:{theme.ACCENT2}}}")
            b.clicked.connect(lambda _, k=key: self._pick(k))
            v.addWidget(b)
        fade_in(self)

    def _pick(self, c):
        self.choice = c; self.accept()


class ModpackSearchDialog(QDialog):
    def __init__(self, parent, log_fn=None):
        super().__init__(parent)
        self.result = None
        self.log_fn = log_fn or (lambda t, m: None)
        self._req_id = 0; self._w = None; self.results_data = []
        self.setWindowTitle("Search Modpacks")
        self.resize(760, 520)
        self.setStyleSheet(f"""QDialog{{background:{theme.BG};color:{theme.FG}}}
            QLabel{{color:{theme.FG};font-family:"{theme.UI_FONT}"}}
            QLineEdit{{background:{theme.BG2};color:{theme.FG};
                border:1px solid {theme.BORDER};border-radius:0;padding:8px;
                font-family:"{theme.UI_FONT}";font-size:10pt}}
            QListWidget{{background:{theme.BG2};color:{theme.FG};
                border:1px solid {theme.BORDER};padding:0;border-radius:0}}
            QListWidget::item{{padding:8px}}
            QListWidget::item:hover{{background:{theme.BG3}}}
            QListWidget::item:selected{{background:{theme.ACCENT};color:{theme.on_accent()}}}
            QPushButton{{background:{theme.BG3};color:{theme.FG};
                border:1px solid {theme.BORDER};border-radius:0;
                padding:8px 16px;font-family:"{theme.UI_FONT}"}}
            QPushButton:hover{{background:{theme.BORDER}}}""")
        v = QVBoxLayout(self); v.setContentsMargins(14, 14, 14, 14); v.setSpacing(8)
        head = QLabel("Search Modrinth modpacks")
        head.setStyleSheet(f"color:{theme.FG};font-size:13pt;font-weight:bold")
        v.addWidget(head)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Type to search modpacks…")
        v.addWidget(self.search)
        self.list = QListWidget(); self.list.itemDoubleClicked.connect(lambda _: self._choose())
        v.addWidget(self.list, 1)
        btns = QHBoxLayout(); btns.addStretch()
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        ok = QPushButton("Install")
        ok.setStyleSheet(f"QPushButton{{background:{theme.ACCENT};color:{theme.on_accent()};"
                         f"border:none;border-radius:0;padding:8px 20px;font-weight:bold}}"
                         f"QPushButton:hover{{background:{theme.ACCENT2}}}")
        ok.clicked.connect(self._choose); btns.addWidget(ok)
        v.addLayout(btns)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True); self._debounce.setInterval(800)
        self._debounce.timeout.connect(self._do_search)
        self.search.textChanged.connect(lambda _: (self._debounce.stop(), self._debounce.start()))
        self.search.returnPressed.connect(self._do_search)
        QTimer.singleShot(200, self._do_search)
        fade_in(self)

    def _do_search(self):
        import modrinth
        q = self.search.text().strip() or "fabulously optimized"
        self._req_id += 1; rid = self._req_id
        self.list.clear(); self.list.addItem("  Searching…")
        w = Worker(lambda log, progress, progress_end: modrinth.search_modpacks(q))
        w.done.connect(lambda r, r_=rid: self._apply(r, r_), Qt.QueuedConnection)
        w.log.connect(self.log_fn, Qt.QueuedConnection)
        self._w = w; w.start()

    def _apply(self, hits, rid):
        if rid != self._req_id: return
        self.list.clear(); self.results_data = hits or []
        for h in self.results_data:
            self.list.addItem(QListWidgetItem(
                f"  {h['title']}   ·  {h['author']}  ·  {h['dl']:,} DL\n"
                f"      {h['desc'][:90]}"))
        if self.results_data: self.list.setCurrentRow(0)

    def _choose(self):
        row = self.list.currentRow()
        if row < 0 or row >= len(self.results_data): return
        self.result = self.results_data[row]; self.accept()


class ProfileDialog(QDialog):
    def __init__(self, parent, releases, settings, profile=None):
        super().__init__(parent)
        self.settings = settings
        self.profile = profile
        self.is_new = profile is None
        self.setWindowTitle("New Instance" if self.is_new else f"Edit — {profile.name}")
        self.resize(640, 600)
        self.setMinimumSize(520, 460)
        self.setStyleSheet(
            f"QDialog{{background:{theme.BG};color:{theme.FG}}}"
            f"QLabel{{background:{theme.BG};color:{theme.FG};"
            f"font-family:\"{theme.UI_FONT}\";font-size:10pt}}"
            + s_entry() + s_combo() + s_spin() + s_textedit() + s_tabs() +
            f"QCheckBox{{background:{theme.BG};color:{theme.FG};"
            f"font-family:\"{theme.UI_FONT}\";font-size:10pt}}"
        )
        v = QVBoxLayout(self); v.setContentsMargins(16, 16, 16, 16); v.setSpacing(10)
        self.tabs = QTabWidget(self); v.addWidget(self.tabs, 1)

        # ---------- Basic ----------
        t1 = QWidget(); g1 = QGridLayout(t1)
        g1.setContentsMargins(14, 14, 14, 14); g1.setSpacing(8)
        g1.addWidget(QLabel("Name"), 0, 0)
        self.name = QLineEdit(profile.name if profile else "My Instance")
        g1.addWidget(self.name, 0, 1)
        g1.addWidget(QLabel("Version"), 1, 0)
        self.ver = QComboBox()
        ids = [x["id"] for x in releases]; self.ver.addItems(ids)
        if profile and profile.version in ids: self.ver.setCurrentText(profile.version)
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

        # ---------- JVM ----------
        t2 = QWidget(); g2 = QVBoxLayout(t2)
        g2.setContentsMargins(14, 14, 14, 14); g2.setSpacing(8)
        row = QHBoxLayout()
        row.addWidget(QLabel("GC"))
        self.gc = QComboBox()
        self.gc.addItem(f"Use global ({settings.get('gc', 'G1GC')})", "")
        for g in ("G1GC", "ZGC", "Parallel", "Serial"):
            self.gc.addItem(f"Override: {g}", g)
        if profile and profile.override_gc:
            idx = self.gc.findData(profile.override_gc)
            if idx >= 0: self.gc.setCurrentIndex(idx)
        row.addWidget(self.gc); row.addStretch()
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

        # ---------- Environment ----------
        t3 = QWidget(); g3 = QVBoxLayout(t3)
        g3.setContentsMargins(14, 14, 14, 14); g3.setSpacing(8)
        g3.addWidget(QLabel("Environment variables (overrides global)"))
        self.env = QPlainTextEdit()
        self.env.setPlaceholderText("MANGOHUD=1")
        self.env.setPlainText(profile.override_env_vars if profile else "")
        g3.addWidget(self.env, 1)
        self.tabs.addTab(t3, "Environment")

        # ---------- Advanced ----------
        t4 = QWidget(); g4 = QGridLayout(t4)
        g4.setContentsMargins(14, 14, 14, 14); g4.setSpacing(8)
        g4.addWidget(QLabel("Java"), 0, 0)
        jrow = QHBoxLayout()
        self.java_path = QLineEdit(profile.override_java_path if profile else "")
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
        find_btn.setStyleSheet(s_btn(theme.BG2, theme.FG, theme.BG3))
        find_btn.clicked.connect(self._find_java); jrow.addWidget(find_btn)
        browse_btn = QPushButton("Browse")
        browse_btn.setStyleSheet(s_btn(theme.BG2, theme.FG, theme.BG3))
        browse_btn.clicked.connect(self._browse_java); jrow.addWidget(browse_btn)
        g4.addLayout(jrow, 0, 1)

        g4.addWidget(QLabel("Wrapper"), 1, 0)
        self.wrapper = QLineEdit(profile.override_wrapper if profile else "")
        self.wrapper.setPlaceholderText("mangohud --dlsym")
        g4.addWidget(self.wrapper, 1, 1)

        # --- NVIDIA fix, only enabled if Sodium is present ---
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
            getattr(profile, "override_nvidia_fix", False) if profile else False)
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

        btns = QHBoxLayout(); btns.addStretch()
        c = QPushButton("Cancel")
        c.setStyleSheet(s_btn(theme.BG2, theme.FG, theme.BG3))
        c.clicked.connect(self.reject); btns.addWidget(c)
        ok = QPushButton("Create" if self.is_new else "Save")
        ok.setStyleSheet(s_btn_accent())
        ok.clicked.connect(self.accept); btns.addWidget(ok)
        v.addLayout(btns)
        self.name.selectAll(); self.name.setFocus()
        fade_in(self)

    def _refresh_jvm(self):
        auto = " ".join(default_jvm_flags(
            str(int(self.ram.currentData())),
            self.gc.currentData() or self.settings.get("gc", "G1GC")))
        current = self.jvm.toPlainText()
        if getattr(self, "_auto_str", "") and current.startswith(self._auto_str):
            user_part = current[len(self._auto_str):].strip()
            self.jvm.setPlainText((auto + " " + user_part).strip())
        self._auto_str = auto

    def _find_java(self):
        javas = find_javas()
        if not javas:
            QMessageBox.information(self, "No Java", "No Java installations detected.")
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
            self, "Select java executable", str(Path.home()),
            "Java (java)" if not IS_WIN else "Java (*.exe)")
        if path: self.java_path.setText(path)

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
                str(int(self.ram.currentData())), self.loader.currentData())
