import os, re, glob, shutil, subprocess, platform, zipfile, tarfile
from pathlib import Path
import requests
from paths import JAVA_DIR, MC_ROOT, ADOPTIUM_API, IS_WIN


def recommended_java_for(mc_version):
    try:
        p = mc_version.split(".")
        major = int(p[0])
        minor = int(p[1]) if len(p) > 1 else 0
        patch = int(p[2]) if len(p) > 2 else 0
    except Exception:
        return 25
    if major >= 26: return 25
    if major != 1: return 25
    if minor >= 22: return 25
    if minor == 21: return 25 if patch >= 9 else 21
    if minor == 20: return 21 if patch >= 5 else 17
    if minor >= 18: return 17
    if minor == 17: return 16
    return 8


def java_version(path):
    try:
        kw = dict(capture_output=True, text=True, timeout=8)
        out = subprocess.run([str(path), "-version"], **kw)
    except Exception:
        return None, None
    txt = (out.stderr or "") + "\n" + (out.stdout or "")
    if "version" not in txt.lower(): return None, None
    m = re.search(r'version "([^"]+)"', txt) or re.search(r'version (\S+)', txt)
    ver = m.group(1) if m else "?"
    try:
        major = int(ver.split(".")[1]) if ver.startswith("1.") else int(re.match(r'(\d+)', ver).group(1))
    except Exception:
        major = None
    return ver, major


def find_javas():
    raw = set()
    def add(p):
        if p: raw.add(str(p))
    if IS_WIN:
        roots = [r"C:\Program Files\Java", r"C:\Program Files (x86)\Java",
                 r"C:\Program Files\Eclipse Adoptium",
                 r"C:\Program Files\Microsoft", r"C:\Program Files\Zulu",
                 r"C:\Program Files\Amazon Corretto",
                 os.path.expandvars(r"%LOCALAPPDATA%\Programs\Eclipse Adoptium"),
                 os.path.expandvars(r"%USERPROFILE%\.jdks"),
                 str(MC_ROOT / "runtime")]
        for r in roots:
            if not os.path.isdir(r): continue
            add(os.path.join(r, "bin", "java.exe"))
            for n in os.listdir(r):
                sub = os.path.join(r, n)
                if os.path.isdir(sub):
                    add(os.path.join(sub, "bin", "java.exe"))
                    add(os.path.join(sub, "jre", "bin", "java.exe"))
        for w in (shutil.which("java.exe"), shutil.which("java")): add(w)
        jh = os.environ.get("JAVA_HOME")
        if jh: add(os.path.join(jh, "bin", "java.exe"))
    else:
        for p in ("/usr/bin/java", "/usr/local/bin/java"): add(p)
        for pat in ("/usr/lib/jvm/*/bin/java", "/usr/lib/jvm/*/jre/bin/java",
                    "/usr/lib/jvm/*/*/bin/java", "/opt/*/bin/java",
                    os.path.expanduser("~/.sdkman/candidates/java/*/bin/java"),
                    os.path.expanduser("~/.jdks/*/bin/java"),
                    str(MC_ROOT / "runtime/*/*/bin/java")):
            raw.update(glob.glob(pat))
        add(shutil.which("java"))
        jh = os.environ.get("JAVA_HOME")
        if jh: add(os.path.join(jh, "bin", "java"))
    for p in JAVA_DIR.rglob("java" if not IS_WIN else "java.exe"):
        add(str(p))
    resolved = set()
    for c in raw:
        try: resolved.add(c); resolved.add(os.path.realpath(c))
        except Exception: resolved.add(c)
    out = {}
    for c in resolved:
        try:
            if not Path(c).is_file(): continue
            if not IS_WIN and not os.access(c, os.X_OK): continue
        except Exception: continue
        ver, major = java_version(c)
        if ver: out[c] = (f"Java {ver}", major or 0)
    return sorted(out.items(), key=lambda x: -x[1][1])


def install_java(ver, log=None):
    osname = {"Windows": "windows", "Linux": "linux", "Darwin": "mac"}.get(platform.system(), "linux")
    arch = platform.machine().lower()
    arch = "x64" if arch in ("x86_64", "amd64") else ("aarch64" if arch in ("aarch64", "arm64") else "x64")
    url = f"{ADOPTIUM_API}/assets/latest/{ver}/hotspot?architecture={arch}&image_type=jre&os={osname}&vendor=eclipse"
    try:
        info = requests.get(url, timeout=20).json()
        if not info: return None
        pkg = info[0]["binary"]["package"]
        link, fname, rel = pkg["link"], pkg["name"], info[0]["release_name"]
    except Exception as e:
        if log: log("error", f"adoptium: {e}")
        return None
    dest = JAVA_DIR / rel
    exe = "java.exe" if IS_WIN else "java"
    if not (dest / "bin").exists():
        if log: log("java", f"downloading temurin {ver} ({fname})")
        archive = JAVA_DIR / fname
        try:
            with requests.get(link, stream=True, timeout=120) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0))
                done = 0
                with open(archive, "wb") as f:
                    for chunk in r.iter_content(65536):
                        f.write(chunk); done += len(chunk)
                        if log and total and done % (1024*1024) < 65536:
                            log("java", f"  {done*100//total}%")
            if fname.endswith(".zip"):
                with zipfile.ZipFile(archive) as z: z.extractall(dest)
            else:
                with tarfile.open(archive) as t: t.extractall(dest)
        except Exception as e:
            if log: log("error", f"download failed: {e}")
            return None
        finally:
            try: archive.unlink()
            except Exception: pass
    hits = [m for m in dest.rglob(exe) if m.is_file()]
    if not hits: return None
    path = str(hits[0])
    if not IS_WIN:
        try: os.chmod(path, 0o755)
        except Exception: pass
    return path


def best_java(mc_version, log=None, override=""):
    if override and Path(override).exists():
        return override
    want = recommended_java_for(mc_version)
    if log: log("java", f"need java {want} for {mc_version}")
    installed = find_javas()
    for path, (label, major) in installed:
        if major == want:
            if log: log("java", f"using {label}")
            return path
    for path, (label, major) in installed:
        if major and want <= major <= want + 4:
            if log: log("java", f"using {label} (newer than needed)")
            return path
    if log: log("java", f"java {want} not found — fetching from Adoptium")
    return install_java(want, log)
