#!/usr/bin/env python3
import os
import re
import sys
import ssl
import shutil
import zipfile
import subprocess
import platform
import venv
import webbrowser
import urllib.request
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QProgressBar, QMessageBox, QDialog, QLineEdit,
)

_SSL_CONTEXT = None
_SSL_MODE = "default"


def _bootstrap_ssl():
    global _SSL_CONTEXT, _SSL_MODE
    try:
        import truststore
        truststore.inject_into_ssl()
        _SSL_CONTEXT = ssl.create_default_context()
        _SSL_MODE = "truststore"
        return
    except Exception:
        pass
    try:
        import certifi
        _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
        _SSL_MODE = "certifi"
        return
    except Exception:
        pass
    try:
        _SSL_CONTEXT = ssl._create_unverified_context()
        _SSL_MODE = "unverified"
    except Exception:
        _SSL_CONTEXT = None
        _SSL_MODE = "none"


_bootstrap_ssl()

REPO_ZIP = "https://github.com/xenexx-arch/Xeria-Launcher/archive/refs/heads/main.zip"
REPO_ZIP_ALT = "https://github.com/xenexx-arch/Xeria-Launcher/archive/refs/heads/master.zip"
APP_NAME = "Xeria Launcher"
APP_EXEC = "xeria.pyw"

IS_WIN = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"

HOME = Path.home()

if IS_WIN:
    INSTALL_DIR = Path(os.getenv("LOCALAPPDATA", HOME)) / "Xeria Launcher"
    VENV_DIR = INSTALL_DIR / ".venv"
    APPS_DIR = Path(os.getenv("APPDATA", HOME)) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    DESKTOP_DIR = HOME / "Desktop"
elif IS_MAC:
    INSTALL_DIR = HOME / "Applications" / "Xeria Launcher"
    VENV_DIR = INSTALL_DIR / ".venv"
    APPS_DIR = HOME / "Applications"
    DESKTOP_DIR = HOME / "Desktop"
else:
    INSTALL_DIR = HOME / ".local" / "share" / "xeria-launcher"
    VENV_DIR = INSTALL_DIR / ".venv"
    APPS_DIR = HOME / ".local" / "share" / "applications"
    DESKTOP_DIR = HOME / ".local" / "share" / "applications"

PIP_REQUIREMENTS = [
    "PyQt5",
    "PyQtWebEngine",
    "PyQt5-sip",
    "PyOpenGL",
    "requests",
    "Pillow",
    "truststore",
]

LINUX_SYS_PACKAGES = {
    "apt": ["python3-pyqt5.qtwebengine", "python3-pyqt5.qtsvg",
            "python3-pyqt5.qtwayland", "libgl1-mesa-dri",
            "mesa-vulkan-drivers", "mesa-opencl-icd",
            "libglx-mesa0", "libopencl1"],
    "dnf": ["python3-qt5-webengine", "python3-qt5-svg", "qt5-qtwayland",
            "mesa-dri-drivers", "mesa-vulkan-drivers",
            "mesa-libOpenCL", "ocl-icd"],
    "pacman": ["python-pyqt5-webengine", "python-pyqt5-svg",
               "qt5-wayland", "mesa", "vulkan-icd-loader",
               "ocl-icd"],
    "zypper": ["python3-qt5-webengine", "libqt5-qtsvg",
               "libqt5-qtwayland", "Mesa", "Mesa-libGL1",
               "libvulkan1", "libOpenCL1", "ocl-icd"],
    "apk": ["py3-pyqt5-webengine", "py3-pyqt5-svg", "qt5-qtwayland",
            "mesa-dri-gallium", "vulkan-loader", "opencl-icd-loader"],
}

MIN_PYTHON = (3, 9)
RECOMMENDED_PYTHON = (3, 12)

PYTHON_DOWNLOAD_URLS = {
    "Windows": {
        "3.12": "https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe",
        "3.13": "https://www.python.org/ftp/python/3.13.0/python-3.13.0-amd64.exe",
    },
    "Darwin": {
        "3.12": "https://www.python.org/ftp/python/3.12.7/python-3.12.7-macos11.pkg",
        "3.13": "https://www.python.org/ftp/python/3.13.0/python-3.13.0-macos11.pkg",
    },
}

