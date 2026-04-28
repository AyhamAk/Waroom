"""
Game recipe library — keyword-matched genre templates.

Each recipe is a JSON file alongside this module. The Director loads the
recipe (or falls back to a generic blueprint), the rest of the pipeline
parametrizes from it.
"""
import json
from pathlib import Path

_GAME_RECIPES_DIR = Path(__file__).parent


def list_game_recipes() -> list[str]:
    return sorted(p.stem for p in _GAME_RECIPES_DIR.glob("*.json"))


def load_game_recipe(name: str) -> dict | None:
    path = _GAME_RECIPES_DIR / f"{name}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def pick_game_recipe(brief: str, genre_hint: str = "auto") -> dict | None:
    """
    Score recipes by keyword hits in the brief plus a strong bonus for an
    explicit genre hint match. Returns the highest-scoring recipe or the
    fallback recipe (one with `"fallback": true`) if nothing matches.
    """
    text = (brief or "").lower()
    best: tuple[int, dict | None] = (0, None)
    fallback: dict | None = None

    for name in list_game_recipes():
        recipe = load_game_recipe(name)
        if not recipe:
            continue
        if recipe.get("fallback"):
            fallback = recipe
        score = 0
        for kw in recipe.get("match", []):
            if kw.lower() in text:
                score += 3
        if genre_hint and genre_hint != "auto" and recipe.get("genre") == genre_hint:
            score += 8
        if score > best[0]:
            best = (score, recipe)

    return best[1] if best[1] else fallback


def parameterize_recipe(recipe: dict, brief: str, art_style: str = "stylized") -> dict:
    """Strip metadata fields and inject the user's brief + style preference."""
    if not recipe:
        return {}
    spec = {k: v for k, v in recipe.items() if k not in ("match", "fallback", "name")}
    spec["brief"] = brief
    if art_style and art_style != "auto":
        spec["art_style"] = art_style
    return spec
