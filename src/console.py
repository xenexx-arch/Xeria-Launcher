import time
from datetime import datetime
from PyQt5.QtGui import QFont, QTextCursor
from PyQt5.QtWidgets import QPlainTextEdit
import theme


class Console(QPlainTextEdit):
    TAGS = {"info": ("  >>", None), "ok": ("  OK", None),
            "warn": ("  !!", None), "error": ("  XX", None),
            "java": ("  JV", None), "net": ("  NW", None),
            "sys": ("  SY", None), "mc": ("  MC", None)}

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setFont(QFont(theme.MONO_FONT, 9))
        self.restyle()
        self.setMaximumBlockCount(4000)
        self._last_progress = False
        self._t0 = time.time()

    def restyle(self):
        self.setStyleSheet(
            f"QPlainTextEdit{{background:{theme.BG2};color:{theme.GREEN};"
            f"border:none;border-radius:0;padding:6px}}")

    def _esc(self, s):
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _write(self, html):
        self.appendHtml(html)
        sb = self.verticalScrollBar(); sb.setValue(sb.maximum())

    def log(self, tag, msg):
        if tag == "progress":
            label, cur, total, extra, speed = msg
            self._progress(label, cur, total, extra, speed); return
        if tag == "progress_end":
            self._last_progress = False; return
        t, _ = self.TAGS.get(tag, self.TAGS["info"])
        ts = datetime.now().strftime("%H:%M:%S")
        rel = f"{time.time()-self._t0:.2f}s"
        color = {"ok": theme.GREEN, "warn": theme.YELLOW,
                 "error": theme.RED, "java": theme.CYAN,
                 "net": theme.BLUE, "sys": theme.PURPLE,
                 "mc": theme.FG}.get(tag, theme.CYAN)
        self._write(f'<span style="color:{theme.GRAY}">[{ts} {rel:>7}]</span> '
                    f'<span style="color:{color};font-weight:bold">{t}</span> '
                    f'<span style="color:{theme.FG}">{self._esc(msg)}</span>')
        self._last_progress = False

    def _progress(self, label, cur, total, extra, speed):
        total = max(total, 1)
        pct = cur * 100 / total
        w = 30
        fill = int(w * cur / total)
        bar = "=" * fill + (">" if fill < w else "") + " " * (w - fill - (0 if fill >= w else 1))
        bar = bar[:w]
        color = theme.GREEN if pct >= 99 else (theme.YELLOW if pct >= 50 else theme.CYAN)
        ts = datetime.now().strftime("%H:%M:%S")
        html = (f'<span style="color:{theme.GRAY}">[{ts}]</span> '
                f'<span style="color:{theme.GREEN};font-weight:bold">  DL</span> '
                f'<span style="color:{theme.FG}">{self._esc(label)[:22]:<22}</span>'
                f'<span style="color:{color}">[{bar}]</span> '
                f'<span style="color:{color};font-weight:bold">{pct:5.1f}%</span> '
                f'<span style="color:{theme.GRAY}">{self._esc(speed):>10}</span>')
        if self._last_progress:
            c = self.textCursor()
            c.movePosition(QTextCursor.End)
            c.select(QTextCursor.BlockUnderCursor)
            c.removeSelectedText()
            c.deletePreviousChar()
        self._write(html)
        self._last_progress = True


class MiniConsole(QPlainTextEdit):
    TAGS = Console.TAGS
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont(theme.MONO_FONT, 8))
        self.restyle()
        self.setMaximumBlockCount(500)

    def restyle(self):
        self.setStyleSheet(
            f"QPlainTextEdit{{background:{theme.BG2};color:{theme.GREEN};"
            f"border:none;border-radius:0;padding:4px}}")

    def log(self, tag, msg):
        if tag == "progress":
            label, cur, total, extra, speed = msg
            ts = datetime.now().strftime("%H:%M:%S")
            pct = int(cur * 100 / max(total, 1))
            self.appendPlainText(f"[{ts}] DL {label[:22]:<22} {pct:3d}% {speed}")
        elif tag == "progress_end":
            return
        else:
            t, _ = self.TAGS.get(tag, self.TAGS["info"])
            ts = datetime.now().strftime("%H:%M:%S")
            self.appendPlainText(f"[{ts}] {t} {msg}")
        sb = self.verticalScrollBar(); sb.setValue(sb.maximum())
