import os, json, zipfile, subprocess, platform, re
from pathlib import Path
import requests
from core.paths import MC_ROOT, NO_WINDOW

FABRIC_META    = "https://meta.fabricmc.net/v2"
QUILT_META     = "https://meta.quiltmc.org/v3"
FORGE_MAVEN    = "https://maven.minecraftforge.net/net/minecraftforge/forge"
FORGE_PROMOS   = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
NEOFORGE_MAVEN = "https://maven.neoforged.net/releases/net/neoforged/neoforge"
NEOFORGE_META  = "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"


def install(loader, mc_version, log=None, progress=None, progress_end=None):
    def L(tag, msg):
        if log: log(tag, msg)
    loader = (loader or "vanilla").lower()
    L("info", f"loader install: {loader} for MC {mc_version}")
    if loader == "vanilla":
        L("sys", "vanilla — nothing to install"); return mc_version
    try:
        if loader == "fabric":   return _install_fabric(mc_version, L)
        if loader == "quilt":    return _install_quilt(mc_version, L)
        if loader == "forge":    return _install_forge(mc_version, L, progress, progress_end)
        if loader == "neoforge": return _install_neoforge(mc_version, L, progress, progress_end)
        L("error", f"unknown loader: {loader}"); return None
    except Exception as e:
        import traceback; traceback.print_exc()
        L("error", f"{loader} install crashed: {e}"); return None


def _install_fabric(mc_version, L):
    existing = _find_installed_version("fabric-loader", mc_version)
    if existing:
        L("ok", f"fabric already installed → {existing}"); return existing
    L("net", f"GET {FABRIC_META}/versions/loader/{mc_version}")
    try:
        r = requests.get(f"{FABRIC_META}/versions/loader/{mc_version}", timeout=20)
        r.raise_for_status(); data = r.json()
    except Exception as e:
        L("error", f"fabric meta fetch failed: {e}"); return None
    if not data:
        L("error", f"fabric has no loader for MC {mc_version}"); return None
    loader_ver = data[0]["loader"]["version"]
    L("java", f"fabric-loader {loader_ver}")
    url = f"{FABRIC_META}/versions/loader/{mc_version}/{loader_ver}/profile/json"
    try:
        r = requests.get(url, timeout=20); r.raise_for_status()
        profile = r.json()
    except Exception as e:
        L("error", f"fabric profile fetch failed: {e}"); return None
    vid = f"fabric-loader-{loader_ver}-{mc_version}"
    _write_version(vid, profile, L)
    _download_libraries(profile.get("libraries", []), L, label="fabric")
    L("ok", f"fabric installed → {vid}"); return vid


def _install_quilt(mc_version, L):
    existing = _find_installed_version("quilt-loader", mc_version)
    if existing:
        L("ok", f"quilt already installed → {existing}"); return existing
    try:
        r = requests.get(f"{QUILT_META}/versions/loader/{mc_version}", timeout=20)
        r.raise_for_status(); data = r.json()
    except Exception as e:
        L("error", f"quilt meta failed: {e}"); return None
    if not data:
        L("error", f"quilt has no loader for MC {mc_version}"); return None
    loader_ver = data[0]["loader"]["version"]
    L("java", f"quilt-loader {loader_ver}")
    url = f"{QUILT_META}/versions/loader/{mc_version}/{loader_ver}/profile/json"
    try:
        r = requests.get(url, timeout=20); r.raise_for_status()
        profile = r.json()
    except Exception as e:
        L("error", f"quilt profile failed: {e}"); return None
    vid = f"quilt-loader-{loader_ver}-{mc_version}"
    _write_version(vid, profile, L)
    _download_libraries(profile.get("libraries", []), L, label="quilt")
    L("ok", f"quilt installed → {vid}"); return vid


def _install_forge(mc_version, L, progress, progress_end):
    existing = _find_installed_version("forge", mc_version)
    if existing:
        L("ok", f"forge already installed → {existing}"); return existing
    try:
        r = requests.get(FORGE_PROMOS, timeout=20); r.raise_for_status()
        promos = r.json().get("promos", {})
    except Exception as e:
        L("error", f"forge promos failed: {e}"); return None
    fver = None
    for key in (f"{mc_version}-recommended", f"{mc_version}-latest"):
        if key in promos: fver = promos[key]; break
    if not fver:
        L("error", f"forge has no build for MC {mc_version}"); return None
    L("java", f"forge {fver}")
    jar_name = f"forge-{mc_version}-{fver}-installer.jar"
    url = f"{FORGE_MAVEN}/{mc_version}-{fver}/{jar_name}"
    jar = _download_installer(url, jar_name, L, progress, progress_end, "forge")
    if not jar: return None
    java = _java_bin(L)
    if not java: return None
    L("sys", "running forge installer")
    rc = _run_installer(java, jar, L)
    if rc != 0:
        L("error", f"forge installer exited {rc}"); return None
    produced = _find_installed_version("forge", mc_version)
    if not produced:
        L("error", "forge installer produced no version dir"); return None
    L("ok", f"forge installed → {produced}"); return produced


