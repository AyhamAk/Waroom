"""
GameState — TypedDict for the 3D game studio pipeline.

Mirrors the Blender pipeline shape: each agent overwrites its slice, control
flow is explicit (cycle, is_done, verdict, regression history). Designed so
graph routing can branch on state without inspecting the workspace.
"""
from typing import Optional
from typing_extensions import TypedDict


class GameState(TypedDict):
    # Session identity
    session_id: str
    workspace_dir: str          # absolute path to per-session workspace
    api_key: str

    # User inputs
    brief: str                  # raw description of the game to build
    genre: str                  # topdown_shooter | platformer | fps_arena | racing | walking_sim | tower_defense
    art_style: str              # realistic | stylized | toon | low_poly | pixel_3d
    target: str                 # web | mobile | desktop
    recipe_name: Optional[str]  # if a recipe matched the brief

    # Director output
    game_design: str            # docs/game-design.md (pillars, core loop, win/lose, controls)

    # Level designer output
    levels_manifest: str        # docs/levels/manifest.json — list of levels + paths

    # Asset lead output
    asset_manifest: str         # docs/asset-manifest.json — id → {path, type, source, gltf}

    # Engine engineer output
    engine_config: str          # docs/engine-config.json — renderer/physics/input wiring

    # Tech-art output
    materials_config: str       # docs/materials.json — material/lighting/post-fx presets

    # Gameplay programmer output (just records files written)
    gameplay_files: list

    # Playtester loop state
    playtest_pass: int          # how many playtest passes for current cycle
    playtest_verdict: str       # APPROVED | REVISE
    playtest_score: float       # 0-10
    playtest_fixes: list        # list of {op, args} typed fix ops
    playtest_report: str        # raw JSON report
    playtest_score_history: list  # for regression detection
    is_rebuild: bool            # rebuild flag — discard fix attempts, re-run engine + gameplay from spec

    # Render artefacts
    latest_screenshot: Optional[str]   # abs path to most recent playtest screenshot
    preview_url: Optional[str]         # served URL of the running build

    # Control flow
    cycle: int
    is_done: bool
    director_feedback: str      # APPROVED or improvement notes after playtest

    # Token accounting
    total_tokens: int


def make_game_state(
    session_id: str,
    workspace_dir: str,
    api_key: str,
    brief: str,
    genre: str = "auto",
    art_style: str = "stylized",
    target: str = "web",
) -> GameState:
    return GameState(
        session_id=session_id,
        workspace_dir=workspace_dir,
        api_key=api_key,
        brief=brief,
        genre=genre,
        art_style=art_style,
        target=target,
        recipe_name=None,
        game_design="",
        levels_manifest="",
        asset_manifest="",
        engine_config="",
        materials_config="",
        gameplay_files=[],
        playtest_pass=0,
        playtest_verdict="",
        playtest_score=0.0,
        playtest_fixes=[],
        playtest_report="",
        playtest_score_history=[],
        is_rebuild=False,
        latest_screenshot=None,
        preview_url=None,
        cycle=0,
        is_done=False,
        director_feedback="",
        total_tokens=0,
    )
