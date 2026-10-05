import json
from integration import modrinth
from browse.base import BrowseBase


class ResourcePacksDialog(BrowseBase):
    KIND = "resourcepack"
    TITLE = "Resource Packs"
    FOLDER = "resourcepacks"
    SEARCH_PH = "Search resource packs..."
    HEADER_ICON = "preferences-desktop-theme"
    VANILLA_WARN = None

    def _search_url(self, query):
        return ("https://api.modrinth.com/v2/search",
                {"query": query, "limit": 30,
                 "facets": json.dumps([["project_type:resourcepack"]])})

    def pick_download(self, hit):
        return modrinth.pick_file(hit["id"], self.profile.version,
                                  "resourcepack", None)
