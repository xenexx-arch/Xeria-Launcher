import json
import modrinth
from browse_base import BrowseBase


class ModsDialog(BrowseBase):
    KIND = "mod"
    TITLE = "Mods"
    FOLDER = "mods"
    SEARCH_PH = "Search mods..."
    HEADER_ICON = "system-software-install"
    VANILLA_WARN = "⚠  This profile is vanilla — mods won't load."

    def _search_url(self, query):
        facets = [["project_type:mod"]]
        loader = (self.profile.loader or "vanilla").lower()
        if loader and loader != "vanilla":
            facets.append([f"categories:{loader}"])
        return ("https://api.modrinth.com/v2/search",
                {"query": query, "limit": 30,
                 "facets": json.dumps(facets)})

    def pick_download(self, hit):
        loader = (self.profile.loader or "vanilla").lower()
        return modrinth.pick_file(hit["id"], self.profile.version,
                                  "mod", loader)
