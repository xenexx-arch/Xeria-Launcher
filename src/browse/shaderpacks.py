import json

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTabWidget

from core import theme
from integration import modrinth
from browse.base import BrowseBase
from browse.control import ControlTab


class ShadersSearchTab(BrowseBase):
    KIND = "shader"
    TITLE = "Shaders"
    FOLDER = "shaderpacks"
    SEARCH_PH = "Search shaders..."
    HEADER_ICON = "video-display"
    VANILLA_WARN = None

    def _search_url(self, query):
        return ("https://api.modrinth.com/v2/search",
                {"query": query, "limit": 30,
                 "facets": json.dumps([["project_type:shader"]])})

    def pick_download(self, hit):
        return modrinth.pick_file(hit["id"], self.profile.version,
                                  "shader", None)


class ShadersDialog(QDialog):
    def __init__(self, parent, profile, log_fn):
        super().__init__(parent)
        self.profile = profile
        self.log_fn = log_fn
        self.setWindowTitle(f"Shaders — {profile.name}")
        self.resize(1080, 700)
        self.setMinimumSize(760, 500)
        self.setStyleSheet(f"QDialog{{background:{theme.BG};border:none}}")

        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(6)

        self.tabs = QTabWidget(self)
        self.tabs.setStyleSheet(
            f"QTabWidget::pane{{border:none;background:{theme.BG}}}"
            f"QTabBar::tab{{background:transparent;color:{theme.FG};"
            f"padding:8px 14px;border:none;"
            f"font-family:'{theme.UI_FONT}';font-size:10pt}}"
            f"QTabBar::tab:selected{{color:{theme.FG};"
            f"border-bottom:1px solid {theme.ACCENT}}}")
        v.addWidget(self.tabs, 1)

        self.search_tab = ShadersSearchTab(self, profile, log_fn)
        self.tabs.addTab(self.search_tab, "Search")

        self.control_tab = ControlTab(self, profile, log_fn, "shader")
        self.tabs.addTab(self.control_tab, "Control")

    def closeEvent(self, event):
        try:
            self.search_tab.closeEvent(event)
        except Exception:
            super().closeEvent(event)
