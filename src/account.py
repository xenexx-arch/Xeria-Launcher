# account.py
from PyQt5.QtCore import QSize, Qt, QPoint, QRect
from PyQt5.QtGui import QColor, QFont, QPen
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QInputDialog, QMessageBox, QMenu,
    QApplication, QFrame, QStyledItemDelegate, QStyle,
)
import theme
import auth
from ui_helpers import s_plus_btn


ROW_GAP = 0
ROW_PAD_V = 16
LIST_FONT_SIZE = 10


class _AccountItemDelegate(QStyledItemDelegate):
    """Single-line row: accent marker + name + [type], all vertically centered."""

    def paint(self, painter, option, index):
        painter.save()

        row = option.rect.adjusted(0, ROW_GAP // 2, 0, -ROW_GAP // 2)

        if option.state & QStyle.State_Selected:
            painter.fillRect(row, QColor(theme.BG3))
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(row, QColor(theme.BG3))

        text = index.data(Qt.DisplayRole) or ""
        if not text:
            painter.restore()
            return

        painter.setFont(QFont(option.font))
        fm = painter.fontMetrics()

        r = row.adjusted(10, ROW_PAD_V // 2, -10, -ROW_PAD_V // 2)

        painter.setPen(QPen(QColor(theme.FG)))
        painter.drawText(r, Qt.AlignLeft | Qt.AlignVCenter, text)

        marker = text[0]
        marker_w = fm.horizontalAdvance(marker)
        y = r.top() + (r.height() - fm.height()) // 2
        mrect = QRect(r.left(), y, marker_w + 1, fm.height())
        painter.setPen(QPen(QColor(theme.ACCENT)))
        painter.drawText(mrect, Qt.AlignLeft | Qt.AlignVCenter, marker)

        painter.restore()

    def sizeHint(self, option, index):
        fm = option.fontMetrics
        return QSize(0, fm.height() + ROW_PAD_V + ROW_GAP)


class AccountView(QWidget):
    def __init__(self, parent, settings, log):
        super().__init__(parent)
        self.settings = settings
        self._log = log
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(20)

        self.header = QFrame()
        self.header.setStyleSheet(
            f"QFrame{{background:{theme.BG2};border:none}}")
        hdr = QHBoxLayout(self.header)
        hdr.setContentsMargins(14, 12, 14, 12)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self.title_lbl = QLabel("Accounts")
        self.title_lbl.setStyleSheet(
            f"background:transparent;color:{theme.FG};"
            f"font-size:14pt;font-weight:bold")
        title_col.addWidget(self.title_lbl)
        self.title_spacer = QLabel("")
        self.title_spacer.setStyleSheet(
            f"background:transparent;color:{theme.GRAY};font-size:10pt")
        title_col.addWidget(self.title_spacer)
        hdr.addLayout(title_col, 1)

        self.add_btn = QPushButton("+")
        self.add_btn.setToolTip("Add account")
        self.add_btn.setStyleSheet(s_plus_btn())
        self.add_btn.clicked.connect(self._on_add)
        hdr.addWidget(self.add_btn)
        v.addWidget(self.header)

        self.list_frame = QFrame()
        self.list_frame.setStyleSheet(
            f"QFrame{{background:{theme.BG2};border:none}}")
        lf = QVBoxLayout(self.list_frame)
        lf.setContentsMargins(10, 10, 10, 10); lf.setSpacing(0)

        self.list = QListWidget()
        self.list.setFont(QFont(theme.UI_FONT, LIST_FONT_SIZE))
        self.list.setWordWrap(False)
        self.list.setTextElideMode(Qt.ElideRight)
        self.list.setSelectionMode(QListWidget.SingleSelection)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_ctx)
        self.list.setItemDelegate(_AccountItemDelegate(self.list))
        self.list.setSpacing(0)
        self.list.setStyleSheet(
            f"QListWidget{{background:{theme.BG2};color:{theme.FG};"
            f"border:none;outline:none;padding:0}}"
            f"QListWidget::item{{padding:0;border:none}}")
        self.list.itemSelectionChanged.connect(self._on_select)
        lf.addWidget(self.list, 1)
        v.addWidget(self.list_frame, 1)

    # --------------------------------------------------------------
    def _active_index(self):
        try:
            return int(self.settings.get("active_account", 0))
        except (TypeError, ValueError):
            return 0

    # --------------------------------------------------------------
    def refresh(self):
        self.list.blockSignals(True)
        self.list.clear()
        accs = self.settings.get_accounts()
        active = self._active_index()
        for i, a in enumerate(accs):
            kind = "Online" if a.get("type") == "online" else "Offline"
            name = a.get("name") or "(unnamed)"
            is_active = (i == active)
            marker = "●" if is_active else "○"
            it = QListWidgetItem(f"{marker}  {name}  [{kind}]")
            self.list.addItem(it)
        self.list.blockSignals(False)
        if accs:
            row = active if 0 <= active < len(accs) else 0
            self.list.setCurrentRow(row)

    def _on_select(self):
        pass

    def _unstick(self):
        self.setFocus()
        self.activateWindow()
        QApplication.processEvents()

    def restyle(self):
        self.list.setStyleSheet(
            f"QListWidget{{background:{theme.BG2};color:{theme.FG};"
            f"border:none;outline:none;padding:0}}"
            f"QListWidget::item{{padding:0;border:none}}")
        self.add_btn.setStyleSheet(s_plus_btn())
        self.header.setStyleSheet(
            f"QFrame{{background:{theme.BG2};border:none}}")
        self.list_frame.setStyleSheet(
            f"QFrame{{background:{theme.BG2};border:none}}")
        self.title_lbl.setStyleSheet(
            f"background:transparent;color:{theme.FG};"
            f"font-size:14pt;font-weight:bold")
        self.title_spacer.setStyleSheet(
            f"background:transparent;color:{theme.GRAY};font-size:10pt")
        self.refresh()

    # --------------------------------------------------------------
    def _on_ctx(self, pos: QPoint):
        it = self.list.itemAt(pos)
        if it is None:
            return
        row = self.list.row(it)
        accs = self.settings.get_accounts()
        if not (0 <= row < len(accs)):
            return
        self.list.setCurrentRow(row)
        acc = accs[row]
        active = self._active_index()

        m = QMenu(self)
        m.setStyleSheet(
            f"QMenu{{background:{theme.BG2};color:{theme.FG};"
            f"border:none;padding:4px}}"
            f"QMenu::item{{padding:6px 20px 6px 12px}}"
            f"QMenu::item:selected{{background:{theme.BG3};color:{theme.FG}}}"
            f"QMenu::item:disabled{{color:{theme.GRAY}}}")

        if row == active:
            a = m.addAction("In use")
            a.setEnabled(False)
        else:
            m.addAction("Use this account", self._use_current)

        m.addSeparator()
        if acc.get("type") == "online":
            m.addAction("Sign out", self._sign_out_current)
        m.addAction("Rename", self._rename_current)
        m.addSeparator()
        m.addAction("Remove", self._remove_current)
        m.exec_(self.list.mapToGlobal(pos))

    def _use_current(self):
        row = self.list.currentRow()
        accs = self.settings.get_accounts()
        if not (0 <= row < len(accs)):
            return
        self.settings.set_active_account(row)
        self._log("ok", f"now using '{accs[row].get('name')}'")
        self.refresh()
        self._unstick()

    # --------------------------------------------------------------
    def _sign_out_current(self):
        row = self.list.currentRow()
        accs = self.settings.get_accounts()
        if not (0 <= row < len(accs)):
            return
        if accs[row].get("type") != "online":
            return
        accs[row]["data"] = {}
        self.settings.set_accounts(accs)
        self._log("info", f"signed out '{accs[row].get('name')}'")
        self.refresh()
        self._unstick()

    def _rename_current(self):
        row = self.list.currentRow()
        accs = self.settings.get_accounts()
        if not (0 <= row < len(accs)):
            return
        old = accs[row].get("name", "")
        name, ok = QInputDialog.getText(self, "Rename account",
                                        "Username:", text=old)
        if not ok or not name.strip():
            self._unstick()
            return
        accs[row]["name"] = name.strip()
        self.settings.set_accounts(accs)
        self.refresh()
        self._unstick()

    def _remove_current(self):
        row = self.list.currentRow()
        accs = self.settings.get_accounts()
        if not (0 <= row < len(accs)):
            return
        a = accs[row]
        if QMessageBox.question(self, "Remove",
            f"Remove account '{a.get('name')}'?") != QMessageBox.Yes:
            self._unstick()
            return
        del accs[row]
        self.settings.set_accounts(accs)
        active = self._active_index()
        if active >= len(accs):
            active = max(0, len(accs) - 1)
        self.settings.set_active_account(active)
        self._log("warn", f"removed account '{a.get('name')}'")
        self.refresh()
        self._unstick()

    # --------------------------------------------------------------
    def _on_add(self):
        choice, ok = QInputDialog.getItem(
            self, "Add account", "Account type:",
            ["Online (Microsoft)", "Offline"], 0, False)
        if not ok:
            self._unstick()
            return
        if choice.startswith("Offline"):
            self._add_offline()
        else:
            self._add_online()

    def _add_offline(self):
        name, ok = QInputDialog.getText(self, "Offline account", "Username:")
        if not ok or not name.strip():
            self._unstick()
            return
        name = name.strip()
        accs = self.settings.get_accounts()
        accs.append({"type": "offline", "name": name, "data": {}})
        self.settings.set_accounts(accs)
        self.settings.set_active_account(len(accs) - 1)
        self._log("ok", f"offline account '{name}' added")
        self.refresh()
        self._unstick()

    def _add_online(self):
        self._log("info", "starting Microsoft sign-in…")
        try:
            new = auth.sign_in_webview(parent=self, log=self._log)
        except Exception as e:
            self._log("error", f"sign-in failed: {e}")
            self._unstick()
            return
        if not new:
            self._log("warn", "sign-in cancelled")
            self._unstick()
            return
        accs = self.settings.get_accounts()
        accs.append({
            "type": "online",
            "name": new.name,
            "data": new.to_dict(),
        })
        self.settings.set_accounts(accs)
        self.settings.set_active_account(len(accs) - 1)
        self._log("ok", f"signed in as {new.name}")
        self.refresh()
        self._unstick()
