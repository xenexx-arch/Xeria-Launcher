import time
import json
from pathlib import Path
from urllib.parse import urlencode
import requests
from PyQt5.QtCore import Qt, QTimer, QSize, QUrl
from PyQt5.QtGui import QIcon
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QLineEdit, QListWidget, QListWidgetItem, QWidget,
    QPushButton, QMessageBox, QStyle,
)
import theme
from worker import Worker
from console import MiniConsole

from browse_common import (
    ICON_SIZE_ROW, _ICON_CACHE, make_placeholder,
    IconLoader, GalleryLoader,
    square_icon, square_icon_pixmap,
)
from browse_detail import DetailPanel


class BrowseBase(QDialog):
    KIND = ""
    TITLE = ""
    FOLDER = ""
    SEARCH_PH = ""
    HEADER_ICON = "package-x-generic"
    VANILLA_WARN = None

    ROW_PAD = 4
    ROW_GAP = 6

    def __init__(self, parent, profile, log_fn):
        super().__init__(parent)
        self.profile, self.log_fn = profile, log_fn
        self.results_data, self._req_id = [], 0
        self._w = None
        self._last_query = ""
        self._rows = {}
        self._selected_row = -1
        self._search_reply = None

        self.setWindowTitle(f"{self.TITLE} — {profile.name}")
        self.resize(1080, 680); self.setMinimumSize(760, 460)
        self.setStyleSheet(f"QDialog{{background:{theme.BG};border:none}}")

        win_ic = QIcon.fromTheme("applications-games")
        if not win_ic.isNull():
            self.setWindowIcon(win_ic)

        self._nam = QNetworkAccessManager(self)

        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10); v.setSpacing(6)

        head_row = QHBoxLayout(); head_row.setSpacing(6)
        head_ic = QLabel()
        hi = QIcon.fromTheme(self.HEADER_ICON)
        if hi.isNull():
            hi = QIcon.fromTheme("package-x-generic")
        if not hi.isNull():
            head_ic.setPixmap(hi.pixmap(20, 20))
        head = QLabel(f"{self.TITLE}  →  {profile.name}")
        head.setStyleSheet(f"color:{theme.FG};font-size:13pt;font-weight:bold;"
                           f"background:transparent;border:none")
        head_row.addWidget(head_ic); head_row.addWidget(head); head_row.addStretch()
        v.addLayout(head_row)

        if self.VANILLA_WARN and (profile.loader or "vanilla").lower() == "vanilla":
            warn = QLabel(self.VANILLA_WARN)
            warn.setStyleSheet(
                f"color:{theme.YELLOW};font-size:9pt;padding:6px;"
                f"background:{theme.BG2};border:none")
            warn.setWordWrap(True); v.addWidget(warn)

        row = QHBoxLayout(); row.setSpacing(0)
        self.search = QLineEdit()
        self.search.setPlaceholderText(self.SEARCH_PH)
        self.search.setStyleSheet(
            f"QLineEdit{{background:{theme.BG2};color:{theme.FG};"
            f"border:none;padding:8px}}")
        search_ic = QIcon.fromTheme("edit-find")
        if not search_ic.isNull():
            self.search.addAction(search_ic, QLineEdit.LeadingPosition)
        row.addWidget(self.search, 1)
        v.addLayout(row)

        body = QHBoxLayout()
        body.setSpacing(6)

        left = QWidget()
        left.setStyleSheet("background:transparent")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0); ll.setSpacing(4)

        self.list = QListWidget()
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.setSelectionMode(QListWidget.SingleSelection)
        self.list.setIconSize(QSize(ICON_SIZE_ROW, ICON_SIZE_ROW))
        self.list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setStyleSheet(
            f"QListWidget{{background:{theme.BG2};color:{theme.FG};"
            f"border:none;padding:0;outline:0}}"
            f"QListWidget::item{{padding:0;border:none}}"
            f"QListWidget::item:selected{{background:{theme.BG3};border:none}}"
            f"QListWidget::item:hover{{background:{theme.BG3};border:none}}"
            f"QScrollBar:vertical{{background:{theme.BG2};width:8px;margin:0}}"
            f"QScrollBar::handle{{background:{theme.BG3};min-height:20px}}"
            f"QScrollBar::add-line,QScrollBar::sub-line{{height:0}}"
            f"QScrollBar::add-page,QScrollBar::sub-page{{background:transparent}}")
        self.list.currentRowChanged.connect(self._on_row_changed)
        self.list.verticalScrollBar().valueChanged.connect(
            self._request_visible_icons)
        ll.addWidget(self.list, 1)

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
        self.log_view = MiniConsole()
        self.log_view.setMaximumHeight(90)
        lfl.addWidget(self.log_view, 1)
        ll.addWidget(self.log_frame)

        body.addWidget(left, 1)

        self.detail = DetailPanel(nam=self._nam)
        body.addWidget(self.detail, 0)

        v.addLayout(body, 1)

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
            f"QPushButton{{background:{theme.ACCENT};color:{theme.on_accent()};"
            f"border:none;padding:8px 20px;font-weight:bold}}"
            f"QPushButton:hover{{background:{theme.ACCENT2}}}"
            f"QPushButton:disabled{{background:{theme.BG3};color:{theme.GRAY}}}")
        self.install_btn.clicked.connect(self.install_selected)
        btns.addWidget(self.install_btn)
        v.addLayout(btns)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(700)
        self._debounce.timeout.connect(self.search_now)

        self.icon_loader = IconLoader(self, nam=self._nam)
        self.icon_loader.icon_ready.connect(self._on_icon_ready)

        self.gallery_loader = GalleryLoader(self, nam=self._nam)
        self.gallery_loader.shot_ready.connect(self._on_shot_ready)

        self.search.textChanged.connect(self._schedule_search)
        self.search.setFocus()
        self._log("info", f"ready — {self.TITLE} on {profile.name}")

    def _row_height(self):
        return ICON_SIZE_ROW + self.ROW_PAD * 2 + self.ROW_GAP

    def pick_download(self, hit):
        raise NotImplementedError

    def _search_url(self, query):
        raise NotImplementedError

    def _parse_search_response(self, obj):
        return [{"id": h["project_id"], "title": h["title"],
                 "author": h["author"], "desc": h.get("description", ""),
                 "dl": h.get("downloads", 0),
                 "categories": h.get("categories", [])}
                for h in obj.get("hits", [])]

    def row_title(self, hit):
        return hit["title"]

    def row_subtitle(self, hit):
        loaders = [c for c in hit.get("categories", [])
                   if c in ("fabric", "forge", "neoforge", "quilt")]
        tag = f"  [{','.join(loaders)}]" if loaders else ""
        return f"by {hit['author']}{tag}  ·  {hit['dl']:,} dl"

    def _btn_style(self):
        return (f"QPushButton{{background:{theme.BG3};color:{theme.FG};"
                f"border:none;padding:8px 16px}}"
                f"QPushButton:hover{{background:{theme.BORDER}}}")

    def _icon(self, name, fallback):
        ic = QIcon.fromTheme(name)
        return ic if not ic.isNull() else self.style().standardIcon(fallback)

    def _log(self, tag, msg):
        self.log_view.log(tag, msg); self.log_fn(tag, msg)

    def _schedule_search(self, _):
        q = self.search.text().strip()
        if q == self._last_query:
            return
        self._debounce.stop()
        self._debounce.start()

    def search_now(self, silent=False):
        self._debounce.stop()
        q = self.search.text().strip()
        if not q:
            self.list.clear(); self.results_data = []
            self._rows.clear()
            self.detail.pid = None
            self.detail.close_panel()
            return
        if q == self._last_query and not silent:
            return
        self._last_query = q
        self._req_id += 1; rid = self._req_id

        if self._search_reply is not None:
            try:
                self._search_reply.abort()
                self._search_reply.deleteLater()
            except Exception:
                pass
            self._search_reply = None

        if not silent:
            self.list.clear()
            self._rows.clear()
            self.detail.pid = None
            self.detail.close_panel()

        url, params = self._search_url(q)
        full = f"{url}?{urlencode(params)}"
        req = QNetworkRequest(QUrl(full))
        req.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
        req.setRawHeader(b"User-Agent", b"Xeria-Launcher/1.0")
        self._log("net", f"query '{q}' ({self.KIND})")
        reply = self._nam.get(req)
        self._search_reply = reply
        reply.finished.connect(lambda r=reply, r_=rid: self._on_search(r, r_))

    def _on_search(self, reply, rid):
        if rid != self._req_id:
            try: reply.deleteLater()
            except Exception: pass
            return
        status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
        data = reply.readAll()
        err = reply.error()
        reply.deleteLater()
        self._search_reply = None
        if err != 0 or status != 200:
            self._log("error", f"search failed: status={status}")
            return
        try:
            obj = json.loads(bytes(data).decode("utf-8"))
        except Exception as e:
            self._log("error", f"search parse failed: {e}")
            return
        hits = self._parse_search_response(obj)
        self._apply(hits, rid)

    def _installed_keys(self):
        d = self.profile.dir / self.FOLDER
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
        if self._same_as_current(hits):
            return

        self.list.clear()
        self._rows.clear()
        self.results_data = hits
        installed = self._installed_keys()

        for h in self.results_data:
            key = h["title"].lower().replace(" ", "")
            is_installed = key in installed

            it = QListWidgetItem()
            it.setSizeHint(QSize(0, self._row_height()))
            it.setData(Qt.UserRole + 1, h.get("id") or h.get("project_id"))
            it.setData(Qt.UserRole + 2, is_installed)
            self.list.addItem(it)

            row = self._make_row(h, is_installed)
            self.list.setItemWidget(it, row)
            self._rows[h.get("id") or h.get("project_id")] = row

        if self.results_data:
            self._log("ok", f"{len(self.results_data)} results")
            self.list.setCurrentRow(0)
            QTimer.singleShot(50, self._request_visible_icons)
        else:
            self._log("warn", "no results")
            self.detail.pid = None
            self.detail.close_panel()

    def _request_visible_icons(self, *args):
        if not self.results_data:
            return
        first = self.list.indexAt(self.list.rect().topLeft()).row()
        last = self.list.indexAt(self.list.rect().bottomLeft()).row()
        if first < 0:
            first = 0
        if last < 0:
            last = len(self.results_data) - 1
        for i in range(max(0, first), min(len(self.results_data), last + 2)):
            pid = (self.results_data[i].get("id") or
                   self.results_data[i].get("project_id"))
            if pid:
                self.icon_loader.request(pid)

    def _make_row(self, hit, is_installed):
        row = QWidget()
        row.setObjectName("modRow")
        row.setStyleSheet(
            f"QWidget#modRow{{background:transparent;border:none;"
            f"border-bottom:{self.ROW_GAP}px solid {theme.BG};}}")
        h = QHBoxLayout(row)
        h.setContentsMargins(self.ROW_PAD, self.ROW_PAD,
                             self.ROW_PAD, self.ROW_PAD)
        h.setSpacing(12)

        ic = QLabel()
        ic.setFixedSize(ICON_SIZE_ROW, ICON_SIZE_ROW)
        ic.setAlignment(Qt.AlignCenter)
        ph = make_placeholder(ICON_SIZE_ROW).pixmap(
            ICON_SIZE_ROW, ICON_SIZE_ROW)
        ic.setPixmap(square_icon_pixmap(ph, ICON_SIZE_ROW))

        ic_host = QWidget()
        ic_host.setStyleSheet("background:transparent;border:none")
        ic_host.setFixedWidth(ICON_SIZE_ROW)
        ic_col = QVBoxLayout(ic_host)
        ic_col.setContentsMargins(0, 0, 0, 0)
        ic_col.setSpacing(0)
        ic_col.addStretch(1)
        ic_col.addWidget(ic, 0, Qt.AlignHCenter)
        ic_col.addStretch(1)
        h.addWidget(ic_host, 0)

        col = QVBoxLayout()
        col.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)

        title = QLabel(self.row_title(hit))
        title.setStyleSheet(
            f"color:{theme.FG};font-weight:bold;font-size:11pt;"
            f"font-family:'{theme.UI_FONT}';background:transparent")
        title_row.addWidget(title)

        if is_installed:
            badge = QLabel("Installed")
            badge.setStyleSheet(
                f"color:{theme.ACCENT};"
                f"font-family:'{theme.UI_FONT}';font-size:8pt;"
                f"font-weight:bold;"
                f"background:transparent")
            title_row.addWidget(badge)

        title_row.addStretch(1)
        col.addLayout(title_row)

        meta = QLabel(self.row_subtitle(hit))
        meta.setStyleSheet(
            f"color:{theme.GRAY};font-size:9pt;"
            f"font-family:'{theme.UI_FONT}';background:transparent")
        col.addWidget(meta)

        h.addLayout(col, 1)
        row._icon = ic
        return row

    def _on_row_changed(self, row):
        if row < 0 or row >= len(self.results_data):
            return
        self._selected_row = row
        hit = self.results_data[row]
        pid = hit.get("id") or hit.get("project_id")

        key = hit["title"].lower().replace(" ", "")
        installed = key in self._installed_keys()
        if installed:
            self.install_btn.setEnabled(False)
            self.install_btn.setText("Already Installed")
        else:
            self.install_btn.setEnabled(True)
            self.install_btn.setText("Install Selected")

        if pid:
            self.icon_loader.request(pid)

        self.detail.open_for(hit)
        if pid and pid in _ICON_CACHE:
            self.detail.set_icon(_ICON_CACHE[pid])

        if pid:
            self.gallery_loader.request(pid)

    def _on_icon_ready(self, project_id, icon):
        row = self._rows.get(project_id)
        if row is not None and hasattr(row, "_icon"):
            pm = square_icon(icon, ICON_SIZE_ROW)
            if pm is not None:
                row._icon.setPixmap(pm)
        if self.detail.pid == project_id:
            self.detail.set_icon(icon)

    def _on_shot_ready(self, project_id, idx, pm):
        if self.detail.pid == project_id:
            self.detail.add_screenshot(idx, pm)

    def _selected_hit(self):
        row = self.list.currentRow()
        if row < 0 or row >= len(self.results_data):
            return None
        return self.results_data[row]

    def install_selected(self):
        hit = self._selected_hit()
        if hit is None:
            QMessageBox.information(self, "Select", "Click a row first.")
            return
        self.install_btn.setEnabled(False)
        self._log("info", f"installing {hit['title']}")
        w = Worker(lambda log, progress, progress_end:
                   self._install(hit, progress, progress_end))
        w.log.connect(self._log, Qt.QueuedConnection)
        w.progress.connect(lambda *a: self._log("progress", a), Qt.QueuedConnection)
        w.progress_end.connect(lambda: None, Qt.QueuedConnection)
        w.done.connect(lambda p: self._install_done(hit, p), Qt.QueuedConnection)
        self._w = w; w.start()

    def _install(self, hit, progress, progress_end):
        picked = self.pick_download(hit)
        if not picked:
            self._log("warn", "no compatible file"); return None
        url, filename = picked
        dest = self.profile.dir / self.FOLDER / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
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
            self._last_query = ""
            self.search_now(silent=True)
        else:
            self._log("error", f"install failed: {hit['title']}")

    def closeEvent(self, event):
        w = getattr(self, "_w", None)
        if w and w.isRunning():
            try:
                w.log.disconnect(); w.done.disconnect()
                w.progress.disconnect(); w.progress_end.disconnect()
            except Exception:
                pass
            w.quit(); w.wait(1000)
        if self._search_reply is not None:
            try:
                self._search_reply.abort()
                self._search_reply.deleteLater()
            except Exception:
                pass
        super().closeEvent(event)
