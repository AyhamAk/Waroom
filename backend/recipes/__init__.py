"""
Scene recipes — pre-validated JSON scene-plans for common request shapes.

When a product + style matches a recipe, we skip the Scene Architect entirely
and hand the recipe straight to the Artist (parameterised with product details).
This typically cuts tokens by ~40-60% for recognised requests.

Usage:
    from recipes import pick_recipe, parameterize
    recipe = pick_recipe("a luxury watch on marble", style="luxury")
    if recipe:
        spec = parameterize(recipe, product_description="...", style="luxury")
        # hand spec to Artist directly
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

_RECIPE_DIR = Path(__file__).parent
_CACHE: dict[str, dict] | None = None


def _load_all() -> dict[str, dict]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    recipes: dict[str, dict] = {}
    for p in _RECIPE_DIR.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if "name" in data:
                recipes[data["name"]] = data
        except Exception as exc:
            print(f"[recipes] failed to load {p.name}: {exc}")
    _CACHE = recipes
    return recipes


def list_recipes() -> list[str]:
    return sorted(_load_all().keys())


def get_recipe(name: str) -> Optional[dict]:
    return _load_all().get(name)


def pick_recipe(description: str, style: str = "commercial") -> Optional[dict]:
    """
    Match a description + style to the best-fitting recipe.
    Returns the recipe dict or None if no confident match.

    Selection order:
      1. Style match + keyword hit: score = 3 + hits
      2. Style match + fallback recipe: score = 3 (no keyword needed)
      3. No match → None
    """
    desc = (description or "").lower()
    tokens = [t for t in desc.replace("-", " ").replace(",", " ").split() if len(t) > 2]

    best: tuple[int, Optional[dict]] = (0, None)
    fallback: Optional[dict] = None
    for name, recipe in _load_all().items():
        m = recipe.get("match") or {}
        styles = m.get("styles") or []
        keywords = [k.lower() for k in (m.get("keywords") or [])]

        if style not in styles:
            continue

        hits = sum(1 for kw in keywords if any(tok in kw or kw in tok for tok in tokens))
        score = 3 + hits   # style already matched = 3 base
        if score > best[0]:
            best = (score, recipe)

        if m.get("fallback") and fallback is None:
            fallback = recipe

    # Prefer a keyword-matched recipe (score >= 4)
    if best[0] >= 4:
        return best[1]
    # Else accept the fallback for this style
    if fallback is not None:
        return fallback
    return None


def parameterize(recipe: dict, product_description: str, style: str) -> dict:
    """
    Clone the recipe and fold in product-specific details. Currently preserves
    the recipe's geometry/lighting (which is the whole point — pre-validated
    composition) and only updates metadata. Future: swap hero primitive based
    on product category, tune colors, etc.
    """
    spec = json.loads(json.dumps(recipe))  # deep copy via JSON
    # Strip recipe-only metadata — the spec goes straight to build_scene_from_spec
    spec.pop("name", None)
    spec.pop("match", None)
    spec["_recipe"] = recipe.get("name", "unknown")
    spec["_product"] = product_description
    return spec