def _install_neoforge(mc_version, L, progress, progress_end):
    existing = _find_installed_version("neoforge", mc_version)
    if existing:
        L("ok", f"neoforge already installed → {existing}"); return existing
    parts = mc_version.split(".")
    if len(parts) < 2 or parts[0] != "1":
        L("error", f"neoforge: unsupported MC version {mc_version}"); return None
    prefix = f"{parts[1]}.{parts[2] if len(parts) > 2 else '0'}"
    try:
        r = requests.get(NEOFORGE_META, timeout=20); r.raise_for_status()
        versions = re.findall(r"<version>([^<]+)</version>", r.text)
    except Exception as e:
        L("error", f"neoforge metadata failed: {e}"); return None
    matching = [v for v in versions if v.startswith(prefix + ".")]
    if not matching:
        L("error", f"neoforge has no build for MC {mc_version}"); return None
    nver = matching[-1]
    L("java", f"neoforge {nver}")
    jar_name = f"neoforge-{nver}-installer.jar"
    url = f"{NEOFORGE_MAVEN}/{nver}/neoforge-{nver}-installer.jar"
    jar = _download_installer(url, jar_name, L, progress, progress_end, "neoforge")
    if not jar: return None
    java = _java_bin(L)
    if not java: return None
    L("sys", "running neoforge installer")
    rc = _run_installer(java, jar, L)
    if rc != 0:
        L("error", f"neoforge installer exited {rc}"); return None
    produced = _find_installed_version("neoforge", mc_version)
    if not produced:
        L("error", "neoforge installer produced no version dir"); return None
    L("ok", f"neoforge installed → {produced}"); return produced


def _write_version(vid, profile, L):
    vdir = MC_ROOT / "versions" / vid
    vdir.mkdir(parents=True, exist_ok=True)
    (vdir / f"{vid}.json").write_text(json.dumps(profile, indent=2))
    jar = vdir / f"{vid}.jar"
    if not jar.exists() or jar.stat().st_size < 22:
        with zipfile.ZipFile(jar, "w") as z:
            z.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
    L("sys", f"wrote {vdir}")


def _download_libraries(libs, L, label="libraries"):
    if not libs:
        L("sys", f"{label}: no libraries"); return
    L("sys", f"{label}: {len(libs)} libraries to download")
    for i, lib in enumerate(libs, 1):
        art = lib.get("downloads", {}).get("artifact")
        if not art: continue
        p = MC_ROOT / "libraries" / art["path"]
        if p.exists() and p.stat().st_size > 0: continue
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with requests.get(art["url"], stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(p, "wb") as f:
                    for chunk in r.iter_content(65536): f.write(chunk)
        except Exception as e:
            L("error", f"lib failed {art['path'][-50:]}: {e}")
        if i % 5 == 0: L("sys", f"{label} libs {i}/{len(libs)}")


def _find_installed_version(keyword, mc_version):
    vroot = MC_ROOT / "versions"
    if not vroot.exists(): return None
    for d in vroot.iterdir():
        if not d.is_dir(): continue
        if keyword.lower() in d.name.lower() and mc_version in d.name:
            if (d / f"{d.name}.json").exists(): return d.name
    return None


def _download_installer(url, jar_name, L, progress, progress_end, label):
    tmp = MC_ROOT / "installers"; tmp.mkdir(parents=True, exist_ok=True)
    jar = tmp / jar_name
    if jar.exists() and jar.stat().st_size > 1000:
        L("sys", f"{jar_name} already downloaded"); return jar
    L("net", f"downloading {jar_name}")
    try:
        with requests.get(url, stream=True, timeout=180) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            done = 0
            with open(jar, "wb") as f:
                for chunk in r.iter_content(65536):
                    f.write(chunk); done += len(chunk)
                    if progress and total:
                        progress(label, done, total, "", "")
            if progress_end: progress_end()
        return jar
    except Exception as e:
        L("error", f"installer download failed: {e}"); return None


def _java_bin(L):
    from core.java import find_javas
    javas = find_javas()
    if not javas:
        L("error", "no java found to run installer"); return None
    return javas[0][0]


def _run_installer(java, jar, L):
    cmd = [java, "-jar", str(jar), "--installClient", str(MC_ROOT)]
    L("sys", f"spawn: {' '.join(str(c) for c in cmd)}")
    try:
        proc = subprocess.Popen(cmd, cwd=str(jar.parent),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1, creationflags=NO_WINDOW)
    except Exception as e:
        L("error", f"installer spawn failed: {e}"); return -1
    for line in proc.stdout:
        line = line.rstrip()
        if line: L("mc", line)
    proc.wait()
    return proc.returncode
