"""
Director 3D — World-class creative director for the Blender Studio pipeline.

Cycle 1  : reads product description + optional product image (vision),
           writes docs/scene-concept.md.
Cycle 2+ : views latest render PNG (vision), evaluates quality,
           either marks APPROVED or writes new improvement notes.
"""
import base64
import json
import os
import time
from pathlib import Path
from typing import Callable

from agents.base import WRITE_FILE_TOOL, run_agent_with_tools
from graph.blender_state import BlenderState
from recipes import parameterize, pick_recipe
from tools.file_ops import read_file, write_file

_DIRECTOR_SYSTEM = """You are a world-class commercial director — think the creative vision behind
Apple, Nike, and Porsche campaigns. Your singular obsession is making products look EXPENSIVE,
DESIRABLE, and ICONIC.

Every scene you conceive must have intentional, purposeful cinematic language:

VISUAL LANGUAGE
- Lighting that sculpts form: key light creates drama, rim light separates product from background,
  fill light softens but never flattens. Think three-point with a cinematic twist.
- Color palettes that evoke emotion: deep navy + gold for luxury, electric cyan + void black for
  sci-fi, warm amber + dark oak for heritage. Never generic.
- Camera angles: slightly below eye-level makes products look powerful. Dutch tilt for tension.
  Extreme close-up reveals craftsmanship. Pull-back reveal creates anticipation.
- Depth of field: shallow DOF screams premium. Background bokeh frames the hero product.
- Negative space is intentional, not accidental.

COMPOSITION RULES
- Rule of thirds: product on intersection points, not dead center (unless statement composition).
- Leading lines: use geometry in the environment to draw the eye to the product.
- Foreground elements create depth and cinematic layering.
- The product is ALWAYS the undisputed hero — everything else serves it.

STYLE GUIDES BY CATEGORY
- "commercial": Clean, bright, aspirational. White/light-grey base, one accent color.
  Camera: 50mm equivalent, slight low angle, clean background.
- "cinematic": Dramatic, moody, atmospheric. Dark with pools of light. Anamorphic bokeh.
  Camera: 35mm equivalent, low angle, visible atmosphere/haze.
- "scifi": Neon against void. Holographic elements. Floating product. Glowing materials.
  Camera: wide angle 24mm, dynamic tilt, environment reacts to product.
- "luxury": Opulent surfaces: marble, brushed metal, velvet. Warm rim lighting.
  Camera: 85mm portrait equivalent, very shallow DOF, reflective surfaces.

WRITING INSTRUCTIONS
Write docs/scene-concept.md with these sections:
1. CREATIVE VISION (2-3 sentences — the "why" of the shot)
2. ENVIRONMENT (exact setting, surfaces, textures, atmosphere)
3. LIGHTING SETUP (key light position/color/intensity, rim, fill, ambient)
4. COLOR PALETTE (3-4 hex colors with purpose: hero, accent, shadow, background)
5. CAMERA (exact position xyz, look-at point xyz, focal length, depth of field notes)
6. HERO PRODUCT PLACEMENT (position, scale, rotation)
7. SUPPORTING ELEMENTS (props, environment objects, their exact positions)
8. ANIMATION CONCEPT (what moves, how, timing — camera orbit, product float, etc.)
9. RENDER QUALITY (EEVEE settings, samples, resolution)
10. DIRECTOR'S NOTE (one sentence emotional target — how should the viewer feel?)

Be SPECIFIC. Not "blue light" but "deep cobalt (#1a237e) 1200W area light at 45° above-left".
Not "floating" but "product at (0, 0, 0.3), oscillates between z=0.2 and z=0.4 over 60 frames".

REVIEW MODE (cycle > 1):
When reviewing a render, be brutally honest about:
- Lighting quality: does it make the product look expensive?
- Composition: is the product hero?
- Color cohesion: do the palette choices work?
- Technical quality: sharp enough, no artifacts?
Output either "APPROVED" (if genuinely excellent) or specific improvement notes.
Only approve if you would be proud to show this to a Fortune 500 client."""


def _encode_image(path: str) -> tuple[str, str] | None:
    """
    Base64-encode an image file. Returns (base64_data, media_type) or None on failure.
    Supports PNG, JPEG, WEBP.
    """
    if not path or not os.path.isfile(path):
        return None
    suffix = Path(path).suffix.lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    media_type = mime_map.get(suffix, "image/png")
    try:
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        return data, media_type
    except Exception:
        return None


