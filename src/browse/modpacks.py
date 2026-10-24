import json

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox

from core import theme
from integration import modrinth
from browse.base import BrowseBase


class ModpackSearchDialog(BrowseBase):
    """Modpack search — same layout as Mods / Resource Packs / Shaders
    because it *is* a BrowseBase instance. Install Selected returns the
    picked project via .result instead of downloading into a folder."""

    KIND = "modpack"
    TITLE = "Modpacks"
    FOLDER = "modpacks"
    SEARCH_PH = "Search modpacks..."
    HEADER_ICON = "package-x-generic"
    VANILLA_WARN = None

    DEFAULT_QUERY = "fabulously optimized"

    def __init__(self, parent, log_fn=None):
        self.result = None
        # BrowseBase expects (parent, profile, log_fn) and uses
        # `profile.name`, `profile.loader`, `profile.version`, and
        # `profile.dir / FOLDER`. For modpacks none of those are used
        # for actual file operations, so a dummy profile is fine.
        super().__init__(parent, _DummyProfile(), log_fn or (lambda t, m: None))
        self.setWindowTitle("Modpacks")
        # Seed the search field so the tab is populated on open.
        if not self.search.text():
            self.search.setText(self.DEFAULT_QUERY)

    def _search_url(self, query):
        return ("https://api.modrinth.com/v2/search",
                {"query": query, "limit": 30,
                 "facets": json.dumps([["project_type:modpack"]])})

    def pick_download(self, hit):
        picked = modrinth.pick_modpack_file(hit["id"])
        if not picked:
            return None
        url, filename, _ver = picked
        return url, filename

    def row_subtitle(self, hit):
        cats = hit.get("categories", [])
        mc = ""
        for c in cats:
            if c.startswith("1."):
                mc = f"  ·  MC {c}"
                break
        return f"by {hit['author']}{mc}  ·  {hit['dl']:,} dl"

    def install_selected(self):
        """Instead of downloading, pick the hit and close."""
        hit = self._selected_hit()
        if hit is None:
            QMessageBox.information(self, "Select", "Click a row first.")
            return
        self.result = hit
        self.accept()


class _DummyProfile:
    """Minimal Profile stand-in. Modpack search never touches the
    filesystem; BrowseBase only calls profile.dir / FOLDER and checks
    .exists() to decide the 'Installed' badge, which we want always
    False."""
    name = "(modpacks)"
    loader = "vanilla"
    version = ""

    class _D:
        def __truediv__(self, other):
            return self

        def exists(self):
            return False

        def iterdir(self):
            return iter(())

    dir = _D()
