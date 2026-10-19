import json
from integration import modrinth
from browse.base import BrowseBase


class ShadersDialog(BrowseBase):
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
