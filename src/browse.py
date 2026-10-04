import time
import io
import json
import hashlib
from pathlib import Path
import requests
from PyQt5.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QSize, QUrl, QObject,
    pyqtSignal, QRunnable, QThreadPool, pyqtSlot,
)
from PyQt5.QtGui import (
    QColor, QIcon, QPixmap, QPainter, QPainterPath, QBrush, QImage,
    QPalette,
)
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSplitter, QFrame,
    QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QMessageBox, QStyle,
)
import theme
from worker import Worker
from console import MiniConsole
import modrinth

try:
    from PIL import Image
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False


# ---------------------------------------------------------------------------
# Icon plumbing
# ---------------------------------------------------------------------------
ICON_SIZE = 32
ICON_SIZE_LG = 64
CACHE_DIR = Path.home() / ".cache" / "mc_launcher" / "icons"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CDN_BASE = "https://cdn.modrinth.com/data/{id}/icon.png"
API_BASE = "https://api.modrinth.com/v2/project/{id}"

_ICON_CACHE = {}          # project_id -> QIcon
_HASH_CACHE = {}          # project_id -> sha1 prefix


def _pid_hash(pid):
    h = _HASH_CACHE.get(pid)
    if h is None:
        h = hashlib.sha1(pid.encode()).hexdigest()[:16]
        _HASH_CACHE[pid] = h
    return h


def slide_widget(widget, visible, duration=180):
    if visible and widget.isVisible(): return
    if not visible and not widget.isVisible(): return
    if visible:
        widget.setVisible(True); start = 0; end = widget.sizeHint().height()
    else:
        start = widget.height(); end = 0
    a = QPropertyAnimation(widget, b"maximumHeight", widget)
    a.setDuration(duration); a.setStartValue(start); a.setEndValue(end)
    a.setEasingCurve(QEasingCurve.OutCubic)
    if not visible:
        def done():
            widget.setVisible(False); widget.setMaximumHeight(16777215)
        a.finished.connect(done)
    else:
        widget.setMaximumHeight(0)
        def done():
            widget.setMaximumHeight(16777215)
        a.finished.connect(done)
    widget._anim = a; a.start()


def make_placeholder(size=ICON_SIZE):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, 4, 4)
    p.fillPath(path, QColor(theme.BG3))
    p.setPen(QColor(theme.GRAY))
    p.drawText(pm.rect(), Qt.AlignCenter, "?")
    p.end()
    return QIcon(pm)


def decode_image(data):
    """Runs on a worker thread. Tries Qt first, then Pillow."""
    if not data:
        return None

    pm = QPixmap()
    if pm.loadFromData(data) and not pm.isNull():
        return pm

    for fmt in (b"PNG", b"JPG", b"JPEG", b"BMP", b"GIF"):
        if pm.loadFromData(data, fmt) and not pm.isNull():
            return pm

    if _HAS_PIL:
        try:
            img = Image.open(io.BytesIO(bytes(data))).convert("RGBA")
            img = img.resize((ICON_SIZE_LG, ICON_SIZE_LG), Image.LANCZOS)
            qimg = QImage(img.tobytes(), img.width, img.height,
                          QImage.Format_RGBA8888).copy()
            pm2 = QPixmap.fromImage(qimg)
            if not pm2.isNull():
                return pm2
        except Exception as e:
            print(f"[pil] decode failed: {e}")

    return None