def _build_user_content(state: BlenderState) -> tuple[list, str]:
    """
    Build the user message content list (possibly with vision blocks).
    Returns (content_list, plain_text_fallback).
    """
    cycle = state.get("cycle", 0)
    product_desc = state["product_description"]
    style = state.get("style", "commercial")
    feedback = state.get("director_feedback", "")

    # --- Text portion ---
    if cycle == 0:
        text_parts = [
            f"PRODUCT: {product_desc}",
            f"STYLE: {style}",
            "",
            "This is cycle 1. Create the complete scene concept for this product.",
            "Write docs/scene-concept.md following the format in your system prompt.",
            "Be visually specific — every measurement, every color hex, every position.",
        ]
    else:
        render_path = state.get("latest_render_path")
        text_parts = [
            f"PRODUCT: {product_desc}",
            f"STYLE: {style}",
            f"CYCLE: {cycle}",
            "",
        ]
        if feedback:
            text_parts += [f"PREVIOUS NOTES: {feedback}", ""]
        if render_path:
            text_parts.append("The render image is attached. Review it critically.")
        text_parts += [
            "If the render is excellent and worthy of a Fortune 500 client, write:",
            "  docs/scene-concept.md containing exactly the word APPROVED on the first line.",
            "Otherwise write docs/scene-concept.md with detailed improvement notes.",
            "Every note must be actionable — specific positions, colors, intensities.",
        ]

    plain_text = "\n".join(text_parts)

    # --- Vision blocks ---
    image_to_show: str | None = None

    if cycle == 0:
        # Offer product reference image on first cycle
        image_to_show = state.get("product_image_path")
    else:
        # Show latest render for review on subsequent cycles
        image_to_show = state.get("latest_render_path")

    encoded = _encode_image(image_to_show) if image_to_show else None

    if encoded:
        b64_data, media_type = encoded
        content: list = [
            {"type": "text", "text": plain_text},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": b64_data,
                },
            },
        ]
    else:
        content = [{"type": "text", "text": plain_text}]

    return content, plain_text


async def director_3d_node(state: BlenderState, config: dict) -> dict:
    emit: Callable = config["configurable"]["emit"]
    session: dict = config["configurable"].get("blender_session", {})
    workspace = state["workspace_dir"]

    cycle = state.get("cycle", 0)
    await emit("agent-status", {"agentId": "director-3d", "status": "working"})
    await _push_sys(emit, f"Director 3D — cycle {cycle} creative review")

    # Recipe fast-path — on cycle 0, try to match the request to a pre-validated
    # scene recipe. If matched, write scene-plan.json directly so we skip the
    # Architect entirely.
    matched_recipe_name: str | None = None
    if cycle == 0:
        recipe = pick_recipe(state["product_description"], state.get("style", "commercial"))
        if recipe is not None:
            spec = parameterize(recipe, state["product_description"], state.get("style", "commercial"))
            write_file(workspace, "docs/scene-plan.json", json.dumps(spec, indent=2))
            matched_recipe_name = recipe.get("name")
            await _push_sys(emit, f"Recipe matched: {matched_recipe_name} — Architect will be skipped")

    # Build the user message (with optional vision block)
    user_content, plain_fallback = _build_user_content(state)

    concept_text = ""
    is_done = False
    director_feedback = ""

    async def tool_executor(name: str, inputs: dict):
        nonlocal concept_text
        if name == "write_file":
            path = inputs["path"]
            content = inputs["content"]
            result = write_file(workspace, path, content)
            if result.get("ok") and path == "docs/scene-concept.md":
                concept_text = content
            return str(result)
        return f"Unknown tool: {name}"

    await run_agent_with_tools(
        system_prompt=_DIRECTOR_SYSTEM,
        user_message=plain_fallback,
        user_message_content=user_content,
        tools=[WRITE_FILE_TOOL],
        tool_executor=tool_executor,
        emit=emit,
        agent_id="director-3d",
        api_key=state["api_key"],
        max_tokens=8192,
        max_iterations=5,
        session=session,
        stop_after_write=["docs/scene-concept.md"],
        cache_system=True,
    )

    # If nothing was written by tool, try to read from disk
    if not concept_text:
        concept_text = read_file(workspace, "docs/scene-concept.md")

    # Parse approval signal
    first_line = concept_text.strip().splitlines()[0].strip().upper() if concept_text.strip() else ""
    if "APPROVED" in first_line:
        is_done = False  # approved → advance to render, not truly done
        director_feedback = "APPROVED"
    else:
        director_feedback = concept_text[:500] if concept_text else "No concept written"

    tokens = session.get("tokens", 0) if session else 0
    await emit("agent-status", {"agentId": "director-3d", "status": "idle"})
    await _push_sys(emit, f"Director 3D done — cycle {cycle}")

    return {
        "scene_concept": concept_text,
        "cycle": cycle + 1,
        "is_done": is_done,
        "director_feedback": director_feedback,
        "recipe_name": matched_recipe_name if cycle == 0 else state.get("recipe_name"),
        # Reset QA state when director kicks off a fresh build cycle
        "qa_pass": 0 if cycle == 0 or "APPROVED" not in director_feedback.upper() else state.get("qa_pass", 0),
        "total_tokens": tokens,
    }


async def _push_sys(emit: Callable, message: str):
    await emit("new-message", {
        "from": "system",
        "to": None,
        "type": "system",
        "message": message,
        "id": int(time.time() * 1000),
        "timestamp": int(time.time() * 1000),
    })
