import threading
from PyQt5.QtCore import QThread, pyqtSignal

_shutdown = threading.Event()
_leaked_threads = []


class Worker(QThread):
    log = pyqtSignal(str, str)
    progress = pyqtSignal(str, int, int, str, str)
    progress_end = pyqtSignal()
    done = pyqtSignal(object)

    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args

    def run(self):
        try:
            if _shutdown.is_set():
                self.done.emit(None); return
            r = self.fn(*self.args, log=self.log.emit,
                        progress=self.progress.emit,
                        progress_end=self.progress_end.emit)
            self.done.emit(r)
        except Exception as e:
            import traceback; traceback.print_exc()
            try: self.log.emit("error", f"crashed: {e}")
            except Exception: pass
            self.done.emit(None)