class _DecodeTask(QRunnable):
    """Runs off the GUI thread. Emits decoded QPixmap back to IconLoader."""
    def __init__(self, loader, project_id, path, data):
        super().__init__()
        self.loader = loader
        self.project_id = project_id
        self.path = path
        self.data = bytes(data)
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self):
        pm = decode_image(self.data)
        if pm is None or pm.isNull():
            print(f"[decode] FAILED pid={self.project_id} "
                  f"bytes={len(self.data)} head={self.data[:16]!r}")
            return
        pm_scaled = pm.scaled(ICON_SIZE_LG, ICON_SIZE_LG,
                              Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.loader._decode_done.emit(self.project_id, pm_scaled, self.path)


class IconLoader(QObject):
    """Parallel async Modrinth icon loader with off-thread decoding."""
    icon_ready = pyqtSignal(str, QIcon)
    _decode_done = pyqtSignal(str, object, object)   # pid, pixmap_or_None, path

    MAX_PARALLEL = 6
    MAX_ATTEMPTS = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.nam = QNetworkAccessManager(self)
        self._queue = []
        self._active = {}
        self._seen = set()
        self._cache = _ICON_CACHE
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)
        self._decode_done.connect(self._on_decode_done)

    # ------------------------------------------------------------------
    def request(self, project_id):
        if not project_id:
            return
        if project_id in self._cache:
            self.icon_ready.emit(project_id, self._cache[project_id])
            return
        if project_id in self._seen:
            return

        h = _pid_hash(project_id)
        path = CACHE_DIR / f"{h}.png"
        if path.exists():
            pm = QPixmap(str(path))
            if not pm.isNull():
                ic = QIcon(pm)
                self._cache[project_id] = ic
                self.icon_ready.emit(project_id, ic)
                return

        self._seen.add(project_id)
        self._queue.append((project_id, path, 0))
        self._pump()

    # ------------------------------------------------------------------
    def _pump(self):
        while len(self._active) < self.MAX_PARALLEL and self._queue:
            project_id, path, attempt = self._queue.pop(0)
            url = CDN_BASE.format(id=project_id)
            req = QNetworkRequest(QUrl(url))
            req.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
            req.setAttribute(QNetworkRequest.CacheLoadControlAttribute,
                             QNetworkRequest.PreferCache)
            reply = self.nam.get(req)
            self._active[reply] = [project_id, path, attempt, False]
            reply.finished.connect(lambda r=reply: self._on_cdn_finished(r))

    # ------------------------------------------------------------------
    def _consume(self, reply):
        meta = self._active.pop(reply, None)
        if meta is None:
            try: reply.deleteLater()
            except Exception: pass
            return None, None, None
        status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
        err = reply.error()
        data = reply.readAll()
        reply.deleteLater()
        return meta, status, (err, data)

    # ------------------------------------------------------------------
    def _dispatch_decode(self, project_id, path, data):
        """Hand data to the pool and free the network slot immediately."""
        self._pool.start(_DecodeTask(self, project_id, path, data))

    def _on_decode_done(self, project_id, pm, path):
        if pm is None:
            return
        ic = QIcon(pm)
        self._cache[project_id] = ic
        try:
            pm.save(str(path), "PNG")
        except Exception:
            pass
        self.icon_ready.emit(project_id, ic)

    # ------------------------------------------------------------------
    def _backoff(self, project_id, path, attempt):
        if attempt >= self.MAX_ATTEMPTS:
            return False
        delay = 400 * (2 ** attempt)
        QTimer.singleShot(
            delay,
            lambda pid=project_id, p=path, a=attempt + 1:
                self._retry(pid, p, a))
        return True

    def _retry(self, project_id, path, attempt):
        self._queue.append((project_id, path, attempt))
        self._pump()

    # ------------------------------------------------------------------
    def _on_cdn_finished(self, reply):
        meta, status, payload = self._consume(reply)
        if meta is None:
            self._pump(); return
        project_id, path, attempt, tried_api = meta
        err, data = payload

        if err == QNetworkReply.NoError and status == 200:
            self._dispatch_decode(project_id, path, data)
            self._pump()
            return

        if status in (429, 503) or (status and 500 <= status < 600) \
                or err not in (QNetworkReply.NoError,
                               QNetworkReply.ContentNotFoundError):
            if self._backoff(project_id, path, attempt):
                self._pump(); return
            self._pump(); return

        if not tried_api:
            self._fetch_via_api(project_id, path, attempt)
            return

        self._pump()

    # ------------------------------------------------------------------
    def _fetch_via_api(self, project_id, path, attempt):
        api = API_BASE.format(id=project_id)
        req = QNetworkRequest(QUrl(api))
        req.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
        reply = self.nam.get(req)
        self._active[reply] = [project_id, path, attempt, True]
        reply.finished.connect(lambda r=reply: self._on_api_finished(r))

    def _on_api_finished(self, reply):
        meta, status, payload = self._consume(reply)
        if meta is None:
            self._pump(); return
        project_id, path, attempt, _ = meta
        err, data = payload

        if status in (429, 503) or (status and 500 <= status < 600):
            if self._backoff(project_id, path, attempt):
                self._pump(); return
            self._pump(); return

        if err != QNetworkReply.NoError:
            self._pump(); return

        try:
            info = json.loads(bytes(data).decode("utf-8"))
            icon_url = info.get("icon_url")
        except Exception:
            icon_url = None

        if not icon_url:
            self._pump(); return

        req = QNetworkRequest(QUrl(icon_url))
        req.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
        rep = self.nam.get(req)
        self._active[rep] = [project_id, path, attempt, True]
        rep.finished.connect(lambda r=rep: self._on_icon_finished(r))

    def _on_icon_finished(self, reply):
        meta, status, payload = self._consume(reply)
        if meta is None:
            self._pump(); return
        project_id, path, attempt, _ = meta
        err, data = payload

        if err == QNetworkReply.NoError and status == 200:
            self._dispatch_decode(project_id, path, data)
            self._pump()
            return

        if status in (429, 503) or (status and 500 <= status < 600):
            if self._backoff(project_id, path, attempt):
                self._pump(); return

        self._pump()