MIN_GL = (3, 3)

BG      = "#1a1a1a"
BG2     = "#232323"
BG3     = "#2e2e2e"
BORDER  = "#3d3d3d"
FG      = "#e6e6e6"
GRAY    = "#8a8a8a"
ACCENT  = "#ffffff"
ACCENT2 = "#d0d0d0"
GREEN   = "#5eb87d"
RED     = "#e05c5c"
YELLOW  = "#e0b85c"
CYAN    = "#5cb8d8"

UI_FONT   = "Segoe UI" if IS_WIN else "DejaVu Sans"
MONO_FONT = "Consolas" if IS_WIN else "DejaVu Sans Mono"

CREATE_NO_WINDOW = 0x08000000 if IS_WIN else 0


def _detect_opengl():
    """Return (vendor, renderer, version_str, (major, minor)) or (None,)*4
    on failure. Creates a hidden QOpenGLWidget to obtain a real GL context."""
    try:
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtGui import QOpenGLContext, QOffscreenSurface, QSurfaceFormat
    except Exception as e:
        return None, None, f"PyQt GL imports failed: {e}", None

    try:
        ctx = QOpenGLContext()
        # Request any version; the driver will give us what it has
        fmt = QSurfaceFormat()
        fmt.setRenderableType(QSurfaceFormat.OpenGL)
        ctx.setFormat(fmt)
        if not ctx.create():
            return None, None, "failed to create GL context", None

        surface = QOffscreenSurface()
        surface.setFormat(ctx.format())
        surface.create()
        if not surface.isValid():
            return None, None, "offscreen surface invalid", None

        if not ctx.makeCurrent(surface):
            return None, None, "could not make context current", None

        try:
            from OpenGL import GL
        except Exception as e:
            ctx.doneCurrent()
            return None, None, f"PyOpenGL missing: {e}", None

        def _s(enum):
            v = GL.glGetString(enum)
            if v is None:
                return ""
            try:
                return v.decode("utf-8", "replace")
            except Exception:
                return str(v)

        vendor   = _s(GL.GL_VENDOR)
        renderer = _s(GL.GL_RENDERER)
        version  = _s(GL.GL_VERSION)

        ctx.doneCurrent()
        surface.destroy()

        m = re.match(r"(\d+)\.(\d+)", version or "")
        parsed = (int(m.group(1)), int(m.group(2))) if m else None
        return vendor, renderer, version, parsed
    except Exception as e:
        return None, None, f"GL probe failed: {e}", None


def _open_ms_store_home():
    if not IS_WIN:
        return False
    try:
        webbrowser.open("ms-windows-store://home")
        return True
    except Exception:
        return False


def _print_linux_hint(pm):
    """Return a short string telling the user which distro packages map to
    the vulkan/opencl/opengl stack."""
    if pm == "apt":
        return "sudo apt install libgl1-mesa-dri mesa-vulkan-drivers mesa-opencl-icd"
    if pm == "dnf":
        return "sudo dnf install mesa-dri-drivers mesa-vulkan-drivers mesa-libOpenCL"
    if pm == "pacman":
        return "sudo pacman -S mesa vulkan-icd-loader ocl-icd"
    if pm == "zypper":
        return "sudo zypper install Mesa Mesa-libGL1 libvulkan1 libOpenCL1"
    if pm == "apk":
        return "sudo apk add mesa-dri-gallium vulkan-loader opencl-icd-loader"
    return "install your distro's mesa/vulkan/opencl packages"


