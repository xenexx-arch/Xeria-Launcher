import json
import requests
from core.paths import MODRINTH_API


def search(query, kind, mc_version=None, loader=None, limit=30):
    facets = [[f"project_type:{kind}"]]
    if mc_version and kind != "modpack":
        facets.append([f"versions:{mc_version}"])
    if kind == "mod" and loader and loader != "vanilla":
        facets.append([f"categories:{loader}"])
    r = requests.get(f"{MODRINTH_API}/search", timeout=15, params={
        "query": query, "limit": limit, "facets": json.dumps(facets)})
    r.raise_for_status()
    return [{"id": h["project_id"], "title": h["title"], "author": h["author"],
             "desc": h.get("description", ""), "dl": h.get("downloads", 0),
             "categories": h.get("categories", [])}
            for h in r.json().get("hits", [])]


def pick_file(project_id, mc_version, kind, loader=None):
    r = requests.get(f"{MODRINTH_API}/project/{project_id}/version", timeout=15)
    r.raise_for_status()
    versions = r.json()
    candidates = []
    for x in versions:
        if mc_version and mc_version not in x.get("game_versions", []): continue
        if kind == "mod" and loader and loader != "vanilla":
            if loader not in (x.get("loaders") or []): continue
        candidates.append(x)
    chosen = candidates[0] if candidates else (versions[0] if versions else None)
    if not chosen: return None
    files = chosen.get("files", [])
    if not files: return None
    prim = next((f for f in files if f.get("primary")), files[0])
    return prim["url"], prim["filename"]


def search_modpacks(query, limit=20):
    return search(query, "modpack", None, None, limit=limit)


def pick_modpack_file(project_id):
    r = requests.get(f"{MODRINTH_API}/project/{project_id}/version", timeout=15)
    r.raise_for_status()
    for v in r.json():
        for f in v.get("files", []):
            if f["filename"].endswith(".mrpack"):
                return f["url"], f["filename"], v.get("version_number", "")
    return None
