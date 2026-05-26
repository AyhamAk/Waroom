"""
texture_gen.py — procedural PNG texture generator.

Zero external dependencies: uses stdlib zlib + struct for PNG encoding.
If Pillow is installed, uses it for faster image writing only.

Public API:
  generate_all_textures(spec_dict, workspace_dir) -> dict
    spec_dict: {surface_id: {texture_type, pattern, primary_color,
                              secondary_color, tile_repeat}}
    workspace_dir: absolute path string
    returns: {surface_id: {file, repeat}}  (also writes docs/textures.json)
"""
import json
import math
import struct
import zlib
from pathlib import Path

try:
    from PIL import Image as _PILImage
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

SIZE = 256  # texture resolution (256×256)


# ── Math helpers ──────────────────────────────────────────────────────────────

def hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip('#')
    if len(h) != 6:
        return (128, 128, 128)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (128, 128, 128)


def _clamp(v: float, lo: int = 0, hi: int = 255) -> int:
    return max(lo, min(hi, int(v)))


def _lerp_rgb(c1: tuple, c2: tuple, t: float) -> tuple:
    t = max(0.0, min(1.0, t))
    return (
        _clamp(c1[0] + (c2[0] - c1[0]) * t),
        _clamp(c1[1] + (c2[1] - c1[1]) * t),
        _clamp(c1[2] + (c2[2] - c1[2]) * t),
    )


def _hash_float(a: int, b: int, seed: int = 0) -> float:
    """Deterministic pseudo-random float in [0, 1] — no stdlib hash randomisation."""
    h = (a * 1664525 + b * 1013904223 + seed * 22695477) & 0xFFFFFFFF
    h = h ^ (a * 214013 + b * 2531011 + seed * 6364136223846793005) & 0xFFFFFFFF
    h = (h ^ (h >> 16)) * 0x45D9F3B & 0xFFFFFFFF
    h = (h ^ (h >> 16)) & 0xFFFFFFFF
    return h / 0xFFFFFFFF


