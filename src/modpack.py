import json, zipfile, shutil, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from paths import PROFILES_DIR
from profile import Profile


def read_index(mrpack_path):
    with zipfile.ZipFile(mrpack_path) as z:
        with z.open("modrinth.index.json") as f:
            return json.loads(f.read().decode("utf-8"))


def detect_loader(deps):
    for key, name in (("fabric-loader", "fabric"), ("quilt-loader", "quilt"),
                      ("forge", "forge"), ("neoforge", "neoforge")):
        if key in deps: return name, deps[key]
    return "vanilla", ""


def install(mrpack_path, profile_name=None, log=None, progress=None, progress_end=None):
    def L(tag, msg):
        if log: log(tag, msg)
    mrpack_path = Path(mrpack_path)
    if not mrpack_path.exists():
        L("error", f"file not found: {mrpack_path}"); return None
    L("info", f"reading {mrpack_path.name}")
    try:
        index = read_index(mrpack_path)
    except Exception as e:
        L("error", f"failed to read modpack: {e}"); return None
    name = index.get("name", mrpack_path.stem)
    deps = index.get("dependencies", {})
    mc_version = deps.get("minecraft")
    if not mc_version:
        L("error", "modpack has no minecraft version"); return None
    loader, _ = detect_loader(deps)
    L("ok", f"pack: {name}")
    L("java", f"mc {mc_version}  ·  loader {loader}")
    profile_name = profile_name or name
    base = profile_name; n = 1
    while (PROFILES_DIR / f"{profile_name}.json").exists():
        profile_name = f"{base} ({n})"; n += 1
    p = Profile(profile_name)
    p.version = mc_version; p.ram = "4"; p.loader = loader
    p.dir; p.save()
    L("ok", f"created profile '{profile_name}'")
    files = index.get("files", [])
    L("sys", f"{len(files)} files to download")
    lock = threading.Lock(); done = [0]
    session = requests.Session()
    def fetch(entry):
        url = entry.get("downloads", [None])[0]
        rel = entry.get("path")
        if not url or not rel: return False
        dest = p.dir / rel
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with session.get(url, stream=True, timeout=60) as r:
                r.raise_for_status()
                tmp = dest.with_suffix(dest.suffix + ".part")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(65536): f.write(chunk)
                tmp.replace(dest)
            ok = True
        except Exception as e:
            L("error", f"failed {rel[-50:]}: {e}"); ok = False
        with lock:
            done[0] += 1
            if progress: progress("modpack", done[0], len(files), "", "")
        return ok
    ok_count = 0
    if files:
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures = [ex.submit(fetch, f) for f in files]
            for f in as_completed(futures):
                if f.result(): ok_count += 1
    if progress_end: progress_end()
    L("ok", f"{ok_count}/{len(files)} files downloaded")
    L("sys", "extracting overrides")
    try:
        with zipfile.ZipFile(mrpack_path) as z:
            for prefix in ("overrides/", "client-overrides/"):
                for member in z.namelist():
                    if not member.startswith(prefix): continue
                    rel = member[len(prefix):]
                    if not rel or rel.endswith("/"): continue
                    target = p.dir / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
    except Exception as e:
        L("warn", f"override extraction failed: {e}")
    L("ok", f"modpack '{profile_name}' installed")
    return profile_name


def export_mrpack(profile, dest_path, log=None, progress=None, progress_end=None):
    """Export a profile as a .mrpack. Mods are listed by hash lookups against
    the local mods/ folder using the Modrinth version API when possible;
    otherwise files are bundled into overrides/."""
    import hashlib, re
    def L(tag, msg):
        if log: log(tag, msg)

    dest_path = Path(dest_path)
    index = {
        "formatVersion": 1,
        "game": "minecraft",
        "versionId": "1.0.0",
        "name": profile.name,
        "files": [],
        "dependencies": {"minecraft": profile.version},
    }
    if profile.loader == "fabric":
        index["dependencies"]["fabric-loader"] = "*"
    elif profile.loader == "quilt":
        index["dependencies"]["quilt-loader"] = "*"
    elif profile.loader == "forge":
        index["dependencies"]["forge"] = "*"
    elif profile.loader == "neoforge":
        index["dependencies"]["neoforge"] = "*"

    game_dir = profile.dir
    mods_dir = game_dir / "mods"
    overrides = []  # files to put under overrides/

    # Look up each mod jar's sha1 against Modrinth
    try:
        from modrinth import MODRINTH_API
        import requests
    except Exception:
        MODRINTH_API = None
        requests = None

    if mods_dir.exists():
        jars = [f for f in mods_dir.iterdir() if f.is_file() and f.suffix == ".jar"]
        L("sys", f"hashing {len(jars)} mods")
        for i, jar in enumerate(jars, 1):
            try:
                sha1 = hashlib.sha1(jar.read_bytes()).hexdigest()
            except Exception:
                overrides.append(jar); continue
            found = None
            if requests and MODRINTH_API:
                try:
                    r = requests.get(f"{MODRINTH_API}/version_file/{sha1}",
                                     timeout=10)
                    if r.status_code == 200:
                        found = r.json()
                except Exception:
                    pass
            if found:
                # get project for slug/path
                proj_id = found.get("project_id")
                fname = found.get("file_name", jar.name)
                urls = found.get("files", [])
                primary = next((u for u in urls if u.get("primary")), urls[0] if urls else None)
                if primary and "url" in primary:
                    index["files"].append({
                        "path": f"mods/{fname}",
                        "hashes": {"sha1": sha1,
                                   "sha512": primary.get("hashes", {}).get("sha512", "")},
                        "downloads": [primary["url"]],
                        "fileSize": primary.get("size", jar.stat().st_size),
                    })
                else:
                    overrides.append(jar)
            else:
                overrides.append(jar)
            if progress and i % 5 == 0:
                progress("hash", i, len(jars), "", "")

    L("ok", f"{len(index['files'])} mods matched, {len(overrides)} bundled")
    if progress_end: progress_end()

    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("modrinth.index.json", json.dumps(index, indent=2))
        # Bundle overrides (mods we couldn't match + configs + saves)
        for src in overrides:
            arc = f"overrides/{src.relative_to(game_dir)}"
            z.write(src, arc)
        for sub in ("config", "resourcepacks", "shaderpacks", "saves", "options.txt"):
            p = game_dir / sub
            if p.is_dir():
                for f in p.rglob("*"):
                    if f.is_file():
                        z.write(f, f"overrides/{f.relative_to(game_dir)}")
            elif p.is_file():
                z.write(p, f"overrides/{p.name}")

    L("ok", f"exported → {dest_path.name}")
    return str(dest_path)