class PasswordDialog(QDialog):
    def __init__(self, parent=None, prompt="Administrator password required."):
        super().__init__(parent)
        self.setWindowTitle("Authentication required")
        self.setModal(True)
        self.setMinimumWidth(380)
        self.setStyleSheet(
            f"QDialog{{background:{BG};color:{FG}}}"
            f"QLabel{{background:transparent;color:{FG};"
            f"font-family:'{UI_FONT}';font-size:10pt}}"
            f"QLineEdit{{background:{BG3};color:{FG};border:none;"
            f"padding:8px;font-family:'{UI_FONT}';font-size:11pt}}"
            f"QPushButton{{background:{BG3};color:{FG};border:none;"
            f"padding:8px 18px;font-family:'{UI_FONT}'}}"
            f"QPushButton:hover{{background:{BORDER}}}"
        )
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 18, 18, 18)
        v.setSpacing(10)

        lbl = QLabel(prompt)
        lbl.setWordWrap(True)
        v.addWidget(lbl)

        self.field = QLineEdit()
        self.field.setEchoMode(QLineEdit.Password)
        self.field.setPlaceholderText("password")
        v.addWidget(self.field)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        ok = QPushButton("OK")
        ok.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:#000000;border:none;"
            f"padding:8px 20px;font-weight:bold;font-family:'{UI_FONT}'}}"
            f"QPushButton:hover{{background:{ACCENT2}}}")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        btns.addWidget(ok)
        v.addLayout(btns)
        self.field.setFocus()

    def value(self):
        return self.field.text()