def _smoothstep(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


def _value_noise(x: float, y: float, seed: int = 0) -> float:
    """Bilinear value noise, returns [0, 1]."""
    ix, iy = int(math.floor(x)), int(math.floor(y))
    fx, fy = x - ix, y - iy
    ux, uy = _smoothstep(fx), _smoothstep(fy)
    a = _hash_float(ix,     iy,     seed)
    b = _hash_float(ix + 1, iy,     seed)
    c = _hash_float(ix,     iy + 1, seed)
    d = _hash_float(ix + 1, iy + 1, seed)
    return a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy


def _fbm(x: float, y: float, octaves: int = 5, seed: int = 0) -> float:
    """Fractal Brownian Motion, returns [0, 1]."""
    val, amp, freq, total = 0.0, 0.5, 1.0, 0.0
    for _ in range(octaves):
        val += _value_noise(x * freq, y * freq, seed) * amp
        total += amp
        amp *= 0.5
        freq *= 2.0
    return val / total


# ── Texture generators ────────────────────────────────────────────────────────

def _gen_noise(size: int, primary: tuple, secondary: tuple,
               octaves: int = 5, seed: int = 0) -> list:
    pixels = []
    for y in range(size):
        ny = (y / size) * 4.0
        for x in range(size):
            nx = (x / size) * 4.0
            t = _fbm(nx, ny, octaves=octaves, seed=seed)
            pixels.append(_lerp_rgb(primary, secondary, t))
    return pixels


def _gen_grain(size: int, primary: tuple, secondary: tuple, seed: int = 0) -> list:
    """Wood grain: distorted concentric rings + horizontal streak."""
    cx, cy = size / 2.0, size / 2.0
    pixels = []
    for y in range(size):
        for x in range(size):
            dx, dy = x - cx, y - cy
            dist = math.sqrt(dx * dx + dy * dy)
            noise_warp = _value_noise(x * 0.04, y * 0.04, seed) * 10.0
            rings = math.sin((dist * 0.18 + noise_warp) * math.pi) * 0.5 + 0.5
            grain = _value_noise(x * 0.9, y * 0.04, seed + 1) * 0.3
            t = rings * 0.7 + grain * 0.3
            pixels.append(_lerp_rgb(primary, secondary, t))
    return pixels


def _gen_grid(size: int, primary: tuple, secondary: tuple) -> list:
    """Sci-fi grid: dark base + bright grid lines."""
    cell = max(16, size // 16)
    line_w = max(1, cell // 8)
    pixels = []
    for y in range(size):
        for x in range(size):
            in_x = (x % cell) < line_w
            in_y = (y % cell) < line_w
            t = 1.0 if (in_x or in_y) else 0.0
            # Slight corner brightening for tech-panel look
            if (x % cell) < line_w and (y % cell) < line_w:
                t = 1.0
            pixels.append(_lerp_rgb(primary, secondary, t))
    return pixels


def _gen_brick(size: int, primary: tuple, secondary: tuple,
               mortar: tuple = (30, 28, 26)) -> list:
    """Brick pattern with offset rows and per-brick variation."""
    bw = max(32, size // 8)
    bh = max(16, size // 16)
    mw = max(2, bw // 12)

    pixels = []
    for y in range(size):
        row = y // bh
        offset = (bw // 2) if (row % 2) else 0
        in_mortar_y = (y % bh) < mw
        for x in range(size):
            bx = (x + offset) % bw
            in_mortar_x = bx < mw
            if in_mortar_x or in_mortar_y:
                pixels.append(mortar)
            else:
                brick_col = (x + offset) // bw
                var = (_hash_float(brick_col, row) - 0.5) * 28
                pixels.append((
                    _clamp(primary[0] + var),
                    _clamp(primary[1] + var),
                    _clamp(primary[2] + var),
                ))
    return pixels


def _gen_marble(size: int, primary: tuple, secondary: tuple, seed: int = 0) -> list:
    """Marble: fBm-distorted sine veins."""
    pixels = []
    for y in range(size):
        ny = y / size * 3.0
        for x in range(size):
            nx = x / size * 3.0
            n = _fbm(nx, ny, octaves=4, seed=seed)
            veins = math.sin((nx + ny + n * 4.0) * math.pi * 2.5) * 0.5 + 0.5
            t = veins * 0.65 + n * 0.35
            pixels.append(_lerp_rgb(primary, secondary, t))
    return pixels


# ── PNG encoder (pure stdlib fallback) ───────────────────────────────────────

def _write_png_stdlib(pixels: list, size: int, path: Path) -> None:
    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', crc)

    ihdr = struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0)
    raw = bytearray()
    for y in range(size):
        raw.append(0)  # filter: None
        for x in range(size):
            r, g, b = pixels[y * size + x]
            raw += bytes([_clamp(r), _clamp(g), _clamp(b)])

    path.write_bytes(
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', ihdr)
        + chunk(b'IDAT', zlib.compress(bytes(raw), 6))
        + chunk(b'IEND', b'')
    )


def _write_png(pixels: list, size: int, path: Path) -> None:
    if _HAS_PIL:
        data = bytearray()
        for r, g, b in pixels:
            data += bytes([_clamp(r), _clamp(g), _clamp(b)])
        img = _PILImage.frombytes('RGB', (size, size), bytes(data))
        img.save(str(path), 'PNG', optimize=True)
    else:
        _write_png_stdlib(pixels, size, path)


# ── Dispatch ──────────────────────────────────────────────────────────────────

_PATTERN_FN = {
    "grid":   lambda s, p, c, seed: _gen_grid(s, p, c),
    "grain":  lambda s, p, c, seed: _gen_grain(s, p, c, seed),
    "brick":  lambda s, p, c, seed: _gen_brick(s, p, c),
    "marble": lambda s, p, c, seed: _gen_marble(s, p, c, seed),
    "noise":  lambda s, p, c, seed: _gen_noise(s, p, c, seed=seed),
}


def generate_surface_texture(
    surface_id: str,
    spec: dict,
    output_dir: Path,
    size: int = SIZE,
    seed: int = 42,
) -> str:
    """Generate one PNG. Returns relative URL path like 'textures/floor.png'."""
    output_dir.mkdir(parents=True, exist_ok=True)
    primary = hex_to_rgb(spec.get("primary_color", "#2a2a3e"))
    secondary = hex_to_rgb(spec.get("secondary_color", "#111122"))
    pattern = spec.get("pattern", "noise")

    fn = _PATTERN_FN.get(pattern, _PATTERN_FN["noise"])
    pixels = fn(size, primary, secondary, seed)

    out_path = output_dir / f"{surface_id}.png"
    _write_png(pixels, size, out_path)
    return f"textures/{surface_id}.png"


def generate_all_textures(spec_dict: dict, workspace_dir: str) -> dict:
    """
    Generate all surface textures from spec_dict.
    Writes game/public/textures/*.png and docs/textures.json.
    Returns: {surface_id: {file, repeat}}
    """
    workspace = Path(workspace_dir)
    tex_dir = workspace / "game" / "public" / "textures"
    tex_dir.mkdir(parents=True, exist_ok=True)

    result = {}
    for i, (surface_id, spec) in enumerate(spec_dict.items()):
        try:
            file_path = generate_surface_texture(
                surface_id, spec, tex_dir,
                size=SIZE, seed=42 + i * 17,
            )
            result[surface_id] = {
                "file": file_path,
                "repeat": spec.get("tile_repeat", 4),
            }
        except Exception as exc:
            result[surface_id] = {
                "file": None,
                "repeat": spec.get("tile_repeat", 4),
                "error": str(exc),
            }

    # Write docs/textures.json
    docs_dir = workspace / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    textures_json = json.dumps(result, indent=2)
    (docs_dir / "textures.json").write_text(textures_json, encoding="utf-8")

    # Mirror to game/public for runtime /textures.json fetch
    pub_dir = workspace / "game" / "public"
    pub_dir.mkdir(parents=True, exist_ok=True)
    (pub_dir / "textures.json").write_text(textures_json, encoding="utf-8")

    return result
