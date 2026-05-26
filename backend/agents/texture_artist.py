"""
Texture Artist — deterministic node that generates procedural surface textures.

No LLM call. Reads design docs, applies genre-aware heuristics to classify
each surface category (floor / wall / prop), then calls texture_gen to
produce PNG files at game/public/textures/.

Runs between tech_art and gameplay_programmer.
Writes: game/public/textures/*.png + docs/textures.json
"""
import json
import time
from pathlib import Path
from typing import Callable

from graph.game_state import GameState
from tools.file_ops import read_file, write_file
from tools.texture_gen import generate_all_textures


# ── Heuristics ────────────────────────────────────────────────────────────────

def _darken(hex_color: str, factor: float = 0.65) -> str:
    h = hex_color.lstrip('#')
    if len(h) != 6:
        return '#111111'
    try:
        r = int(int(h[0:2], 16) * factor)
        g = int(int(h[2:4], 16) * factor)
        b = int(int(h[4:6], 16) * factor)
        return f'#{r:02x}{g:02x}{b:02x}'
    except ValueError:
        return '#111111'


def _classify_surfaces(gdd: str, materials: dict) -> dict:
    """
    Map floor / wall / prop to a texture spec based on genre keywords.
    Returns spec_dict for generate_all_textures().
    """
    gdd_lower = gdd.lower()
    lighting_preset = str(
        materials.get('lighting', {}).get('preset', '')
    ).lower()
    combined = gdd_lower + ' ' + lighting_preset

    # Genre flags
    is_scifi       = any(k in combined for k in ['sci-fi', 'sci_fi', 'cyber', 'neon', 'space', 'arena', 'futur', 'tech', 'laser'])
    is_fantasy     = any(k in combined for k in ['fantasy', 'medieval', 'dungeon', 'castle', 'magic', 'stone', 'ancient', 'rpg'])
    is_nature      = any(k in combined for k in ['forest', 'jungle', 'nature', 'grass', 'outdoor', 'terrain', 'wilderness', 'village'])
    is_industrial  = any(k in combined for k in ['industrial', 'factory', 'metal', 'machine', 'warehouse', 'steampunk'])
    is_horror      = any(k in combined for k in ['horror', 'dark', 'gothic', 'decay', 'haunted'])
    is_western     = any(k in combined for k in ['western', 'desert', 'sand', 'wild west', 'saloon', 'cowboy'])

    # Extract palette from block_materials
    block_mats = materials.get('block_materials', {})
    floor_base = block_mats.get('floor', {}).get('base_color', '#2a2a3e')
    wall_base  = block_mats.get('wall',  {}).get('base_color', '#1e1e2e')
    prop_base  = block_mats.get('crate', {}).get('base_color', '#5a4a3a')

    if is_scifi:
        floor = ('sci_fi', 'grid',  floor_base, _darken(floor_base, 0.3), 8)
        wall  = ('metal',  'noise', wall_base,  _darken(wall_base,  0.5), 4)
        prop  = ('metal',  'noise', prop_base,  _darken(prop_base,  0.6), 2)
    elif is_fantasy:
        floor = ('stone',  'noise', floor_base, _darken(floor_base, 0.6), 8)
        wall  = ('stone',  'brick', wall_base,  _darken(wall_base,  0.5), 4)
        prop  = ('stone',  'noise', prop_base,  _darken(prop_base,  0.7), 2)
    elif is_nature:
        floor = ('grass',  'noise', floor_base, _darken(floor_base, 0.55), 8)
        wall  = ('wood',   'grain', wall_base,  _darken(wall_base,  0.6),  4)
        prop  = ('wood',   'grain', prop_base,  _darken(prop_base,  0.65), 2)
    elif is_industrial:
        floor = ('metal',    'noise', floor_base, _darken(floor_base, 0.5), 8)
        wall  = ('concrete', 'noise', wall_base,  _darken(wall_base,  0.6), 4)
        prop  = ('metal',    'noise', prop_base,  _darken(prop_base,  0.6), 2)
    elif is_horror:
        floor = ('concrete', 'noise',  floor_base, _darken(floor_base, 0.4), 6)
        wall  = ('stone',    'brick',  wall_base,  _darken(wall_base,  0.5), 4)
        prop  = ('stone',    'noise',  prop_base,  _darken(prop_base,  0.6), 2)
    elif is_western:
        floor = ('dirt',  'noise', floor_base, _darken(floor_base, 0.6), 8)
        wall  = ('wood',  'grain', wall_base,  _darken(wall_base,  0.6), 4)
        prop  = ('wood',  'grain', prop_base,  _darken(prop_base,  0.7), 2)
    else:
        # Generic: noise with palette colours
        floor = ('noise', 'noise', floor_base, _darken(floor_base, 0.55), 8)
        wall  = ('noise', 'noise', wall_base,  _darken(wall_base,  0.6),  4)
        prop  = ('noise', 'noise', prop_base,  _darken(prop_base,  0.65), 2)

    def _spec(t_type, pattern, primary, secondary, repeat):
        return {
            'texture_type':    t_type,
            'pattern':         pattern,
            'primary_color':   primary,
            'secondary_color': secondary,
            'tile_repeat':     repeat,
        }

    return {
        'floor': _spec(*floor),
        'wall':  _spec(*wall),
        'prop':  _spec(*prop),
    }


