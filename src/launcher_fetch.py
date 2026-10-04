import time
from PyQt5.QtCore import Qt
import requests

from paths import MANIFEST_URL
from worker import Worker
from settings import detect_gpu
from ui_helpers import mc_icon_sync


class FetchMixin:
    """Manifest fetch and MC icon apply. Assumes self is a MainWindow."""

    def fetch_manifest(self):
        def task(log, progress, progress_end):
            log("net", f"GET {MANIFEST_URL}")
            t0 = time.time()
            r = requests.get(MANIFEST_URL, timeout=8)
            r.raise_for_status()
            d = r.json()
            rel = [v for v in d["versions"] if v["type"] == "release"]
            log("ok", f"manifest loaded ({len(rel)} releases, "
                      f"{time.time()-t0:.2f}s)")
            return d, rel
        w = Worker(task)
        w.log.connect(self.console.log, Qt.QueuedConnection)
        w.done.connect(self._manifest_done, Qt.QueuedConnection)
        self._track(w)
        w.start()

    def _manifest_done(self, r):
        if not r:
            return
        self.manifest, self.releases = r

    def _apply_mc_icon(self, ic):
        for i in range(self.plist.count()):
            self.plist.item(i).setIcon(ic)
