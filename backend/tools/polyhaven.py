"""
PolyHaven asset search + download.

PolyHaven is a free, CC0, no-auth library of HDRIs, PBR textures, and 3D models.
API: https://api.polyhaven.com/

Used by agents to find photorealistic assets. HDRIs are also downloaded directly
inside Blender via bpy_runtime.set_hdri(slug=...); this module is for the backend
side — searching the catalog and pre-downloading PBR texture maps that Blender
will then load.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Optional

import httpx

_PH_API = "https://api.polyhaven.com"
_PH_FILES = "https://dl.polyhaven.org/file/ph-assets"
_USER_AGENT = "warroom/1.0 (+polyhaven-search)"

# Backend-side cache for search results + texture downloads
_CACHE_DIR = Path(os.environ.get("WARROOM_CACHE", Path.home() / ".warroom_cache")) / "polyhaven"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_META_DIR = _CACHE_DIR / "_meta"
_META_DIR.mkdir(parents=True, exist_ok=True)

VALID_TYPES = ("hdris", "textures", "models")
VALID_TEXTURE_MAPS = ("diffuse", "nor_gl", "rough", "ao", "disp", "metal", "spec", "arm")


# ── Low-level HTTP ────────────────────────────────────────────────────────────
async def _get_json(path: str, params: Optional[dict] = None) -> Optional[dict]:
    url = f"{_PH_API}{path}"
    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        ) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        print(f"[polyhaven] GET {url} failed: {exc}")
        return None


async def _download_file(url: str, dest: Path, timeout: float = 120.0) -> bool:
    if dest.exists() and dest.stat().st_size > 1024:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": _USER_AGENT}) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                with open(tmp, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        f.write(chunk)
        tmp.replace(dest)
        return True
    except Exception as exc:
        if tmp.exists():
            try: tmp.unlink()
            except Exception: pass
        print(f"[polyhaven] download {url} failed: {exc}")
        return False


# ── Public API (backend side) ─────────────────────────────────────────────────
async def list_assets(asset_type: str = "hdris", categories: Optional[list[str]] = None) -> list[dict]:
    """
    Return all assets of a given type, optionally filtered by categories.
    Each dict has: slug, name, categories[], tags[], type, download_count, authors.
    """
    t = asset_type.lower()
    if t not in VALID_TYPES:
        return []

    cache_key = f"list_{t}" + (f"_{'_'.join(sorted(categories))}" if categories else "")
    cache_file = _META_DIR / f"{cache_key}.json"
    if cache_file.exists() and (cache_file.stat().st_mtime > (asyncio.get_event_loop().time() - 86400)):
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    params = {"t": t}
    if categories:
        params["c"] = ",".join(categories)
    data = await _get_json("/assets", params)
    if data is None:
        return []
    # API returns {"slug": {...meta}, ...}
    assets = []
    for slug, meta in data.items():
        assets.append({
            "slug": slug,
            "name": meta.get("name", slug),
            "categories": meta.get("categories", []),
            "tags": meta.get("tags", []),
            "type": t,
            "download_count": meta.get("download_count", 0),
            "authors": list(meta.get("authors", {}).keys()),
        })
    try:
        cache_file.write_text(json.dumps(assets), encoding="utf-8")
    except Exception:
        pass
    return assets


async def search(query: str, asset_type: str = "hdris", limit: int = 10) -> list[dict]:
    """
    Keyword search. Scores by name/tag/category overlap. Returns top `limit`.
    """
    q = query.lower().strip()
    tokens = [t for t in q.replace(",", " ").split() if t]
    if not tokens:
        return []

    assets = await list_assets(asset_type)

    def score(a: dict) -> int:
        name = a["name"].lower()
        tags = " ".join(a["tags"]).lower()
        cats = " ".join(a["categories"]).lower()
        s = 0
        for tok in tokens:
            if tok in name:  s += 5
            if tok in cats:  s += 3
            if tok in tags:  s += 2
        # downloads are a mild tiebreaker
        s += min(a.get("download_count", 0) // 10000, 3)
        return s

    scored = [(score(a), a) for a in assets]
    scored = [(s, a) for s, a in scored if s > 0]
    scored.sort(key=lambda x: -x[0])
    return [a for _, a in scored[:limit]]


async def get_info(slug: str) -> Optional[dict]:
    """Full metadata for a specific slug (including available resolutions)."""
    return await _get_json(f"/info/{slug}")


async def get_files(slug: str) -> Optional[dict]:
    """Download-URL tree for a slug. Keys are map/type → resolution → format → url."""
    return await _get_json(f"/files/{slug}")


async def download_hdri(slug: str, resolution: str = "2k", dest_dir: Optional[Path] = None) -> Optional[str]:
    """
    Download an HDRI .hdr file. Returns the absolute local path or None.
    """
    target_dir = Path(dest_dir) if dest_dir else _CACHE_DIR / "hdris"
    target_dir.mkdir(parents=True, exist_ok=True)
    local = target_dir / f"{slug}_{resolution}.hdr"
    if local.exists() and local.stat().st_size > 10_000:
        return str(local)

    # Try the predictable URL first (fast path)
    fast_url = f"{_PH_FILES}/HDRIs/hdr/{resolution}/{slug}_{resolution}.hdr"
    if await _download_file(fast_url, local):
        return str(local)

    # Fall back to API lookup (handles non-standard names)
    files = await get_files(slug)
    if not files or "hdri" not in files:
        return None
    hdri_info = files["hdri"]
    if resolution not in hdri_info:
        # pick highest available ≤ requested
        resolutions_available = [r for r in hdri_info.keys() if r.endswith("k")]
        if not resolutions_available:
            return None
        resolution = sorted(resolutions_available, key=lambda r: int(r.rstrip("k")))[-1]
    hdr_url = hdri_info[resolution].get("hdr", {}).get("url")
    if not hdr_url:
        return None
    if await _download_file(hdr_url, local):
        return str(local)
    return None


async def download_texture(
    slug: str,
    maps: Optional[list[str]] = None,
    resolution: str = "2k",
    fmt: str = "jpg",
    dest_dir: Optional[Path] = None,
) -> dict[str, str]:
    """
    Download a PBR texture set. Returns {map_name: local_path}.

    Default maps: diffuse + normal (GL) + roughness — the PBR essentials.
    Available map codes: diffuse, nor_gl, rough, ao, disp, metal, spec, arm.
    """
    if maps is None:
        maps = ["diffuse", "nor_gl", "rough"]
    target_dir = Path(dest_dir) if dest_dir else _CACHE_DIR / "textures" / slug
    target_dir.mkdir(parents=True, exist_ok=True)

    files = await get_files(slug)
    if files is None:
        return {}

    out: dict[str, str] = {}
    tasks = []
    for map_code in maps:
        map_info = files.get(map_code)
        if not map_info or resolution not in map_info:
            # pick highest available ≤ requested
            if map_info:
                res_avail = [r for r in map_info.keys() if r.endswith("k")]
                if not res_avail:
                    continue
                resolution_for_map = sorted(res_avail, key=lambda r: int(r.rstrip("k")))[-1]
            else:
                continue
        else:
            resolution_for_map = resolution
        fmt_info = map_info[resolution_for_map].get(fmt)
        if fmt_info is None:
            # fall back to any available format
            fmts = list(map_info[resolution_for_map].keys())
            if not fmts:
                continue
            fmt_info = map_info[resolution_for_map][fmts[0]]
            actual_fmt = fmts[0]
        else:
            actual_fmt = fmt
        url = fmt_info.get("url")
        if not url:
            continue
        local = target_dir / f"{slug}_{map_code}_{resolution_for_map}.{actual_fmt}"
        tasks.append((map_code, url, local))

    async def _one(map_code: str, url: str, dest: Path):
        ok = await _download_file(url, dest)
        return map_code, str(dest) if ok else None

    results = await asyncio.gather(*[_one(*t) for t in tasks])
    for map_code, path in results:
        if path:
            out[map_code] = path
    return out


# ── Sync wrappers for use from Blender-side code (we're async in backend) ────
def download_hdri_sync(slug: str, resolution: str = "2k", dest_dir: Optional[Path] = None) -> Optional[str]:
    try:
        return asyncio.run(download_hdri(slug, resolution, dest_dir))
    except RuntimeError:
        # already in an event loop (shouldn't happen from Blender worker)
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(download_hdri(slug, resolution, dest_dir))
        finally:
            loop.close()
