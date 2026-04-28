"""
WarRoom asset library — tagged CC0 glTFs the Asset Lead picks from.

Public API:

    from assets import search_library, get_asset, copy_to_workspace, library_summary

    hits = search_library(type="character_rigged", tags=["humanoid"], anims=["walk","run"])
    if hits:
        manifest_entry = copy_to_workspace(hits[0]["id"], workspace_dir)
        # → manifest entry with type=gltf, path=/assets/<file>.glb, anims=[...]

The library lives at backend/assets/library/, indexed in
backend/assets/library.json. To rebuild the index after dropping new
packs:

    python -m assets.index_library

To download the Khronos starter pack (public-domain PBR test set, including
the animated Fox character):

    python -m assets.bootstrap
"""
from .library import (
    search_library,
    get_asset,
    copy_to_workspace,
    library_summary,
    library_path,
    available_types,
    available_tags,
)

__all__ = [
    "search_library",
    "get_asset",
    "copy_to_workspace",
    "library_summary",
    "library_path",
    "available_types",
    "available_tags",
]
