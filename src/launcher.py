import os, sys, json, hashlib, zipfile, subprocess, platform, threading, time, tempfile, shlex, shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from PyQt5.QtCore import (
    Qt, QTimer, pyqtSignal, QSize, QPropertyAnimation, QEasingCurve,
)
from PyQt5.QtGui import QFont, QGuiApplication, QColor
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QListWidget, QListWidgetItem, QMenu, QAction,
    QMessageBox, QDialog, QFileDialog, QApplication,
    QLineEdit, QSplitter, QStackedWidget, QStyle, QSizePolicy,
)
import theme
from paths import (MC_ROOT, PROFILES_DIR, MANIFEST_URL,
                   IS_WIN, IS_MAC, NO_WINDOW, XERIA_ROOT)
from java import best_java, recommended_java_for, find_javas
from profile import Profile
from worker import Worker, _shutdown, _leaked_threads
from console import Console
from dialogs import (ChooseInstallDialog, ModpackSearchDialog, fade_in,
                     ProfileDialog)
from browse import BrowseDialog
from settings import Settings, detect_gpu
import auth
from ui_helpers import (
    icon, ICON_SIZE, ICON_SIZE_LG, LOADER_ICON,
    s_icon_btn, s_btn, s_btn_accent, s_entry, s_combo,
    s_textedit, s_spin, s_tabs, s_menu,
    mc_icon_sync, fetch_mc_icon,
    s_btn_launch, s_plus_btn,
)
from loader_icons import (
    loader_icon_sync, fetch_loader_icon, fetch_all_loaders,
)
from menu import MenuView
from account import AccountView
from jvm import default_jvm_flags, build_jvm_flags

from launcher_env import build_launch_env
from launcher_profiles import ProfilesMixin
from launcher_launch import LaunchMixin
from launcher_fetch import FetchMixin


def slide_widget_h(widget, visible, duration=180):
    if visible and widget.isVisible() and widget.maximumWidth() > 100:
        return
    if not visible and (not widget.isVisible() or widget.maximumWidth() < 100):
        return
    if visible:
        widget.setVisible(True)
        start = 0
        end = 340
    else:
        start = max(widget.width(), 200)
        end = 0
    a = QPropertyAnimation(widget, b"maximumWidth", widget)
    a.setDuration(duration)
    a.setStartValue(start)
    a.setEndValue(end)
    a.setEasingCurve(QEasingCurve.OutCubic)
    if not visible:
        def done():
            widget.setVisible(False)
            widget.setMaximumWidth(16777215)
        a.finished.connect(done)
    else:
        widget.setMaximumWidth(0)
        def done():
            widget.setMaximumWidth(340)
        a.finished.connect(done)
    widget._anim_h = a
    a.start()


