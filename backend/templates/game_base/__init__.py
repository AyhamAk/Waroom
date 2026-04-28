"""
game_base scaffold.

Helpers to copy the working Three.js + Vite baseline into a per-session
workspace. The Engine Engineer agent never has to recreate package.json or
the engine modules — it customises this baseline.
"""
import shutil
from pathlib import Path


_TEMPLATE_ROOT = Path(__file__).parent


def scaffold_game_workspace(workspace_dir: str) -> Path:
    """
    Copy templates/game_base/* into <workspace>/game/.

    Files already in the target are left untouched so resuming a session is
    safe — only missing files are filled in. Returns the path to the
    scaffolded game/ subdirectory.
    """
    target = Path(workspace_dir) / "game"
    target.mkdir(parents=True, exist_ok=True)

    for src in _TEMPLATE_ROOT.rglob("*"):
        if src.is_dir():
            continue
        if _is_template_internal(src):
            continue
        rel = src.relative_to(_TEMPLATE_ROOT)
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            shutil.copy2(src, dst)

    return target


def _is_template_internal(path: Path) -> bool:
    """Skip Python module bookkeeping files when copying the scaffold."""
    if path.name == "__init__.py":
        return True
    if path.suffix == ".pyc":
        return True
    if "__pycache__" in path.parts:
        return True
    return False


def template_files() -> list[str]:
    """Return the list of relative paths shipped in the scaffold."""
    out: list[str] = []
    for p in _TEMPLATE_ROOT.rglob("*"):
        if p.is_dir() or _is_template_internal(p):
            continue
        out.append(str(p.relative_to(_TEMPLATE_ROOT)).replace("\\", "/"))
    return sorted(out)
