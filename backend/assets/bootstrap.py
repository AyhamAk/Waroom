"""
Download a starter pack of CC0 glTF assets so the Asset Lead has real
models to pick from on first run.

We pull the Khronos glTF Sample Models repo's known-good .glb files via
raw.githubusercontent.com — stable URLs, public-domain models, all
PBR-correct (the canonical test set you've probably seen in renderer
demos for years). Includes the animated Fox so the Animation system has
something to play with.

After this runs, library.json is rebuilt automatically.

Usage:

    python -m assets.bootstrap                     # default starter pack
    python -m assets.bootstrap --extras            # add larger/heavier models too
"""
import argparse
import sys
import time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

_ROOT = Path(__file__).parent
_KHRONOS_DIR = _ROOT / "library" / "khronos"

_REPO_BASE = "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Models/main/2.0"

# Curated starter pack — small, fast, varied. Each is hand-picked to
# exercise a different bit of the engine (animation, PBR, transparency).
STARTER_PACK = [
    {
        "name":  "Fox",
        "url":   f"{_REPO_BASE}/Fox/glTF-Binary/Fox.glb",
        "meta": {
            "type":    "character_rigged",
            "tags":    ["fox", "animal", "creature", "stylized", "rigged", "low_poly", "humanoid_quadruped"],
            "anims":   ["Survey", "Walk", "Run"],
            "credit":  "Pixar (modified by Tomáš Půček) — CC BY 4.0",
            "license": "CC BY 4.0",
        },
    },
    {
        "name":  "DamagedHelmet",
        "url":   f"{_REPO_BASE}/DamagedHelmet/glTF-Binary/DamagedHelmet.glb",
        "meta": {
            "type":    "prop_static",
            "tags":    ["helmet", "scifi", "metallic", "pbr", "hero", "wearable"],
            "anims":   [],
            "credit":  "ctxwing on artstation, distributed under public domain via Khronos.",
            "license": "CC BY-NC 4.0",
        },
    },
    {
        "name":  "Avocado",
        "url":   f"{_REPO_BASE}/Avocado/glTF-Binary/Avocado.glb",
        "meta": {
            "type":    "prop_static",
            "tags":    ["avocado", "food", "small", "pickup", "organic", "pbr"],
            "anims":   [],
            "credit":  "Microsoft — public domain",
            "license": "CC0",
        },
    },
    {
        "name":  "Lantern",
        "url":   f"{_REPO_BASE}/Lantern/glTF-Binary/Lantern.glb",
        "meta": {
            "type":    "prop_static",
            "tags":    ["lantern", "light", "metal", "fantasy", "atmospheric"],
            "anims":   [],
            "credit":  "Microsoft — public domain",
            "license": "CC0",
        },
    },
    {
        "name":  "BoxAnimated",
        "url":   f"{_REPO_BASE}/BoxAnimated/glTF-Binary/BoxAnimated.glb",
        "meta": {
            "type":    "prop_static",
            "tags":    ["box", "animated", "test", "primitive"],
            "anims":   ["animation_AnimatedCube"],
            "credit":  "Cesium — public domain",
            "license": "CC0",
        },
    },
    {
        "name":  "WaterBottle",
        "url":   f"{_REPO_BASE}/WaterBottle/glTF-Binary/WaterBottle.glb",
        "meta": {
            "type":    "prop_static",
            "tags":    ["bottle", "water", "transparent", "pickup", "pbr"],
            "anims":   [],
            "credit":  "Microsoft — public domain",
            "license": "CC0",
        },
    },
]

EXTRAS_PACK = [
    {
        "name":  "Sponza",
        "url":   f"{_REPO_BASE}/Sponza/glTF-Binary/Sponza.glb",
        "meta": {
            "type":    "environment_tile",
            "tags":    ["sponza", "atrium", "marble", "indoor", "test_scene", "hero"],
            "anims":   [],
            "credit":  "Crytek — restored by Khronos.",
            "license": "CC BY 3.0",
        },
    },
    {
        "name":  "FlightHelmet",
        "url":   f"{_REPO_BASE}/FlightHelmet/glTF-Binary/FlightHelmet.glb",
        "meta": {
            "type":    "prop_static",
            "tags":    ["helmet", "wearable", "leather", "fabric", "pbr", "hero"],
            "anims":   [],
            "credit":  "Microsoft — public domain",
            "license": "CC0",
        },
    },
    {
        "name":  "BrainStem",
        "url":   f"{_REPO_BASE}/BrainStem/glTF-Binary/BrainStem.glb",
        "meta": {
            "type":    "character_rigged",
            "tags":    ["humanoid", "rigged", "test", "stylized"],
            "anims":   ["animation_0"],
            "credit":  "Keith Hunter / Smithsonian / mixamo.com",
            "license": "CC0",
        },
    },
]


def download(url: str, target: Path, timeout: float = 30) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 1024:
        print(f"  [exists]  {target.name} ({target.stat().st_size:,} bytes)")
        return True
    req = Request(url, headers={"User-Agent": "WarRoom-Asset-Bootstrap/1.0"})
    try:
        with urlopen(req, timeout=timeout) as r:
            data = r.read()
        target.write_bytes(data)
        print(f"  [saved]   {target.name} ({len(data):,} bytes)")
        return True
    except (URLError, HTTPError) as exc:
        print(f"  [FAIL]  {target.name} — {exc}")
        return False


def write_meta(target: Path, meta: dict) -> None:
    sidecar = target.with_suffix(target.suffix + ".meta.json")
    import json
    sidecar.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download a starter CC0 glTF pack.")
    parser.add_argument("--extras", action="store_true", help="Also download Sponza/BrainStem/FlightHelmet (heavier)")
    parser.add_argument("--no-index", action="store_true", help="Skip rebuilding library.json after download")
    args = parser.parse_args()

    pack = list(STARTER_PACK)
    if args.extras:
        pack += EXTRAS_PACK

    print(f"WarRoom asset bootstrap -> {_KHRONOS_DIR}")
    print(f"  {len(pack)} assets to fetch.\n")
    _KHRONOS_DIR.mkdir(parents=True, exist_ok=True)

    ok = 0
    fail = 0
    t0 = time.time()
    for asset in pack:
        target = _KHRONOS_DIR / f"{asset['name']}.glb"
        if download(asset["url"], target):
            write_meta(target, asset["meta"])
            ok += 1
        else:
            fail += 1

    print(f"\nDone in {time.time() - t0:.1f}s — {ok} ok, {fail} failed.")

    if not args.no_index:
        print("\nRebuilding index…")
        from .index_library import rebuild
        idx = rebuild()
        print(f"  -> {len(idx['assets'])} assets indexed in library.json")

    if ok == 0:
        print("\nNo files downloaded — check your network and try again.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
