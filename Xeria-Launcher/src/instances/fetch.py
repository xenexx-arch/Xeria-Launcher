import time
from PyQt6.QtCore import Qt

from core.paths import MANIFEST_URL
from core.worker import Worker
from integration import http


class FetchMixin:
    def fetch_manifest(self):
        def task(log, progress, progress_end):
            log("net", f"GET {MANIFEST_URL}")
            t0 = time.time()
            r = http.get(MANIFEST_URL)
            r.raise_for_status()
            d = r.json()
            rel = [v for v in d["versions"] if v["type"] == "release"]
            log("ok", f"manifest loaded ({len(rel)} releases, "
                      f"{time.time()-t0:.2f}s)")
            return d, rel

        w = Worker(task)
        w.log.connect(self.console.log, Qt.ConnectionType.QueuedConnection)
        w.done.connect(self._manifest_done,
                       Qt.ConnectionType.QueuedConnection)
        self._track(w)
        w.start()

    def _manifest_done(self, r):
        if not r:
            return
        self.manifest, self.releases = r

    def _apply_mc_icon(self, ic):
        for i in range(self.plist.count()):
            self.plist.item(i).setIcon(ic)