class InstallWorker(QThread):
    log_line = pyqtSignal(str, str)
    progress = pyqtSignal(int)
    finished_ok = pyqtSignal(bool, str)
    request_password = pyqtSignal(str)

    def __init__(self, log_fn):
        super().__init__()
        self._log = log_fn
        self._cancelled = False
        self._password = None

    def _L(self, tag, msg):
        self._log(tag, msg)
        self.log_line.emit(tag, msg)

    def cancel(self):
        self._cancelled = True

    def supply_password(self, password):
        self._password = password

    def run(self):
        try:
            ok, msg = self._run_install()
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._L("err", f"fatal: {e}")
            ok, msg = False, str(e)
        self.finished_ok.emit(ok, msg)

    def _run_install(self):
        self._L("sys", f"platform {platform.system()} {platform.release()}")
        self._L("sys", f"python {platform.python_version()} (running this installer)")
        self._L("sys", f"ssl backend {_SSL_MODE}")
        self._L("sys", f"install dir {INSTALL_DIR}")

        if _SSL_MODE == "unverified":
            self._L("warn", "using unverified SSL context for bootstrap")
            self._L("warn", "install 'truststore' or 'certifi' to fix this")

        self.progress.emit(5)
        py = self._find_python()
        if py is None:
            self._L("py", f"no Python >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]} found")
            py = self._prompt_install_python()
            if py is None:
                return False, "Python still not available"

        if self._cancelled:
            return False, "cancelled"

        self.progress.emit(15)
        if IS_LINUX:
            self._install_system_packages()

        if self._cancelled:
            return False, "cancelled"

        self.progress.emit(30)
        self._download_repo()

        if self._cancelled:
            return False, "cancelled"

        self.progress.emit(45)
        self._L("sys", f"base interpreter {py}")
        self._create_venv(py)

        if self._cancelled:
            return False, "cancelled"

        self.progress.emit(60)
        self._install_pip_packages()

        if self._cancelled:
            return False, "cancelled"

        self.progress.emit(95)
        if IS_WIN:
            self._make_windows_shortcut()
        elif IS_LINUX or IS_MAC:
            self._make_linux_desktop()
        else:
            self._L("warn", "unsupported platform, no shortcut created")

        self.progress.emit(100)
        return True, "Installation complete."

    def _which(self, program):
        return shutil.which(program)

    def _needs_sudo(self):
        if IS_WIN:
            return False
        try:
            return os.geteuid() != 0
        except AttributeError:
            return True

    def _ensure_password(self):
        if self._password is not None:
            return True
        self.request_password.emit(
            "Administrator privileges are needed to install system packages.\n"
            "Enter your password to continue:")
        return False

    def _run(self, cmd, cwd=None, check=True, use_sudo=False):
        self._L("run", " ".join(str(c) for c in cmd))
        if use_sudo and self._needs_sudo():
            if self._password is None:
                self._ensure_password()
                for _ in range(600):
                    if self._password is not None or self._cancelled:
                        break
                    QThread.msleep(100)
                if self._cancelled:
                    raise RuntimeError("cancelled")
                if self._password is None:
                    raise RuntimeError("no password supplied")
            full = ["sudo", "-S", "-p", ""] + [str(c) for c in cmd]
            proc = subprocess.Popen(
                full,
                cwd=str(cwd) if cwd else None,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            out, _ = proc.communicate(self._password + "\n")
            for line in (out or "").splitlines():
                if line.strip():
                    self._L("sys", line)
            if check and proc.returncode != 0:
                raise subprocess.CalledProcessError(proc.returncode, full)
            return proc.returncode
        return subprocess.run([str(c) for c in cmd],
                              cwd=str(cwd) if cwd else None,
                              check=check,
                              creationflags=CREATE_NO_WINDOW).returncode

    def _download(self, url, dest):
        self._L("net", f"GET {url}  (ssl: {_SSL_MODE})")
        req = urllib.request.Request(
            url, headers={"User-Agent": "Xeria Launcher/1.0"})
        if _SSL_CONTEXT is not None:
            r = urllib.request.urlopen(req, context=_SSL_CONTEXT, timeout=120)
        else:
            r = urllib.request.urlopen(req, timeout=120)
        with r:
            total = int(r.headers.get("Content-Length", 0))
            got = 0
            with open(dest, "wb") as f:
                while True:
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    if total:
                        pct = got * 100 // total
                        self.progress.emit(30 + pct * 15 // 100)
        self._L("net", f"download done, saved {dest}")

    def _python_version_of(self, exe):
        try:
            out = subprocess.run(
                [exe, "-c",
                 "import sys;print('%d.%d' % sys.version_info[:2])"],
                capture_output=True, text=True, timeout=10,
                creationflags=CREATE_NO_WINDOW)
            if out.returncode != 0:
                return None
            return tuple(int(x) for x in out.stdout.strip().split("."))
        except Exception:
            return None

    def _find_python(self):
        seen = set()
        candidates = []
        for name in ("python3.13", "python3.12", "python3.11", "python3.10",
                     "python3.9", "python3", "python"):
            p = self._which(name)
            if p and p not in seen:
                seen.add(p)
                candidates.append(p)

        best, best_ver = None, None
        for c in candidates:
            v = self._python_version_of(c)
            if not v:
                continue
            if v < MIN_PYTHON:
                self._L("py", f"{c} -> {v[0]}.{v[1]} (too old)")
                continue
            self._L("py", f"{c} -> {v[0]}.{v[1]}")
            if best_ver is None or v > best_ver:
                best, best_ver = c, v

        if best is None:
            return None
        self._L("ok", f"selected {best} ({best_ver[0]}.{best_ver[1]})")
        return best

    def _prompt_install_python(self):
        system = platform.system()
        if system == "Linux":
            return self._install_python_linux()
        if system == "Windows":
            return self._install_python_windows()
        if system == "Darwin":
            return self._install_python_mac()
        self._L("err", f"no auto-install path for {system}")
        return None

    def _install_python_linux(self):
        pm = None
        for name in ("apt", "dnf", "pacman", "zypper", "apk"):
            if self._which(name):
                pm = name
                break
        if not pm:
            self._L("err", "no supported package manager for Python install")
            return None
        pkg_map = {
            "apt": ["python3", "python3-venv", "python3-pip"],
            "dnf": ["python3", "python3-pip"],
            "pacman": ["python", "python-pip"],
            "zypper": ["python3", "python3-pip"],
            "apk": ["python3", "py3-pip"],
        }
        pkgs = pkg_map[pm]
        try:
            if pm == "apt":
                self._run(["apt-get", "update"], check=False, use_sudo=True)
                self._run(["apt-get", "install", "-y"] + pkgs, use_sudo=True)
            elif pm == "dnf":
                self._run(["dnf", "install", "-y"] + pkgs, use_sudo=True)
            elif pm == "pacman":
                self._run(["pacman", "-S", "--needed", "--noconfirm"] + pkgs,
                          use_sudo=True)
            elif pm == "zypper":
                self._run(["zypper", "--non-interactive", "install"] + pkgs,
                          use_sudo=True)
            elif pm == "apk":
                self._run(["apk", "add"] + pkgs, use_sudo=True)
            self._L("ok", "python installed")
        except subprocess.CalledProcessError as e:
            self._L("err", f"python install failed: {e}")
            return None
        return self._find_python()

    def _install_python_windows(self):
        url = PYTHON_DOWNLOAD_URLS["Windows"].get("3.12")
        if not url:
            return None
        tmp = Path(os.getenv("TEMP", ".")) / "python-installer.exe"
        self._download(url, tmp)
        try:
            subprocess.run([str(tmp), "/quiet",
                            "InstallAllUsers=0",
                            "PrependPath=1",
                            "Include_test=0",
                            "Include_launcher=1"],
                           check=True, creationflags=CREATE_NO_WINDOW)
        except subprocess.CalledProcessError as e:
            self._L("err", f"python installer failed: {e}")
            return None
        finally:
            try: tmp.unlink()
            except Exception: pass
        candidates = [
            HOME / "AppData" / "Local" / "Programs" / "Python"
            / "Python312" / "python.exe",
            Path(os.getenv("LOCALAPPDATA", "")) / "Programs" / "Python"
            / "Python312" / "python.exe",
            Path(r"C:\Python312\python.exe"),
        ]
        for c in candidates:
            if c.exists():
                self._L("ok", f"python installed at {c}")
                return str(c)
        py = self._which("python")
        if py:
            return py
        self._L("err", "python installed but not on PATH, restart shell")
        return None

    def _install_python_mac(self):
        url = PYTHON_DOWNLOAD_URLS["Darwin"].get("3.12")
        if not url:
            return None
        tmp = Path("/tmp") / "python-installer.pkg"
        self._download(url, tmp)
        try:
            self._run(["installer", "-pkg", str(tmp), "-target", "/"],
                      use_sudo=True)
        except subprocess.CalledProcessError as e:
            self._L("err", f"pkg install failed: {e}")
            return None
        finally:
            try: tmp.unlink()
            except Exception: pass
        return self._find_python()

    def _download_repo(self):
        INSTALL_DIR.parent.mkdir(parents=True, exist_ok=True)
        if INSTALL_DIR.exists():
            self._L("fs", f"removing {INSTALL_DIR}")
            shutil.rmtree(INSTALL_DIR, ignore_errors=True)

        tmp_zip = INSTALL_DIR.parent / "xeria-main.zip"
        last_err = None
        for url in (REPO_ZIP, REPO_ZIP_ALT):
            try:
                self._download(url, tmp_zip)
                last_err = None
                break
            except Exception as e:
                self._L("err", f"download failed: {e}")
                last_err = e
        if last_err:
            raise RuntimeError("could not fetch repository archive")

        self._L("fs", f"extracting {tmp_zip}")
        extract_root = INSTALL_DIR.parent / "_xeria_extract"
        if extract_root.exists():
            shutil.rmtree(extract_root, ignore_errors=True)
        with zipfile.ZipFile(tmp_zip) as z:
            z.extractall(extract_root)
        try: tmp_zip.unlink()
        except Exception: pass

        entries = [p for p in extract_root.iterdir() if p.is_dir()]
        if not entries:
            raise RuntimeError("archive contained no directories")
        src = entries[0]
        self._L("fs", f"moving {src} -> {INSTALL_DIR}")
        src.rename(INSTALL_DIR)
        try: extract_root.rmdir()
        except Exception: pass
        self._L("ok", f"repository ready at {INSTALL_DIR}")

    def _create_venv(self, py):
        if VENV_DIR.exists():
            self._L("venv", f"already present at {VENV_DIR}")
            return
        self._L("venv", f"creating at {VENV_DIR}")
        venv.create(str(VENV_DIR), with_pip=True, clear=False)
        self._L("ok", "virtualenv created")

    def _venv_python(self):
        if IS_WIN:
            return VENV_DIR / "Scripts" / "python.exe"
        return VENV_DIR / "bin" / "python"

    def _install_pip_packages(self):
        py = self._venv_python()
        if not py.exists():
            raise RuntimeError(f"venv python missing: {py}")
        self._L("pip", "upgrading pip / setuptools / wheel")
        try:
            self._run([py, "-m", "pip", "install", "--upgrade",
                       "pip", "setuptools", "wheel"])
        except subprocess.CalledProcessError as e:
            self._L("warn", f"pip bootstrap failed: {e}")
        for i, pkg in enumerate(PIP_REQUIREMENTS, 1):
            self._L("pip", f"install {pkg}")
            try:
                self._run([py, "-m", "pip", "install", "--upgrade", pkg])
                self._L("ok", f"{pkg} installed")
            except subprocess.CalledProcessError as e:
                self._L("warn", f"pip install failed for {pkg}: {e}")
            self.progress.emit(60 + i * 30 // len(PIP_REQUIREMENTS))
        self._L("ok", "python dependencies installed")

    def _install_system_packages(self):
        if not IS_LINUX:
            return
        pm = None
        for name in ("apt", "dnf", "pacman", "zypper", "apk"):
            if self._which(name):
                pm = name
                break
        if not pm:
            self._L("warn", "no supported package manager found")
            return
        pkgs = LINUX_SYS_PACKAGES.get(pm, [])
        if not pkgs:
            return
        try:
            if pm == "apt":
                self._run(["apt-get", "update"], check=False, use_sudo=True)
                self._run(["apt-get", "install", "-y"] + pkgs, use_sudo=True)
            elif pm == "dnf":
                self._run(["dnf", "install", "-y"] + pkgs, use_sudo=True)
            elif pm == "pacman":
                self._run(["pacman", "-S", "--needed", "--noconfirm"] + pkgs,
                          use_sudo=True)
            elif pm == "zypper":
                self._run(["zypper", "--non-interactive", "install"] + pkgs,
                          use_sudo=True)
            elif pm == "apk":
                self._run(["apk", "add"] + pkgs, use_sudo=True)
            self._L("ok", "system packages installed")
        except subprocess.CalledProcessError as e:
            self._L("warn", f"system package install failed: {e}")

    def _check_gpu_stack(self):
        """Probe OpenGL version and warn / open the Microsoft Store or
        print the distro install command if the version is too old."""
        self._L("sys", "probing OpenGL…")
        try:
            vendor, renderer, version, parsed = _detect_opengl()
        except Exception as e:
            self._L("warn", f"GL probe crashed: {e}")
            return
        if version is None:
            self._L("warn", "could not query OpenGL version")
            return
        self._L("sys", f"GL vendor:   {vendor or '(unknown)'}")
        self._L("sys", f"GL renderer: {renderer or '(unknown)'}")
        self._L("sys", f"GL version:  {version}")
        if parsed is None:
            self._L("warn", "could not parse OpenGL version")
            return
        if parsed < MIN_GL:
            self._L("warn",
                    f"OpenGL {parsed[0]}.{parsed[1]} is below the minimum "
                    f"{MIN_GL[0]}.{MIN_GL[1]}")
            if IS_WIN:
                self._L("hint",
                        "Opening Microsoft Store — install your GPU vendor's "
                        "companion app (NVIDIA Control Panel, Intel Graphics "
                        "Command Center, AMD Software) and let it update the "
                        "driver, or run Windows Update.")
                try:
                    _open_ms_store_home()
                except Exception as e:
                    self._L("warn", f"could not open store: {e}")
            elif IS_LINUX:
                pm = None
                for name in ("apt", "dnf", "pacman", "zypper", "apk"):
                    if self._which(name):
                        pm = name
                        break
                hint = _print_linux_hint(pm) if pm else \
                       "install your distro's mesa/vulkan/opencl packages"
                self._L("hint", hint)
            else:
                self._L("hint",
                        "update your GPU driver from your system settings")
        else:
            self._L("ok",
                    f"OpenGL {parsed[0]}.{parsed[1]} meets minimum "
                    f"{MIN_GL[0]}.{MIN_GL[1]}")

    def _make_icon(self):
        for candidate in (
            INSTALL_DIR / "icon.png",
            INSTALL_DIR / "assets" / "icon.png",
            INSTALL_DIR / "src" / "icon.png",
        ):
            if candidate.exists():
                return candidate
        return None

    def _make_linux_desktop(self):
        APPS_DIR.mkdir(parents=True, exist_ok=True)
        desktop_path = APPS_DIR / "xeria-launcher.desktop"
        icon = self._make_icon()
        icon_line = f"Icon={icon}" if icon else "Icon=applications-games"
        py = self._venv_python()
        exec_cmd = f'"{py}" "{INSTALL_DIR / APP_EXEC}"'
        content = f"""[Desktop Entry]
Type=Application
Name=Xeria Launcher
Comment=Lightweight Minecraft launcher
Exec={exec_cmd}
Path={INSTALL_DIR}
{icon_line}
Terminal=false
Categories=Game;
StartupNotify=true
StartupWMClass=Xeria
"""
        desktop_path.write_text(content)
        desktop_path.chmod(0o755)
        self._L("ok", f"desktop entry -> {desktop_path}")

        if DESKTOP_DIR.exists() and DESKTOP_DIR != APPS_DIR:
            try:
                desk_copy = DESKTOP_DIR / "xeria-launcher.desktop"
                desk_copy.write_text(content)
                desk_copy.chmod(0o755)
                if self._which("gio"):
                    subprocess.run(["gio", "set", str(desk_copy),
                                    "metadata::trusted", "true"], check=False)
                self._L("ok", f"desktop shortcut -> {desk_copy}")
            except Exception as e:
                self._L("warn", f"desktop shortcut failed: {e}")

        if self._which("update-desktop-database"):
            subprocess.run(["update-desktop-database", str(APPS_DIR)],
                           check=False)

    def _make_windows_shortcut(self):
        APPS_DIR.mkdir(parents=True, exist_ok=True)
        py = self._venv_python()
        target = INSTALL_DIR / APP_EXEC
        icon = self._make_icon()
        icon_line = f"$s.IconLocation = '{icon}'; " if icon else ""

        def _ps(link_path):
            ps = (
                "$ws = New-Object -ComObject WScript.Shell; "
                f"$s = $ws.CreateShortcut('{link_path}'); "
                f"$s.TargetPath = '{py}'; "
                f"$s.Arguments = '\"{target}\"'; "
                f"$s.WorkingDirectory = '{INSTALL_DIR}'; "
                "$s.WindowStyle = 1; "
                "$s.Description = 'Xeria Launcher'; "
                f"{icon_line}"
                "$s.Save();"
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           check=True, creationflags=CREATE_NO_WINDOW)

        start_link = APPS_DIR / "Xeria Launcher.lnk"
        _ps(start_link)
        self._L("ok", f"start menu shortcut -> {start_link}")

        if DESKTOP_DIR.exists():
            try:
                desk_link = DESKTOP_DIR / "Xeria Launcher.lnk"
                _ps(desk_link)
                self._L("ok", f"desktop shortcut -> {desk_link}")
            except Exception as e:
                self._L("warn", f"desktop shortcut failed: {e}")


class InstallerWindow(QWidget):
    def __init__(self):
        super().__init__()
        self._worker = None
        self._done = False
        self._pending_logs = []
        self.setWindowTitle("Xeria Launcher Installer")
        self.resize(720, 520)
        self.setMinimumSize(560, 380)
        self.setStyleSheet(f"QWidget{{background:{BG};color:{FG}}}")

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(10)

        head = QLabel("Xeria Launcher")
        head.setStyleSheet(
            f"background:transparent;color:{ACCENT};"
            f"font-size:18pt;font-weight:bold;font-family:'{UI_FONT}'")
        v.addWidget(head)
        sub = QLabel("Installation wizard")
        sub.setStyleSheet(
            f"background:transparent;color:{GRAY};"
            f"font-size:10pt;font-family:'{UI_FONT}'")
        v.addWidget(sub)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont(MONO_FONT, 9))
        self.log.setStyleSheet(
            f"QPlainTextEdit{{background:{BG2};color:{FG};border:none;"
            f"padding:8px}}")
        v.addWidget(self.log, 1)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.bar.setStyleSheet(
            f"QProgressBar{{background:{BG3};border:none}}"
            f"QProgressBar::chunk{{background:{ACCENT}}}")
        v.addWidget(self.bar)

        btns = QHBoxLayout()
        btns.addStretch()
        self.install_btn = QPushButton("Install")
        self.install_btn.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:#000000;border:none;"
            f"padding:10px 24px;font-weight:bold;"
            f"font-family:'{UI_FONT}';font-size:11pt}}"
            f"QPushButton:hover{{background:{ACCENT2}}}"
            f"QPushButton:disabled{{background:{BG3};color:{GRAY}}}")
        self.install_btn.clicked.connect(self.start_install)
        btns.addWidget(self.install_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.setStyleSheet(
            f"QPushButton{{background:{BG3};color:{FG};border:none;"
            f"padding:10px 20px;font-family:'{UI_FONT}'}}"
            f"QPushButton:hover{{background:{BORDER}}}")
        self.close_btn.clicked.connect(self.close)
        btns.addWidget(self.close_btn)
        v.addLayout(btns)

        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(50)
        self._flush_timer.timeout.connect(self._flush_logs)
        self._flush_timer.start()

        self._log("sys", f"platform {platform.system()} {platform.release()}")
        self._log("sys", f"python {platform.python_version()}")
        self._log("sys", f"ssl backend {_SSL_MODE}")
        self._log("sys", f"install dir {INSTALL_DIR}")
        self._log("info", "click Install to begin")

    def _log(self, tag, msg):
        self._pending_logs.append((tag, msg))

    def _flush_logs(self):
        if not self._pending_logs:
            return
        batch, self._pending_logs = self._pending_logs, []
        for tag, msg in batch:
            color = {
                "ok": GREEN, "warn": YELLOW, "err": RED,
                "net": CYAN, "pip": CYAN, "py": CYAN, "sys": GRAY,
                "fs": GRAY, "venv": CYAN, "run": GRAY, "info": FG,
                "hint": CYAN,
            }.get(tag, FG)
            safe = (str(msg).replace("&", "&amp;")
                           .replace("<", "&lt;")
                           .replace(">", "&gt;"))
            self.log.appendHtml(
                f'<span style="color:{color};font-weight:bold">[{tag}]</span> '
                f'<span style="color:{FG}">{safe}</span>')
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _ask_password(self, prompt):
        dlg = PasswordDialog(self, prompt)
        if dlg.exec_() == QDialog.Accepted:
            return dlg.value()
        return None

    def start_install(self):
        if self._worker is not None:
            return
        self.install_btn.setEnabled(False)
        self.install_btn.setText("Installing...")
        self.bar.setValue(0)

        self._worker = InstallWorker(self._log)
        self._worker.log_line.connect(self._log, Qt.QueuedConnection)
        self._worker.progress.connect(self.bar.setValue, Qt.QueuedConnection)
        self._worker.finished_ok.connect(self._on_done, Qt.QueuedConnection)
        self._worker.request_password.connect(
            self._on_password_request, Qt.QueuedConnection)
        self._worker.start()

    def _on_password_request(self, prompt):
        pwd = self._ask_password(prompt)
        if pwd is None:
            self._worker.cancel()
        else:
            self._worker.supply_password(pwd)

    def _on_done(self, ok, msg):
        self._done = True
        self._worker = None
        if ok:
            self._log("ok", "============================================")
            self._log("ok", " Xeria Launcher is installed.")
            self._log("ok", "============================================")
            if IS_LINUX or IS_MAC:
                py = (VENV_DIR / "Scripts" / "python.exe") if IS_WIN \
                    else (VENV_DIR / "bin" / "python")
                self._log("hint", f'launch: "{py}" "{INSTALL_DIR / APP_EXEC}"')
                self._log("hint", "or open it from your application menu")
            elif IS_WIN:
                self._log("hint", "launch from Start Menu or Desktop shortcut")
            self._log("info", "")
            self._log("info", "Feel free to close this window.")
            self.bar.setValue(100)
            self.install_btn.setText("Done")
            self.install_btn.setEnabled(False)
            self.close_btn.setStyleSheet(
                f"QPushButton{{background:{ACCENT};color:#000000;border:none;"
                f"padding:10px 20px;font-weight:bold;font-family:'{UI_FONT}'}}"
                f"QPushButton:hover{{background:{ACCENT2}}}")
        else:
            self._log("err", f"installation failed: {msg}")
            self.bar.setValue(0)
            self.install_btn.setEnabled(True)
            self.install_btn.setText("Retry")
            QMessageBox.critical(self, "Installation failed", msg)

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            if QMessageBox.question(
                    self, "Quit",
                    "Installation is still running. Quit anyway?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No) != QMessageBox.Yes:
                event.ignore()
                return
            self._worker.cancel()
            self._worker.wait(2000)
        event.accept()


def main():
    os.environ.setdefault("QT_STYLE_OVERRIDE", "Fusion")
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    ic = QIcon.fromTheme("applications-games")
    if not ic.isNull():
        app.setWindowIcon(ic)
    w = InstallerWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