# ---------------------------------------------------------------------------
# Browse dialog
# ---------------------------------------------------------------------------
class BrowseDialog(QDialog):
    def __init__(self, parent, profile, kind, log_fn):
        super().__init__(parent)
        self.profile, self.kind, self.log_fn = profile, kind, log_fn
        self.results_data, self._req_id = [], 0
        self._w = None
        self._last_query = ""
        self._placeholder = make_placeholder()
        self._placeholder_sm = self._placeholder.pixmap(ICON_SIZE, ICON_SIZE)
        self._placeholder_lg = self._placeholder.pixmap(ICON_SIZE_LG, ICON_SIZE_LG)

        title = {"mod": "Mods", "resourcepack": "Resource Packs",
                 "shader": "Shaders"}[kind]
        self.setWindowTitle(f"{title} — {profile.name}")
        self.resize(900, 640); self.setMinimumSize(620, 420)
        self.setStyleSheet(f"QDialog{{background:{theme.BG};border:none}}")

        win_ic = QIcon.fromTheme("applications-games")
        if not win_ic.isNull():
            self.setWindowIcon(win_ic)

        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10); v.setSpacing(6)

        # --- header --------------------------------------------------------
        head_row = QHBoxLayout(); head_row.setSpacing(6)
        head_ic = QLabel()
        hi = QIcon.fromTheme("system-software-install")
        if hi.isNull():
            hi = QIcon.fromTheme("package-x-generic")
        if not hi.isNull():
            head_ic.setPixmap(hi.pixmap(20, 20))
        head = QLabel(f"{title}  →  {profile.name}")
        head.setStyleSheet(f"color:{theme.FG};font-size:13pt;font-weight:bold;"
                           f"background:transparent;border:none")
        head_row.addWidget(head_ic); head_row.addWidget(head); head_row.addStretch()
        v.addLayout(head_row)

        if kind == "mod" and (profile.loader or "vanilla").lower() == "vanilla":
            warn = QLabel("⚠  This profile is vanilla — mods won't load.")
            warn.setStyleSheet(
                f"color:{theme.YELLOW};font-size:9pt;padding:6px;"
                f"background:{theme.BG2};border:none")
            warn.setWordWrap(True); v.addWidget(warn)

        # --- search --------------------------------------------------------
        row = QHBoxLayout(); row.setSpacing(0)
        self.search = QLineEdit()
        self.search.setPlaceholderText(f"Search {title.lower()}...")
        self.search.setStyleSheet(
            f"QLineEdit{{background:{theme.BG2};color:{theme.FG};"
            f"border:none;padding:8px}}")
        search_ic = QIcon.fromTheme("edit-find")
        if not search_ic.isNull():
            self.search.addAction(search_ic, QLineEdit.LeadingPosition)
        row.addWidget(self.search, 1)
        v.addLayout(row)

        # --- splitter ------------------------------------------------------
        self.split = QSplitter(Qt.Vertical)
        self.split.setChildrenCollapsible(False)
        self.split.setHandleWidth(0)
        self.split.setStyleSheet("QSplitter{border:none;background:transparent}"
                                 "QSplitter::handle{background:transparent;height:0}")

        self.list = QListWidget()
        self.list.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.setStyleSheet(
            f"QListWidget{{background:{theme.BG2};color:{theme.FG};"
            f"border:none;padding:0;outline:0}}"
            f"QListWidget::item{{padding:8px;border:none}}"
            f"QListWidget::item:hover{{background:{theme.BG3};border:none}}"
            f"QListWidget::item:selected{{background:{theme.GREEN};border:none}}")
        self.split.addWidget(self.list)

        # --- info panel ----------------------------------------------------
        self.info = QFrame()
        self.info.setFrameShape(QFrame.NoFrame)
        self.info.setStyleSheet(f"QFrame{{background:{theme.BG2};border:none}}")
        il = QHBoxLayout(self.info)
        il.setContentsMargins(10, 8, 10, 8); il.setSpacing(10)
        self.d_icon = QLabel()
        self.d_icon.setFixedSize(ICON_SIZE_LG, ICON_SIZE_LG)
        self.d_icon.setStyleSheet(f"background:{theme.BG3};border:none")
        self.d_icon.setAlignment(Qt.AlignCenter)
        il.addWidget(self.d_icon)

        text_col = QVBoxLayout(); text_col.setSpacing(4)
        title_row = QHBoxLayout(); title_row.setSpacing(6)
        info_ic = QLabel()
        ii = QIcon.fromTheme("dialog-information")
        if not ii.isNull():
            info_ic.setPixmap(ii.pixmap(16, 16))
        title_row.addWidget(info_ic)
        self.d_title = QLabel("")
        self.d_title.setStyleSheet(
            f"color:{theme.FG};font-weight:bold;font-size:11pt;"
            f"background:transparent;border:none")
        title_row.addWidget(self.d_title); title_row.addStretch(1)
        text_col.addLayout(title_row)

        self.d_meta = QLabel("")
        self.d_meta.setStyleSheet(f"color:{theme.GRAY};font-size:9pt;"
                                  f"background:transparent;border:none")
        text_col.addWidget(self.d_meta)

        self.d_desc = QLabel("")
        self.d_desc.setStyleSheet(f"color:{theme.FG};font-size:9pt;"
                                  f"background:transparent;border:none")
        self.d_desc.setWordWrap(True); text_col.addWidget(self.d_desc)
        il.addLayout(text_col, 1)
        self.split.addWidget(self.info)
        self.info.setVisible(False); self.info.setMaximumHeight(0)

        # --- activity log --------------------------------------------------
        self.log_frame = QFrame()
        self.log_frame.setFrameShape(QFrame.NoFrame)
        self.log_frame.setStyleSheet(
            f"QFrame{{background:{theme.BG2};border:none}}")
        lfl = QVBoxLayout(self.log_frame)
        lfl.setContentsMargins(0, 0, 0, 0); lfl.setSpacing(0)
        lh_row = QHBoxLayout()
        lh_row.setContentsMargins(6, 4, 6, 4); lh_row.setSpacing(6)
        lh_ic = QLabel()
        li = QIcon.fromTheme("utilities-terminal")
        if not li.isNull():
            lh_ic.setPixmap(li.pixmap(16, 16))
        lh_row.addWidget(lh_ic)
        lh = QLabel("Activity")
        lh.setStyleSheet(f"color:{theme.GRAY};font-size:8pt;"
                         f"background:transparent;border:none")
        lh_row.addWidget(lh); lh_row.addStretch(1)
        lfl.addLayout(lh_row)
        self.log_view = MiniConsole(); lfl.addWidget(self.log_view, 1)
        self.split.addWidget(self.log_frame)
        self.log_frame.setVisible(False); self.log_frame.setMaximumHeight(0)

        self.split.setSizes([1, 0, 0])
        v.addWidget(self.split, 1)

        # --- buttons (no Close) -------------------------------------------
        btns = QHBoxLayout(); btns.setSpacing(6)

        refresh = QPushButton("Refresh")
        refresh.setIcon(self._icon("view-refresh", QStyle.SP_BrowserReload))
        refresh.setIconSize(QSize(16, 16))
        refresh.setStyleSheet(self._btn_style())
        refresh.clicked.connect(self.search_now)
        btns.addWidget(refresh); btns.addStretch()

        self.install_btn = QPushButton("Install Selected")
        self.install_btn.setIcon(self._icon("download", QStyle.SP_ArrowDown))
        self.install_btn.setIconSize(QSize(16, 16))
        self.install_btn.setStyleSheet(
            f"QPushButton{{background:{theme.ACCENT};color:{theme.DARK};"
            f"border:none;padding:8px 20px;font-weight:bold}}"
            f"QPushButton:hover{{background:{theme.ACCENT2}}}"
            f"QPushButton:disabled{{background:{theme.BG3};color:{theme.GRAY}}}")
        self.install_btn.clicked.connect(self.install_selected)
        btns.addWidget(self.install_btn)

        v.addLayout(btns)

        # --- timers --------------------------------------------------------
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(2000)
        self._debounce.timeout.connect(self.search_now)

        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.setInterval(2000)
        self._idle_timer.timeout.connect(self._auto_refire)

        # --- icon loader ---------------------------------------------------
        self.icon_loader = IconLoader(self)
        self.icon_loader.icon_ready.connect(self._on_icon_ready)

        # --- signals -------------------------------------------------------
        self.search.textChanged.connect(self._schedule_search)
        self.list.currentRowChanged.connect(self.on_select)
        self.list.itemSelectionChanged.connect(self._reapply_colors)
        self.search.setFocus()
        self._log("info", f"ready — {title} on {profile.name}")

    # ----------------------------------------------------------------------
    def _btn_style(self):
        return (f"QPushButton{{background:{theme.BG3};color:{theme.FG};"
                f"border:none;padding:8px 16px}}"
                f"QPushButton:hover{{background:{theme.BORDER}}}")

    def _icon(self, name, fallback):
        ic = QIcon.fromTheme(name)
        return ic if not ic.isNull() else self.style().standardIcon(fallback)

    def _log(self, tag, msg):
        self.log_view.log(tag, msg); self.log_fn(tag, msg)
        if not self.log_frame.isVisible():
            slide_widget(self.log_frame, True)

    # --- search scheduling -------------------------------------------------
    def _schedule_search(self, _):
        q = self.search.text().strip()
        if q == self._last_query:
            return
        self._debounce.stop(); self._debounce.start()
        self._idle_timer.stop(); self._idle_timer.start()

    def _auto_refire(self):
        q = self.search.text().strip()
        if q and q == self._last_query:
            self._last_query = ""
            self.search_now(silent=True)

    def _set_info(self, visible):
        slide_widget(self.info, visible)

    def search_now(self, silent=False):
        self._debounce.stop()
        q = self.search.text().strip()
        if not q:
            self.list.clear(); self.results_data = []
            self._set_info(False); return
        if q == self._last_query and not silent:
            return
        self._last_query = q
        self._idle_timer.stop()

        prev = self._w
        if prev and prev.isRunning():
            prev.quit(); prev.wait(500)
        self._req_id += 1; rid = self._req_id
        if not silent:
            self.list.clear(); self._set_info(False)
        self._log("net", f"query '{q}' ({self.kind})")
        loader = (self.profile.loader or "vanilla").lower()
        w = Worker(lambda log, progress, progress_end: modrinth.search(
            q, self.kind, self.profile.version, loader))
        w.done.connect(lambda r, r_=rid: self._apply(r, r_), Qt.QueuedConnection)
        w.log.connect(self._log, Qt.QueuedConnection)
        self._w = w; w.start()

    # --- results -----------------------------------------------------------
    def _installed_keys(self):
        sub = {"mod": "mods", "resourcepack": "resourcepacks",
               "shader": "shaderpacks"}[self.kind]
        d = self.profile.dir / sub
        if not d.exists():
            return set()
        return {f.stem.lower().split("-")[0] for f in d.iterdir()}

    def _same_as_current(self, hits):
        if not hits or len(hits) != len(self.results_data):
            return False
        for a, b in zip(hits, self.results_data):
            if (a.get("id") or a.get("project_id")) != \
               (b.get("id") or b.get("project_id")):
                return False
        return True

    def _apply(self, hits, rid):
        if rid != self._req_id:
            return
        hits = hits or []

        # Silent refire with unchanged results → don't rebuild the list.
        if self._same_as_current(hits):
            return

        self.list.clear()
        self.results_data = hits
        installed = self._installed_keys()

        for h in self.results_data:
            loaders = [c for c in h.get("categories", [])
                       if c in ("fabric", "forge", "neoforge", "quilt")]
            tag = f"  [{','.join(loaders)}]" if loaders else ""
            key = h["title"].lower().replace(" ", "")
            mark = "●" if key in installed else "○"

            it = QListWidgetItem(
                f" {mark}  {h['title']}{tag}   ·  "
                f"{h['author']}  ·  {h['dl']:,} Downloads"
            )
            pid = h.get("id") or h.get("project_id")
            it.setData(Qt.UserRole + 1, pid)
            it.setData(Qt.UserRole + 2, key in installed)

            if key in installed:
                it.setForeground(QBrush(QColor(theme.GREEN)))
            else:
                it.setForeground(QBrush(QColor(theme.FG)))
            it.setIcon(self._placeholder)
            self.list.addItem(it)

        for h in self.results_data:
            pid = h.get("id") or h.get("project_id")
            if pid:
                self.icon_loader.request(pid)

        if self.results_data:
            self._log("ok", f"{len(self.results_data)} results")
            self.list.setCurrentRow(0)
        else:
            self._log("warn", "no results")

    def _reapply_colors(self):
        pal = self.list.palette()
        pal.setColor(QPalette.HighlightedText, QColor(theme.FG))
        self.list.setPalette(pal)
        for i in range(self.list.count()):
            it = self.list.item(i)
            color = QColor(theme.GREEN) if it.data(Qt.UserRole + 2) \
                    else QColor(theme.FG)
            it.setForeground(QBrush(color))

    def _on_icon_ready(self, project_id, icon):
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(Qt.UserRole + 1) == project_id:
                it.setIcon(icon)
        row = self.list.currentRow()
        if 0 <= row < len(self.results_data):
            h = self.results_data[row]
            if (h.get("id") or h.get("project_id")) == project_id:
                self.d_icon.setPixmap(icon.pixmap(ICON_SIZE_LG, ICON_SIZE_LG))

    def on_select(self, row):
        if row < 0 or row >= len(self.results_data):
            self._set_info(False); return
        h = self.results_data[row]
        self.d_title.setText(h["title"])
        self.d_meta.setText(
            f"by {h['author']}  ·  {h['dl']:,} Downloads  ·  modrinth")
        self.d_desc.setText(h["desc"][:400])

        pid = h.get("id") or h.get("project_id")
        if pid and pid in _ICON_CACHE:
            self.d_icon.setPixmap(
                _ICON_CACHE[pid].pixmap(ICON_SIZE_LG, ICON_SIZE_LG))
        else:
            self.d_icon.setPixmap(self._placeholder_lg)
            if pid:
                self.icon_loader.request(pid)

        self._set_info(True)
        self._reapply_colors()

    # --- install -----------------------------------------------------------
    def install_selected(self):
        row = self.list.currentRow()
        if row < 0 or row >= len(self.results_data):
            QMessageBox.information(self, "Select", "Pick an item first.")
            return
        hit = self.results_data[row]
        self.install_btn.setEnabled(False)
        self._log("info", f"installing {hit['title']}")
        loader = (self.profile.loader or "vanilla").lower()
        w = Worker(lambda log, progress, progress_end:
                   self._install(hit, loader, progress, progress_end))
        w.log.connect(self._log, Qt.QueuedConnection)
        w.progress.connect(lambda *a: self._log("progress", a), Qt.QueuedConnection)
        w.progress_end.connect(lambda: None, Qt.QueuedConnection)
        w.done.connect(lambda p: self._install_done(hit, p), Qt.QueuedConnection)
        self._w = w; w.start()

    def _install(self, hit, loader, progress, progress_end):
        picked = modrinth.pick_file(hit["id"], self.profile.version,
                                    self.kind, loader)
        if not picked:
            self._log("warn", "no compatible file"); return None
        url, filename = picked
        sub = {"mod": "mods", "resourcepack": "resourcepacks",
               "shader": "shaderpacks"}[self.kind]
        dest = self.profile.dir / sub / filename
        with requests.get(url, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            done = 0; b0 = 0; tl = time.time()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(65536):
                    f.write(chunk); done += len(chunk)
                    now = time.time()
                    if now - tl >= 0.2 or done == total:
                        spd = (done - b0) / (now - tl) if now > tl else 0
                        progress(filename, done, total, "", self._speed(spd))
                        tl = now; b0 = done
        progress_end()
        return str(dest)

    @staticmethod
    def _speed(bps):
        if bps > 1024 * 1024: return f"{bps / 1024 / 1024:.1f} MB/s"
        if bps > 1024: return f"{bps / 1024:.0f} KB/s"
        return f"{bps:.0f} B/s"

    def _install_done(self, hit, path):
        self.install_btn.setEnabled(True)
        if path:
            self._log("ok", f"installed → {Path(path).name}")
            pid = hit.get("id") or hit.get("project_id")
            if pid:
                self.icon_loader.request(pid)
            self._mark_installed(hit["title"])
            self._last_query = ""
            self.search_now(silent=True)
        else:
            self._log("error", f"install failed: {hit['title']}")

    def _mark_installed(self, title):
        key = title.lower().replace(" ", "")
        for i in range(self.list.count()):
            it = self.list.item(i)
            txt = it.text().lower().replace(" ", "")
            if key in txt:
                it.setData(Qt.UserRole + 2, True)
                it.setForeground(QBrush(QColor(theme.GREEN)))
        self._reapply_colors()

    # --- shutdown ----------------------------------------------------------
    def closeEvent(self, event):
        w = getattr(self, "_w", None)
        if w and w.isRunning():
            try:
                w.log.disconnect(); w.done.disconnect()
                w.progress.disconnect(); w.progress_end.disconnect()
            except Exception:
                pass
            w.quit(); w.wait(1000)
        super().closeEvent(event)