# ── LangGraph node ────────────────────────────────────────────────────────────

async def texture_artist_node(state: GameState, config: dict) -> dict:
    emit: Callable = config['configurable']['emit']
    session: dict  = config['configurable'].get('game_session', {})
    workspace = state['workspace_dir']

    await emit('agent-status', {'agentId': 'texture-artist', 'status': 'working'})
    await _push(emit, '🖼️  Texture Artist — generating procedural surface textures')

    textures_map: dict = {}

    try:
        gdd          = read_file(workspace, 'docs/game-design.md') or ''
        materials_raw = read_file(workspace, 'docs/materials.json') or '{}'
        try:
            materials = json.loads(materials_raw)
        except json.JSONDecodeError:
            materials = {}

        spec = _classify_surfaces(gdd, materials)
        types_summary = ', '.join(
            f"{k}={v['texture_type']}/{v['pattern']}" for k, v in spec.items()
        )
        await _push(emit, f'🖼️  Texture plan: {types_summary}')

        textures_map = generate_all_textures(spec, workspace)

        textures_json = json.dumps(textures_map, indent=2)
        await _emit_file(emit, session, 'docs/textures.json', textures_json, 'texture-artist')
        await _push(emit, f'🖼️  Texture Artist done — {len(textures_map)} textures written')

    except Exception as exc:
        await _push(emit, f'⚠️  Texture Artist: {exc} — pipeline continues without textures')

    await emit('agent-status', {'agentId': 'texture-artist', 'status': 'idle'})
    return {
        'textures_config': json.dumps(textures_map, indent=2) if textures_map else '',
        'total_tokens': session.get('tokens', 0) if session else 0,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _push(emit, message: str) -> None:
    await emit('new-message', {
        'from': 'system', 'to': None, 'type': 'system',
        'message': message,
        'id': int(time.time() * 1000),
        'timestamp': int(time.time() * 1000),
    })


async def _emit_file(emit, session, path, content, agent_id) -> None:
    lines = content.count('\n') + 1
    entry = {
        'path': path, 'content': content, 'agentId': agent_id,
        'ts': int(time.time() * 1000), 'lines': lines,
    }
    if session is not None:
        files = session.get('files', [])
        idx = next((i for i, f in enumerate(files) if f['path'] == path), -1)
        if idx >= 0:
            files[idx] = entry
        else:
            files.append(entry)
        session['files'] = files
    await emit('new-file', entry)