class MainWindow(LaunchMixin, ProfilesMixin, FetchMixin, QMainWindow):
    mc_log = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.settings = Settings()
        self.account = self.settings.get_account()
        self.setWindowTitle("Xeria Launcher")
        self.resize(1000, 660)
        self.setMinimumSize(820, 520)
        self.setStyleSheet(
            f"QMainWindow,QWidget{{background:{theme.BG};color:{theme.FG}}}")
        self.manifest, self.releases, self.profiles = None, [], []
        self._row_map = []
        self.current_profile = None
        self._workers = []
        self._process = None
        self._running_profile = None
        self._launching_profile = None
        self._build_ui()
        self.mc_log.connect(self._on_mc_log, Qt.QueuedConnection)
        QTimer.singleShot(100, self._startup)

    def _on_mc_log(self, line):
        if line == "__exit__":
            self._set_launch_state(False); return
        if line: self.console.log("mc", line)

    def _set_account(self, acc):
        self.account = acc
        self.settings.set_account(acc)

    @staticmethod
    def _title_color(t):
        """Accent color, except white-on-light which is invisible."""
        a = (t.ACCENT or "").lower()
        if a in ("#ffffff", "#fff", "white"):
            return t.FG
        return t.ACCENT

    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 8, 10, 8); root.setSpacing(8)

        h = QHBoxLayout()
        self.title_lbl = QLabel("Xeria")
        self.title_lbl.setStyleSheet(
            f"background:transparent;color:{self._title_color(theme)};"
            f"font-size:15pt;font-weight:bold")
        h.addWidget(self.title_lbl); h.addStretch()

        self.account_btn = QPushButton("Account")
        self.account_btn.setStyleSheet(s_btn(theme.BG2, theme.FG, theme.BG3))
        self.account_btn.clicked.connect(self.open_account_view)
        h.addWidget(self.account_btn)

        self.gear_btn = QPushButton("Menu")
        self.gear_btn.setStyleSheet(s_btn(theme.BG2, theme.FG, theme.BG3))
        self.gear_btn.clicked.connect(self.toggle_menu)
        h.addWidget(self.gear_btn)
        root.addLayout(h)

        self.split = QSplitter(Qt.Horizontal)
        self.split.setChildrenCollapsible(False)
        self.split.setHandleWidth(20)
        self.split.setStyleSheet("QSplitter::handle{background:transparent}")

        self.left = QFrame()
        self.left.setMinimumWidth(0); self.left.setMaximumWidth(340)
        self.left.setStyleSheet(f"QFrame{{background:{theme.BG2}}}")
        ll = QVBoxLayout(self.left)
        ll.setContentsMargins(14, 12, 14, 12); ll.setSpacing(6)

        bar = QHBoxLayout()
        bar.setSpacing(4)
        lbl_col = QVBoxLayout()
        lbl_col.setSpacing(2)
        self.instances_lbl = QLabel("Instances")
        self.instances_lbl.setStyleSheet(
            f"background:transparent;color:{theme.FG};"
            f"font-size:14pt;font-weight:bold")
        lbl_col.addWidget(self.instances_lbl)
        self.instances_sub = QLabel("")
        self.instances_sub.setStyleSheet(
            f"background:transparent;color:{theme.GRAY};font-size:10pt")
        lbl_col.addWidget(self.instances_sub)
        bar.addLayout(lbl_col, 1)
        self.add_btn = QPushButton("+")
        self.add_btn.setToolTip("New instance")
        self.add_btn.setStyleSheet(s_plus_btn())
        self.add_btn.clicked.connect(self.add_new)
        bar.addWidget(self.add_btn)
        ll.addLayout(bar)

        self.plist = QListWidget()
        self.plist.setFont(QFont(theme.UI_FONT, 10))
        self.plist.setSpacing(0)
        self.plist.setContextMenuPolicy(Qt.CustomContextMenu)
        self.plist.setIconSize(QSize(20, 20))
        self.plist.setStyleSheet(
            f"QListWidget{{background:{theme.BG2};color:{theme.FG};"
            f"border:none;outline:none;padding:0}}"
            f"QListWidget::item{{padding:8px;border:none}}"
            f"QListWidget::item:hover{{background:{theme.BG3};border:none}}"
            f"QListWidget::item:selected{{background:{theme.BG3};color:{theme.FG};"
            f"padding:8px;border:none}}")
        self.plist.currentRowChanged.connect(self._on_row_changed)
        self.plist.customContextMenuRequested.connect(self._ctx_menu)
        ll.addWidget(self.plist, 1)
        self.split.addWidget(self.left)

        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.inst_view = QWidget()
        self.inst_view.setStyleSheet(f"QWidget{{background:{theme.BG}}}")
        il = QVBoxLayout(self.inst_view)
        il.setContentsMargins(0, 0, 0, 0); il.setSpacing(20)

        self.card = QFrame()
        self.card.setStyleSheet(f"QFrame{{background:{theme.BG2}}}")
        cl = QVBoxLayout(self.card)
        cl.setContentsMargins(14, 12, 14, 12); cl.setSpacing(4)

        top = QHBoxLayout()
        info = QVBoxLayout(); info.setSpacing(2)
        self.card_title = QLabel("No instance selected")
        self.card_title.setStyleSheet(
            f"background:transparent;color:{theme.FG};"
            f"font-size:14pt;font-weight:bold")
        info.addWidget(self.card_title)
        self.card_sub = QLabel('Click "+" to create an instance')
        self.card_sub.setStyleSheet(
            f"background:transparent;color:{theme.GRAY};font-size:10pt")
        info.addWidget(self.card_sub)
        top.addLayout(info, 1)

        self.launch_btn = QPushButton("Launch")
        self.launch_btn.setStyleSheet(s_btn_launch())
        self.launch_btn.clicked.connect(self.launch_toggle)
        top.addWidget(self.launch_btn)
        cl.addLayout(top)
        il.addWidget(self.card)

        self.console_frame = QFrame()
        self.console_frame.setStyleSheet(f"QFrame{{background:{theme.BG2}}}")
        cfl = QVBoxLayout(self.console_frame)
        cfl.setContentsMargins(10, 10, 10, 10); cfl.setSpacing(0)
        self.console = Console(); self.console.setMinimumHeight(200)
        cfl.addWidget(self.console, 1)
        il.addWidget(self.console_frame, 1)

        self.stack.addWidget(self.inst_view)

        self.menu_view = MenuView(self, self.settings)
        self.menu_view.theme_changed.connect(self._apply_theme_live)
        self.stack.addWidget(self.menu_view)

        self.account_view = AccountView(
            self, self.settings,
            log=self.console.log)
        self.stack.addWidget(self.account_view)

        self.split.addWidget(self.stack)
        self.split.setSizes([240, 760])
        root.addWidget(self.split, 1)

    def toggle_menu(self):
        i = self.stack.currentIndex()
        if i == 1:
            self.stack.setCurrentIndex(0)
            self._reset_header()
            slide_widget_h(self.left, True)
        else:
            self.stack.setCurrentIndex(1)
            self._set_back_mode("Menu")
            slide_widget_h(self.left, False)

    def open_account_view(self):
        i = self.stack.currentIndex()
        if i == 2:
            self.stack.setCurrentIndex(0)
            self._reset_header()
            slide_widget_h(self.left, True)
        else:
            self.stack.setCurrentIndex(2)
            self.account_view.refresh()
            self._set_back_mode("Account")
            slide_widget_h(self.left, False)

    def _set_back_mode(self, source):
        if source == "Menu":
            self.gear_btn.setText("Back")
            self.account_btn.setText("Account")
        else:
            self.account_btn.setText("Back")
            self.gear_btn.setText("Menu")

    def _reset_header(self):
        self.gear_btn.setText("Menu")
        self.account_btn.setText("Account")

    def _apply_theme_live(self, theme_name, accent_name):
        import theme as _theme
        _theme.apply(theme_name)
        _theme.apply_accent(accent_name)

        app = QApplication.instance()
        pal = app.palette()
        pal.setColor(pal.Window, QColor(_theme.BG))
        pal.setColor(pal.WindowText, QColor(_theme.FG))
        pal.setColor(pal.Base, QColor(_theme.BG2))
        pal.setColor(pal.AlternateBase, QColor(_theme.BG3))
        pal.setColor(pal.Text, QColor(_theme.FG))
        pal.setColor(pal.Button, QColor(_theme.BG3))
        pal.setColor(pal.ButtonText, QColor(_theme.FG))
        pal.setColor(pal.Highlight, QColor(_theme.ACCENT))
        pal.setColor(pal.HighlightedText, QColor(_theme.on_accent()))
        app.setPalette(pal)

        self.setStyleSheet(
            f"QMainWindow,QWidget{{background:{_theme.BG};color:{_theme.FG}}}")

        self.title_lbl.setStyleSheet(
            f"background:transparent;color:{self._title_color(_theme)};"
            f"font-size:15pt;font-weight:bold")

        self.left.setStyleSheet(f"QFrame{{background:{_theme.BG2}}}")
        self.instances_lbl.setStyleSheet(
            f"background:transparent;color:{_theme.FG};"
            f"font-size:14pt;font-weight:bold")
        self.instances_sub.setStyleSheet(
            f"background:transparent;color:{_theme.GRAY};font-size:10pt")
        self.plist.setStyleSheet(
            f"QListWidget{{background:{_theme.BG2};color:{_theme.FG};"
            f"border:none;outline:none;padding:0}}"
            f"QListWidget::item{{padding:8px;border:none}}"
            f"QListWidget::item:hover{{background:{_theme.BG3};border:none}}"
            f"QListWidget::item:selected{{background:{_theme.BG3};"
            f"color:{_theme.FG};padding:8px;border:none}}")
        self.add_btn.setStyleSheet(s_plus_btn())

        self.inst_view.setStyleSheet(
            f"QWidget{{background:{_theme.BG}}}")
        self.card.setStyleSheet(f"QFrame{{background:{_theme.BG2}}}")
        self.card_title.setStyleSheet(
            f"background:transparent;color:{_theme.FG};"
            f"font-size:14pt;font-weight:bold")
        self.card_sub.setStyleSheet(
            f"background:transparent;color:{_theme.GRAY};font-size:10pt")
        self.console_frame.setStyleSheet(
            f"QFrame{{background:{_theme.BG2}}}")
        if hasattr(self.console, "restyle"):
            self.console.restyle()
        if hasattr(self.console, "clear"):
            self.console.clear()

        self.account_btn.setStyleSheet(
            s_btn(_theme.BG2, _theme.FG, _theme.BG3))
        self.gear_btn.setStyleSheet(
            s_btn(_theme.BG2, _theme.FG, _theme.BG3))
        self.launch_btn.setStyleSheet(s_btn_launch())

        self.menu_view.tabs.setStyleSheet(s_tabs())
        if hasattr(self.menu_view, "restyle"):
            self.menu_view.restyle()

        if hasattr(self.account_view, "restyle"):
            self.account_view.restyle()

        self._update_card()
        self.console.log("ok", f"theme={theme_name} accent={accent_name} applied")

    def _track(self, w):
        self._workers.append(w)
        w.finished.connect(
            lambda: self._workers.remove(w) if w in self._workers else None)

    def _startup(self):
        self.load_profiles()
        self.console.log("sys",
            f"platform={platform.system()} python={platform.python_version()}")
        self.console.log("sys", f"gpu={detect_gpu()}")
        self.console.log("sys", f"mc_root={MC_ROOT}")
        self.fetch_manifest()
        fetch_all_loaders(self._apply_loader_icon)

    def _apply_loader_icon(self, name, ic):
        for i, p in enumerate(self._row_map):
            if (p.loader or "").lower() == name:
                it = self.plist.item(i)
                if it is not None:
                    it.setIcon(ic)

    def _ctx_menu(self, pos):
        it = self.plist.itemAt(pos)
        if not it: return
        self.plist.setCurrentItem(it)
        if not self.current_profile: return
        m = QMenu(self); m.setStyleSheet(s_menu())
        h = QAction(self.current_profile.name, m); h.setEnabled(False); m.addAction(h)
        m.addSeparator()
        for label, kind in (("Mods", "mod"), ("Resource Packs", "resourcepack"),
                            ("Shaders", "shader")):
            a = QAction(label, m)
            a.triggered.connect(lambda _, k=kind: self._open_browse(k))
            m.addAction(a)
        m.addSeparator()
        for label, fn in (("Launch", self.launch_toggle),
                          ("Edit...", self.edit_profile),
                          ("Open Folder", self.open_folder),
                          ("Rename...", self.rename_profile),
                          ("Duplicate", self.duplicate_profile)):
            a = QAction(label, m); a.triggered.connect(fn); m.addAction(a)
        m.addSeparator()
        for label, fn in (("Import Instance...", self.import_instance),
                          ("Export as Modrinth pack (.mrpack)", self.export_mrpack),
                          ("Backup Instance", self.backup_instance),
                          ("Copy Launch Command", self.copy_launch_command),
                          ("Open Logs Folder", self.open_logs)):
            a = QAction(label, m); a.triggered.connect(fn); m.addAction(a)
        m.addSeparator()
        a = QAction("Delete", m); a.triggered.connect(self.delete_profile); m.addAction(a)
        m.exec_(self.plist.mapToGlobal(pos))

    def _open_browse(self, kind):
        if not self.current_profile: return
        BrowseDialog(self, self.current_profile, kind, self.console.log).exec_()

    def closeEvent(self, event):
        _shutdown.set()
        p = self._process
        if p and p.poll() is None:
            try:
                if IS_WIN:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                                   capture_output=True, creationflags=NO_WINDOW)
                else: p.terminate()
                p.wait(2000)
            except Exception:
                try: p.kill()
                except Exception: pass
        for w in list(self._workers):
            try:
                if w.isRunning():
                    try:
                        w.log.disconnect(); w.done.disconnect()
                        w.progress.disconnect(); w.progress_end.disconnect()
                    except Exception: pass
                    w.quit()
                    if not w.wait(3000):
                        _leaked_threads.append(w); w.setParent(None)
            except Exception: pass
        event.accept()
