"""
bpy_runtime — Preloaded Blender helper library.

Injected into the Blender interpreter ONCE at the start of a session via a single
execute_blender() call. After injection, agents call tiny one-liners:

    br.apply_style('commercial')
    br.make_pbr('hero', preset='brushed_aluminum')
    br.set_hdri(slug='studio_small_08')
    br.camera_orbit(radius=8, frames=120)
    br.compositor_polish(preset='cinematic')
    br.build_scene_from_spec(spec_dict)     # the fast path

Why this exists:
    Every bpy_execute call used to re-send hundreds of lines of boilerplate
    (hex_to_rgb, material node setup, HDRI loader, lighting rigs, etc). That
    cost ~1-2k tokens per call x 20 calls x 3 cycles = huge. This module lives
    INSIDE Blender — load once, call forever.
"""
# flake8: noqa

BPY_RUNTIME_SOURCE = r'''
import bpy, bmesh, math, os, json, tempfile, traceback, urllib.request, urllib.parse, hashlib
from types import SimpleNamespace

# ══════════════════════════════════════════════════════════════════════════════
# bpy_runtime v3 — hardened to avoid bpy.ops wherever possible.
#
# Rationale: bpy.ops needs UI context (active area, active object, selection
# state). The MCP socket handler has no UI context, so ops silently no-op or
# produce wrong results. This version uses bpy.data + bmesh for ALL object
# creation and modification. The only remaining bpy.ops calls are render ones,
# wrapped in bpy.context.temp_override.
# ══════════════════════════════════════════════════════════════════════════════

# ──────────────────────────────────────────────────────────────────────────────
# Material presets — all values hand-tuned for Principled BSDF (Blender 4.x)
# ──────────────────────────────────────────────────────────────────────────────
MATERIAL_PRESETS = {
    # Metals
    "brushed_aluminum":   {"base_color": "#d4d7db", "metallic": 1.0, "roughness": 0.35},
    "chrome":             {"base_color": "#fafafa", "metallic": 1.0, "roughness": 0.05},
    "polished_steel":     {"base_color": "#c8ccd0", "metallic": 1.0, "roughness": 0.15},
    "brushed_steel":      {"base_color": "#b4b8bc", "metallic": 1.0, "roughness": 0.40},
    "gold":               {"base_color": "#ffd27a", "metallic": 1.0, "roughness": 0.20},
    "brushed_gold":       {"base_color": "#d9b060", "metallic": 1.0, "roughness": 0.40},
    "rose_gold":          {"base_color": "#e8a898", "metallic": 1.0, "roughness": 0.25},
    "copper":             {"base_color": "#c47149", "metallic": 1.0, "roughness": 0.30},
    "bronze":             {"base_color": "#8a6a44", "metallic": 1.0, "roughness": 0.45},
    "titanium":           {"base_color": "#8a8c8e", "metallic": 1.0, "roughness": 0.30},
    "black_anodized":     {"base_color": "#1a1a1e", "metallic": 1.0, "roughness": 0.45},
    # Plastics
    "plastic_glossy_black": {"base_color": "#0a0a0c", "metallic": 0.0, "roughness": 0.15, "clearcoat": 0.8},
    "plastic_matte_black":  {"base_color": "#121214", "metallic": 0.0, "roughness": 0.70},
    "plastic_white_glossy": {"base_color": "#f2f2f4", "metallic": 0.0, "roughness": 0.18, "clearcoat": 0.6},
    "plastic_white_matte":  {"base_color": "#eaeaec", "metallic": 0.0, "roughness": 0.65},
    "abs_grey":             {"base_color": "#7a7c80", "metallic": 0.0, "roughness": 0.50},
    # Glass
    "glass_clear":        {"base_color": "#ffffff", "transmission": 1.0, "roughness": 0.00, "ior": 1.45, "alpha": 1.0},
    "glass_frosted":      {"base_color": "#ffffff", "transmission": 1.0, "roughness": 0.35, "ior": 1.45, "alpha": 1.0},
    "glass_tinted_black": {"base_color": "#555560", "transmission": 0.8, "roughness": 0.05, "ior": 1.45, "alpha": 1.0},
    "glass_tinted_blue":  {"base_color": "#a0c8e8", "transmission": 0.8, "roughness": 0.02, "ior": 1.45, "alpha": 1.0},
    "crystal":            {"base_color": "#ffffff", "transmission": 1.0, "roughness": 0.00, "ior": 1.50, "alpha": 1.0},
    # Ceramics / stone
    "ceramic_white":      {"base_color": "#f4f2ee", "metallic": 0.0, "roughness": 0.25, "clearcoat": 0.4},
    "porcelain":          {"base_color": "#fbf9f4", "metallic": 0.0, "roughness": 0.22, "clearcoat": 0.7},
    "concrete_smooth":    {"base_color": "#9a9690", "metallic": 0.0, "roughness": 0.78},
    "concrete_polished":  {"base_color": "#8e8a84", "metallic": 0.0, "roughness": 0.30, "clearcoat": 0.2},
    "marble_white":       {"base_color": "#eeece6", "metallic": 0.0, "roughness": 0.08, "clearcoat": 0.5, "_procedural": "marble_white"},
    "marble_black":       {"base_color": "#1a1818", "metallic": 0.0, "roughness": 0.08, "clearcoat": 0.6, "_procedural": "marble_black"},
    # Fabrics
    "velvet_red":         {"base_color": "#7a0e12", "metallic": 0.0, "roughness": 0.92, "sheen": 1.0},
    "velvet_black":       {"base_color": "#0e0e14", "metallic": 0.0, "roughness": 0.95, "sheen": 1.0},
    "velvet_blue":        {"base_color": "#0e1e58", "metallic": 0.0, "roughness": 0.92, "sheen": 1.0},
    "suede_tan":          {"base_color": "#8a6744", "metallic": 0.0, "roughness": 0.85, "sheen": 0.5},
    "leather_black":      {"base_color": "#0f0d0a", "metallic": 0.0, "roughness": 0.55},
    "leather_brown":      {"base_color": "#3a2618", "metallic": 0.0, "roughness": 0.60},
    "leather_tan":        {"base_color": "#8a5a36", "metallic": 0.0, "roughness": 0.58},
    "denim":              {"base_color": "#2a3a6a", "metallic": 0.0, "roughness": 0.85},
    "cotton_white":       {"base_color": "#f4f4ec", "metallic": 0.0, "roughness": 0.90},
    # Wood
    "walnut_wood":        {"base_color": "#5a3520", "metallic": 0.0, "roughness": 0.50, "clearcoat": 0.2},
    "oak_light":          {"base_color": "#c19660", "metallic": 0.0, "roughness": 0.55},
    "oak_dark":           {"base_color": "#6a4528", "metallic": 0.0, "roughness": 0.50},
    "maple":              {"base_color": "#e8c88a", "metallic": 0.0, "roughness": 0.45},
    "ebony":              {"base_color": "#1a1310", "metallic": 0.0, "roughness": 0.40, "clearcoat": 0.3},
    # Rubber
    "rubber_matte":       {"base_color": "#181818", "metallic": 0.0, "roughness": 0.85},
    # Emissive (neon / holographic)
    "neon_cyan":          {"base_color": "#00e0ff", "emission_color": "#00e0ff", "emission_strength": 8.0, "roughness": 0.40},
    "neon_magenta":       {"base_color": "#ff10c0", "emission_color": "#ff10c0", "emission_strength": 8.0, "roughness": 0.40},
    "neon_amber":         {"base_color": "#ffb040", "emission_color": "#ffb040", "emission_strength": 7.0, "roughness": 0.40},
    "holographic_blue":   {"base_color": "#0080ff", "emission_color": "#0080ff", "emission_strength": 3.0, "roughness": 0.10, "clearcoat": 0.8},
    # Car paint
    "car_paint_red":      {"base_color": "#b8121a", "metallic": 0.6, "roughness": 0.25, "clearcoat": 1.0, "clearcoat_roughness": 0.02},
    "car_paint_black":    {"base_color": "#0a0a0c", "metallic": 0.5, "roughness": 0.22, "clearcoat": 1.0, "clearcoat_roughness": 0.02},
    "car_paint_white":    {"base_color": "#f4f4f4", "metallic": 0.5, "roughness": 0.22, "clearcoat": 1.0, "clearcoat_roughness": 0.02},
    "car_paint_silver":   {"base_color": "#c8ccd0", "metallic": 0.8, "roughness": 0.28, "clearcoat": 1.0, "clearcoat_roughness": 0.02},
}

# ──────────────────────────────────────────────────────────────────────────────
# Curated HDRI registry — hand-picked for each style, all from polyhaven.com
# ──────────────────────────────────────────────────────────────────────────────
HDRI_REGISTRY = {
    "commercial":  [("studio_small_08", 0.9), ("studio_small_09", 1.0), ("studio_small_03", 0.9)],
    "cinematic":   [("industrial_sunset_02_puresky", 0.8), ("rainforest_trail", 0.7), ("moonless_golf", 0.9)],
    "scifi":       [("kloofendal_48d_partly_cloudy", 1.1), ("satara_night", 0.9), ("dikhololo_night", 0.8)],
    "luxury":      [("studio_small_03", 1.0), ("studio_small_04", 0.9), ("brown_photostudio_01", 1.0)],
    "outdoor":     [("kloofendal_48d_partly_cloudy", 1.0), ("sunflowers_puresky", 1.0)],
    "night":       [("dikhololo_night", 0.8), ("satara_night", 0.7)],
}

POLYHAVEN_ASSETS_DIR = os.path.join(tempfile.gettempdir(), "warroom_polyhaven")
os.makedirs(POLYHAVEN_ASSETS_DIR, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# Core helpers
# ──────────────────────────────────────────────────────────────────────────────
def _hex_to_rgb(hex_str, alpha=1.0):
    """'#aabbcc' or 'aabbcc' -> (r, g, b, a) in 0..1 linear-ish range."""
    if hex_str is None:
        return (0.0, 0.0, 0.0, alpha)
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (r, g, b, alpha)


def _safe_remove_all():
    """Fully clear scene WITHOUT bpy.ops — direct data-block removal."""
    # Remove every object (meshes, lights, cameras, empties) via bpy.data.
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    # Purge orphan datablocks
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    for lt in list(bpy.data.lights):
        if lt.users == 0:
            bpy.data.lights.remove(lt)
    for cam in list(bpy.data.cameras):
        if cam.users == 0:
            bpy.data.cameras.remove(cam)
    for img in list(bpy.data.images):
        if img.users == 0:
            bpy.data.images.remove(img)


def _link_to_scene(obj):
    """Link an already-created object to the active scene collection."""
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _mesh_from_bmesh(name, builder):
    """Create a bpy.data.meshes object, run a bmesh builder, return the mesh."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    builder(bm)
    bm.to_mesh(me)
    bm.free()
    me.validate(clean_customdata=False)
    return me


def _build_torus_bmesh(bm, major_radius=0.5, minor_radius=0.15,
                       major_segments=24, minor_segments=12):
    """Parametric torus — bmesh.ops has no create_torus."""
    verts = []
    for i in range(major_segments):
        a = (i / major_segments) * 2 * math.pi
        row = []
        for j in range(minor_segments):
            b = (j / minor_segments) * 2 * math.pi
            x = (major_radius + minor_radius * math.cos(b)) * math.cos(a)
            y = (major_radius + minor_radius * math.cos(b)) * math.sin(a)
            z = minor_radius * math.sin(b)
            row.append(bm.verts.new((x, y, z)))
        verts.append(row)
    for i in range(major_segments):
        ni = (i + 1) % major_segments
        for j in range(minor_segments):
            nj = (j + 1) % minor_segments
            bm.faces.new([verts[i][j], verts[ni][j], verts[ni][nj], verts[i][nj]])
    bm.normal_update()


def _bsdf_set(bsdf, key, value):
    """Set a Principled BSDF input safely — Blender 4.x renamed several."""
    try:
        bsdf.inputs[key].default_value = value
        return True
    except (KeyError, TypeError):
        return False


def _get_or_make_world():
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    return world


# ──────────────────────────────────────────────────────────────────────────────
# Render + colour management
# ──────────────────────────────────────────────────────────────────────────────
def clear_scene():
    _safe_remove_all()


def setup_render(
    engine="EEVEE_NEXT",
    samples=64,
    resolution=(1280, 720),
    fps=24,
    frame_start=1,
    frame_end=120,
):
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT" if engine.upper().startswith("EEVEE") else engine.upper()
    except Exception:
        scene.render.engine = "BLENDER_EEVEE"
    if engine.upper() == "CYCLES":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = samples
        try:
            scene.cycles.device = "GPU"
        except Exception:
            pass
        try:
            scene.cycles.use_denoising = True
        except Exception:
            pass
    scene.render.resolution_x = resolution[0]
    scene.render.resolution_y = resolution[1]
    scene.render.fps = fps
    scene.frame_start = frame_start
    scene.frame_end = frame_end


def setup_filmic(look="High Contrast", exposure=0.0, gamma=1.0):
    scene = bpy.context.scene
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = look
    scene.view_settings.exposure = exposure
    scene.view_settings.gamma = gamma


def setup_eevee_quality(
    bloom=True, bloom_threshold=0.85, bloom_intensity=0.3, bloom_radius=5.0,
    ssr=True, gtao=True, gtao_distance=0.25,
):
    eevee = bpy.context.scene.eevee
    for attr, val in (
        ("use_bloom", bloom), ("bloom_threshold", bloom_threshold),
        ("bloom_intensity", bloom_intensity), ("bloom_radius", bloom_radius),
        ("use_ssr", ssr), ("use_gtao", gtao), ("gtao_distance", gtao_distance),
    ):
        try:
            setattr(eevee, attr, val)
        except (AttributeError, TypeError):
            pass


# ──────────────────────────────────────────────────────────────────────────────
# Materials
# ──────────────────────────────────────────────────────────────────────────────
def make_pbr(
    name,
    base_color="#808080",
    metallic=0.0,
    roughness=0.5,
    ior=1.45,
    transmission=0.0,
    emission_color="#000000",
    emission_strength=0.0,
    alpha=1.0,
    sheen=0.0,
    clearcoat=0.0,
    clearcoat_roughness=0.03,
    normal_strength=1.0,
):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        return mat
    _bsdf_set(bsdf, "Base Color", _hex_to_rgb(base_color))
    _bsdf_set(bsdf, "Metallic", float(metallic))
    _bsdf_set(bsdf, "Roughness", float(roughness))
    _bsdf_set(bsdf, "IOR", float(ior))
    _bsdf_set(bsdf, "Transmission Weight", float(transmission))
    _bsdf_set(bsdf, "Transmission", float(transmission))
    _bsdf_set(bsdf, "Alpha", float(alpha))
    _bsdf_set(bsdf, "Emission Color", _hex_to_rgb(emission_color))
    _bsdf_set(bsdf, "Emission Strength", float(emission_strength))
    _bsdf_set(bsdf, "Sheen Weight", float(sheen))
    _bsdf_set(bsdf, "Sheen", float(sheen))
    _bsdf_set(bsdf, "Coat Weight", float(clearcoat))
    _bsdf_set(bsdf, "Clearcoat", float(clearcoat))
    _bsdf_set(bsdf, "Coat Roughness", float(clearcoat_roughness))
    _bsdf_set(bsdf, "Clearcoat Roughness", float(clearcoat_roughness))
    if alpha < 1.0 or transmission > 0.0:
        try:
            mat.blend_method = "HASHED"
        except Exception:
            pass
    return mat


def make_preset_material(preset_name, name=None):
    """Create a material from the PRESET registry. Returns (mat, was_preset_found)."""
    p = MATERIAL_PRESETS.get(preset_name)
    if p is None:
        return make_pbr(name or preset_name, base_color="#808080"), False
    mat_name = name or preset_name
    proc = p.get("_procedural")
    kwargs = {k: v for k, v in p.items() if not k.startswith("_")}
    mat = make_pbr(mat_name, **kwargs)
    if proc == "marble_white":
        _inject_marble_nodes(mat, vein_color="#6b6765", base="#eeece6")
    elif proc == "marble_black":
        _inject_marble_nodes(mat, vein_color="#3a3836", base="#1a1818")
    return mat, True


def _inject_marble_nodes(mat, vein_color="#6b6765", base="#eeece6"):
    """Replace base color with a noise->ramp driven marble pattern."""
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = nodes.get("Principled BSDF")
    noise = nodes.new("ShaderNodeTexNoise")
    ramp = nodes.new("ShaderNodeValToRGB")
    noise.inputs["Scale"].default_value = 3.5
    noise.inputs["Detail"].default_value = 8.0
    noise.inputs["Roughness"].default_value = 0.6
    noise.inputs["Distortion"].default_value = 0.4
    ramp.color_ramp.elements[0].position = 0.3
    ramp.color_ramp.elements[1].position = 0.7
    ramp.color_ramp.elements[0].color = _hex_to_rgb(base)
    ramp.color_ramp.elements[1].color = _hex_to_rgb(vein_color)
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])


def apply_material(obj_name, mat_or_name):
    obj = bpy.data.objects.get(obj_name)
    if obj is None:
        return False
    mat = mat_or_name if hasattr(mat_or_name, "node_tree") else bpy.data.materials.get(mat_or_name)
    if mat is None:
        return False
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
    return True


# ──────────────────────────────────────────────────────────────────────────────
# Lights
# ──────────────────────────────────────────────────────────────────────────────
def make_light(
    name, type="AREA", location=(0, 0, 4), rotation=(0, 0, 0),
    energy=500, color="#ffffff", size=2.0, spot_size_deg=45, spot_blend=0.3,
):
    """Create a light via bpy.data — no ops, no context dependence."""
    t = type.upper()
    light_data = bpy.data.lights.new(name=f"{name}_data", type=t)
    light_data.energy = float(energy)
    r, g, b, _ = _hex_to_rgb(color)
    light_data.color = (r, g, b)
    if t == "AREA":
        light_data.size = float(size)
    elif t == "SPOT":
        light_data.spot_size = math.radians(float(spot_size_deg))
        light_data.spot_blend = float(spot_blend)
    obj = bpy.data.objects.new(name=name, object_data=light_data)
    obj.location = tuple(float(v) for v in location)
    obj.rotation_euler = tuple(float(v) for v in rotation)
    _link_to_scene(obj)
    return obj


def three_point_rig(
    key_energy=500, fill_ratio=0.3, rim_ratio=0.6,
    key_pos=(-3.5, -2.0, 4.8), fill_pos=(3.8, -1.8, 2.5), rim_pos=(2.5, 3.8, 4.2),
    key_color="#fff4e0", fill_color="#e0e8ff", rim_color="#ffe8c0",
):
    """Classic product-photography key/fill/rim."""
    key = make_light("KeyLight", "AREA", key_pos, (math.radians(50), 0, math.radians(-35)),
                     energy=key_energy, color=key_color, size=1.6)
    fill = make_light("FillLight", "AREA", fill_pos, (math.radians(38), 0, math.radians(44)),
                      energy=key_energy * fill_ratio, color=fill_color, size=3.2)
    rim = make_light("RimLight", "AREA", rim_pos, (math.radians(58), 0, math.radians(148)),
                     energy=key_energy * rim_ratio, color=rim_color, size=1.0)
    return key, fill, rim


# ──────────────────────────────────────────────────────────────────────────────
# HDRI — PolyHaven integration
# ──────────────────────────────────────────────────────────────────────────────
def _download_polyhaven_hdri(slug, resolution="2k"):
    """Download an HDRI from polyhaven.com. Returns local filepath or None."""
    safe_slug = slug.replace("/", "_")
    local_path = os.path.join(POLYHAVEN_ASSETS_DIR, f"{safe_slug}_{resolution}.hdr")
    if os.path.isfile(local_path) and os.path.getsize(local_path) > 10_000:
        return local_path
    # polyhaven serves HDRIs at a predictable URL
    url = f"https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/{resolution}/{slug}_{resolution}.hdr"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "warroom-bpy-runtime/1.0"})
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = resp.read()
        with open(local_path, "wb") as f:
            f.write(data)
        return local_path
    except Exception as exc:
        print(f"HDRI_DOWNLOAD_ERROR: {slug} -> {exc}")
        return None


def set_hdri(slug=None, style=None, filepath=None, resolution="2k", strength=1.0):
    """
    Apply an HDRI to the world environment.

    Priority:
      1. filepath — use a local .hdr file directly.
      2. slug     — download from polyhaven.
      3. style    — pick the first HDRI from HDRI_REGISTRY[style].
    """
    if filepath is None:
        if slug is None and style:
            entries = HDRI_REGISTRY.get(style)
            if entries:
                slug, auto_strength = entries[0]
                strength = strength if strength != 1.0 else auto_strength
        if slug:
            filepath = _download_polyhaven_hdri(slug, resolution)
    if not filepath or not os.path.isfile(filepath):
        print(f"HDRI_UNAVAILABLE: slug={slug} style={style} — falling back to solid colour")
        return False

    world = _get_or_make_world()
    nt = world.node_tree
    nt.nodes.clear()
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    bg = nt.nodes.new("ShaderNodeBackground")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    env.image = bpy.data.images.load(filepath, check_existing=True)
    try:
        env.image.colorspace_settings.name = "Linear Rec.709"
    except Exception:
        env.image.colorspace_settings.name = "Non-Color"
    bg.inputs["Strength"].default_value = float(strength)
    nt.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return True


def set_world_color(color="#0a0a14", strength=1.0):
    world = _get_or_make_world()
    nt = world.node_tree
    nt.nodes.clear()
    bg = nt.nodes.new("ShaderNodeBackground")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg.inputs["Color"].default_value = _hex_to_rgb(color)
    bg.inputs["Strength"].default_value = float(strength)
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


# ──────────────────────────────────────────────────────────────────────────────
# Camera
# ──────────────────────────────────────────────────────────────────────────────
def make_camera(
    name="Camera", location=(5.0, -7.0, 3.5), look_at=(0, 0, 0),
    focal_mm=50, dof_distance=None, fstop=2.8, dutch_deg=0.0,
):
    """Create a camera via bpy.data — no ops. Sets itself as active render camera."""
    cam_data = bpy.data.cameras.new(name=f"{name}_data")
    cam_data.lens = float(focal_mm)
    cam_data.clip_start = 0.05
    cam_data.clip_end = 1000.0
    if dof_distance is not None:
        cam_data.dof.use_dof = True
        cam_data.dof.focus_distance = float(dof_distance)
        cam_data.dof.aperture_fstop = float(fstop)
    cam = bpy.data.objects.new(name=name, object_data=cam_data)
    cam.location = tuple(float(v) for v in location)
    _link_to_scene(cam)
    if dutch_deg:
        cam.rotation_euler[2] = math.radians(float(dutch_deg))
    _aim_camera(cam, look_at)
    bpy.context.scene.camera = cam
    return cam


def _aim_camera(cam, target_xyz):
    """Point a camera at a target without a constraint (so animation is simple)."""
    import mathutils
    origin = mathutils.Vector(cam.location)
    target = mathutils.Vector(target_xyz)
    direction = target - origin
    rot_quat = direction.to_track_quat("-Z", "Y")
    dutch = cam.rotation_euler[2]
    cam.rotation_euler = rot_quat.to_euler()
    cam.rotation_euler[2] += dutch


def track_to(cam_name, target_name):
    cam = bpy.data.objects.get(cam_name)
    tgt = bpy.data.objects.get(target_name)
    if cam is None or tgt is None:
        return False
    for c in list(cam.constraints):
        if c.type == "TRACK_TO":
            cam.constraints.remove(c)
    c = cam.constraints.new(type="TRACK_TO")
    c.target = tgt
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis = "UP_Y"
    return True


# ──────────────────────────────────────────────────────────────────────────────
# Animation
# ──────────────────────────────────────────────────────────────────────────────
def camera_orbit(
    cam_name="Camera", radius=8.0, height=4.0,
    start_deg=-90, end_deg=90, frames=120, target=(0, 0, 0),
):
    cam = bpy.data.objects.get(cam_name)
    if cam is None:
        return False
    cam.animation_data_clear()
    for c in list(cam.constraints):
        if c.type == "TRACK_TO":
            cam.constraints.remove(c)
    start = math.radians(start_deg)
    end = math.radians(end_deg)
    for f in range(1, frames + 1):
        t = (f - 1) / max(frames - 1, 1)
        # smoothstep easing
        te = t * t * (3 - 2 * t)
        angle = start + (end - start) * te
        cam.location = (math.cos(angle) * radius, math.sin(angle) * radius, height)
        cam.keyframe_insert(data_path="location", frame=f)
        _aim_camera(cam, target)
        cam.keyframe_insert(data_path="rotation_euler", frame=f)
    return True


def float_animation(obj_name, amplitude=0.15, frames=120, cycles=1.0):
    obj = bpy.data.objects.get(obj_name)
    if obj is None:
        return False
    base_z = obj.location.z
    for f in range(1, frames + 1):
        t = (f - 1) / max(frames - 1, 1)
        obj.location.z = base_z + math.sin(t * math.pi * 2 * cycles) * amplitude
        obj.keyframe_insert(data_path="location", index=2, frame=f)
    obj.location.z = base_z
    return True


def scale_in_reveal(obj_name, start_frame=1, end_frame=20, target_scale=None):
    obj = bpy.data.objects.get(obj_name)
    if obj is None:
        return False
    tgt = tuple(obj.scale) if target_scale is None else tuple(target_scale)
    obj.scale = (0.001, 0.001, 0.001)
    obj.keyframe_insert(data_path="scale", frame=start_frame)
    obj.scale = tgt
    obj.keyframe_insert(data_path="scale", frame=end_frame)
    return True


def set_bezier_all():
    for obj in bpy.data.objects:
        if obj.animation_data and obj.animation_data.action:
            for fcurve in obj.animation_data.action.fcurves:
                for kf in fcurve.keyframe_points:
                    kf.interpolation = "BEZIER"
                    kf.easing = "EASE_IN_OUT"


# ──────────────────────────────────────────────────────────────────────────────
# Compositor — professional polish in one call
# ──────────────────────────────────────────────────────────────────────────────
_COMPOSITOR_PRESETS = {
    "commercial":  {"glow": True, "glow_mix": 0.15, "vignette": 0.18, "color_grade": "neutral",    "lens": 0.00},
    "cinematic":   {"glow": True, "glow_mix": 0.35, "vignette": 0.38, "color_grade": "teal_orange","lens": 0.02},
    "luxury":      {"glow": True, "glow_mix": 0.28, "vignette": 0.30, "color_grade": "warm_gold",  "lens": 0.01},
    "scifi":       {"glow": True, "glow_mix": 0.55, "vignette": 0.32, "color_grade": "cool_cyan",  "lens": 0.03},
    "minimal":     {"glow": False,"glow_mix": 0.0,  "vignette": 0.10, "color_grade": "neutral",    "lens": 0.00},
}


def compositor_polish(preset="cinematic", glow=None, vignette=None, color_grade=None, lens=None):
    cfg = dict(_COMPOSITOR_PRESETS.get(preset, _COMPOSITOR_PRESETS["cinematic"]))
    if glow is not None: cfg["glow"] = glow
    if vignette is not None: cfg["vignette"] = vignette
    if color_grade is not None: cfg["color_grade"] = color_grade
    if lens is not None: cfg["lens"] = lens

    scene = bpy.context.scene
    scene.use_nodes = True
    tree = scene.node_tree
    tree.nodes.clear()
    rl = tree.nodes.new("CompositorNodeRLayers")
    out = tree.nodes.new("CompositorNodeComposite")
    last = rl.outputs["Image"]

    if cfg["glow"]:
        glare = tree.nodes.new("CompositorNodeGlare")
        glare.glare_type = "FOG_GLOW"
        glare.quality = "HIGH"
        glare.threshold = 0.85
        try: glare.size = 8
        except Exception: pass
        glare.mix = cfg["glow_mix"] * 2 - 1  # mix is -1..1 (full src..full effect)
        tree.links.new(last, glare.inputs["Image"])
        last = glare.outputs["Image"]

    if cfg["lens"] and cfg["lens"] > 0:
        try:
            lens = tree.nodes.new("CompositorNodeLensdist")
            # Socket names vary across Blender versions ("Distort"/"Distortion");
            # index access is stable: 0=Image, 1=Distort, 2=Dispersion.
            if len(lens.inputs) >= 2:
                lens.inputs[1].default_value = float(cfg["lens"])
            if len(lens.inputs) >= 3:
                lens.inputs[2].default_value = float(cfg["lens"]) * 0.4
            tree.links.new(last, lens.inputs[0])
            last = lens.outputs[0]
        except Exception as exc:
            print(f"LENS_DISTORT_SKIP: {exc}")

    cg = cfg["color_grade"]
    if cg and cg != "neutral":
        cb = tree.nodes.new("CompositorNodeColorBalance")
        cb.correction_method = "LIFT_GAMMA_GAIN"
        if cg == "teal_orange":
            cb.lift = (1.04, 1.00, 0.94); cb.gain = (0.98, 1.00, 1.04)
        elif cg == "warm_gold":
            cb.lift = (1.05, 1.00, 0.94); cb.gain = (1.03, 1.00, 0.94)
        elif cg == "cool_cyan":
            cb.lift = (0.94, 1.00, 1.04); cb.gain = (0.96, 1.00, 1.05)
        tree.links.new(last, cb.inputs[1])
        last = cb.outputs[0]

    if cfg["vignette"] and cfg["vignette"] > 0:
        try:
            ellipse = tree.nodes.new("CompositorNodeEllipseMask")
            ellipse.width = 0.88
            ellipse.height = 0.88
            blur = tree.nodes.new("CompositorNodeBlur")
            blur.size_x = 180
            blur.size_y = 180
            tree.links.new(ellipse.outputs[0], blur.inputs[0])
            mix = tree.nodes.new("CompositorNodeMixRGB")
            mix.blend_type = "MULTIPLY"
            # Fac socket was renamed to "Factor" in some Blender versions; prefer index.
            try:
                mix.inputs[0].default_value = float(cfg["vignette"])
            except Exception:
                for k in ("Fac", "Factor"):
                    if k in mix.inputs:
                        mix.inputs[k].default_value = float(cfg["vignette"])
                        break
            tree.links.new(last, mix.inputs[1])
            tree.links.new(blur.outputs[0], mix.inputs[2])
            last = mix.outputs[0]
        except Exception as exc:
            print(f"VIGNETTE_SKIP: {exc}")

    tree.links.new(last, out.inputs["Image"])
    return True


# ──────────────────────────────────────────────────────────────────────────────
# Studio presets — full scene scaffolding in one call
# ──────────────────────────────────────────────────────────────────────────────
def apply_style(style="commercial"):
    """Full scaffold: clear, render, world, floor, lights, camera, compositor.

    Wrapped with explicit success/error markers so silent failures are impossible
    to miss in the SSE stream.
    """
    try:
        return _apply_style_impl(style)
    except Exception as exc:
        tb = traceback.format_exc()
        print(f"STYLE_ERROR: style={style} exc={exc}")
        print(f"STYLE_TRACEBACK:\n{tb}")
        raise


def _apply_style_impl(style="commercial"):
    style = style.lower()
    clear_scene()
    setup_render(engine="EEVEE_NEXT", samples=64, resolution=(1280, 720), fps=24, frame_end=120)
    setup_filmic("High Contrast", 0.0)

    if style == "commercial":
        set_world_color("#f0f0f2", strength=0.6)
        _make_cyclorama()
        three_point_rig(key_energy=450, fill_ratio=0.24, rim_ratio=0.67)
        make_camera(location=(5.0, -7.2, 3.0), focal_mm=50, dof_distance=8.8, fstop=4.0)
        setup_eevee_quality(bloom_threshold=0.95, bloom_intensity=0.25, bloom_radius=4.0)
        compositor_polish("commercial")
    elif style == "cinematic":
        set_world_color("#050508", strength=1.0)
        setup_filmic("High Contrast", -0.3)
        _make_dark_floor()
        three_point_rig(
            key_energy=700, fill_ratio=0.05, rim_ratio=0.6,
            key_pos=(-3.8, -1.5, 5.5), fill_pos=(4.0, -3.0, 1.8), rim_pos=(3.2, 4.0, 4.5),
            key_color="#fff4d8", rim_color="#ffc890", fill_color="#a0b8ff",
        )
        make_camera(location=(4.5, -7.5, 2.2), focal_mm=35, dof_distance=8.5, fstop=2.0)
        setup_eevee_quality(bloom_threshold=0.7, bloom_intensity=0.4, bloom_radius=6.0)
        compositor_polish("cinematic")
    elif style == "luxury":
        set_world_color("#100c08", strength=1.0)
        setup_filmic("High Contrast", 0.2)
        _make_marble_floor()
        three_point_rig(
            key_energy=320, fill_ratio=0.12, rim_ratio=1.56,
            key_pos=(-2.0, -2.5, 4.8), fill_pos=(4.0, -3.0, 2.0), rim_pos=(2.8, 3.5, 4.5),
            key_color="#ffe8c8", rim_color="#ffc870", fill_color="#ffeecc",
        )
        # Top light
        make_light("TopLight", "AREA", (0, 0, 5.5), (0, 0, 0), energy=180, color="#fff0dc", size=2.5)
        make_camera(location=(3.5, -6.5, 2.8), focal_mm=85, dof_distance=7.5, fstop=1.8)
        setup_eevee_quality(bloom_threshold=0.85, bloom_intensity=0.2, bloom_radius=3.0)
        compositor_polish("luxury")
    elif style == "scifi":
        set_world_color("#020208", strength=1.0)
        _make_scifi_platform()
        three_point_rig(
            key_energy=280, fill_ratio=0.21, rim_ratio=1.25,
            key_pos=(-2.5, -3.5, 3.0), fill_pos=(4.5, -1.5, 2.0), rim_pos=(3.0, 3.5, 4.0),
            key_color="#00e0ff", fill_color="#ffe0a0", rim_color="#e020ff",
        )
        # Under-glow
        make_light("UnderGlow", "AREA", (0, 0, -2.0), (math.radians(180), 0, 0),
                   energy=150, color="#00c0ff", size=3.0)
        make_camera(location=(4.2, -6.8, 2.8), focal_mm=24, dof_distance=8.0, fstop=2.8, dutch_deg=4)
        setup_eevee_quality(bloom_threshold=0.5, bloom_intensity=0.8, bloom_radius=7.0)
        compositor_polish("scifi")
    else:  # fallback / "minimal"
        set_world_color("#202024", strength=1.0)
        _make_cyclorama()
        three_point_rig()
        make_camera(location=(5, -7, 3), focal_mm=50, dof_distance=8, fstop=4)
        compositor_polish("minimal")

    obj_count = len([o for o in bpy.data.objects])
    light_count = len([o for o in bpy.data.objects if o.type == "LIGHT"])
    cam_count = len([o for o in bpy.data.objects if o.type == "CAMERA"])
    print(f"STYLE_APPLIED: {style} objects={obj_count} lights={light_count} cameras={cam_count}")
    return True


def _make_plane(name, size=1.0, location=(0, 0, 0)):
    """Create a flat quad mesh via bmesh, link to scene, return the object."""
    half = size / 2.0
    me = _mesh_from_bmesh(f"{name}_mesh",
        lambda bm: bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=half))
    obj = bpy.data.objects.new(name, me)
    obj.location = tuple(float(v) for v in location)
    _link_to_scene(obj)
    return obj


def _make_cylinder(name, radius=0.5, depth=1.0, segments=32, location=(0, 0, 0)):
    me = _mesh_from_bmesh(f"{name}_mesh",
        lambda bm: bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False,
                                         segments=segments, radius1=radius,
                                         radius2=radius, depth=depth))
    obj = bpy.data.objects.new(name, me)
    obj.location = tuple(float(v) for v in location)
    _link_to_scene(obj)
    return obj


def _make_torus(name, major_radius=0.5, minor_radius=0.15, location=(0, 0, 0)):
    me = _mesh_from_bmesh(f"{name}_mesh",
        lambda bm: _build_torus_bmesh(bm, major_radius=major_radius,
                                      minor_radius=minor_radius))
    obj = bpy.data.objects.new(name, me)
    obj.location = tuple(float(v) for v in location)
    _link_to_scene(obj)
    return obj


def _make_cyclorama():
    _make_plane("Cyclorama", size=16, location=(0, 1.5, 0))
    mat = make_pbr("CycloramaMat", base_color="#f2f2f5", roughness=0.85)
    apply_material("Cyclorama", mat)


def _make_dark_floor():
    _make_plane("DarkFloor", size=14, location=(0, 0, 0))
    mat = make_pbr("DarkFloorMat", base_color="#0a0a0c", roughness=0.6)
    apply_material("DarkFloor", mat)


def _make_marble_floor():
    _make_plane("MarbleFloor", size=12, location=(0, 0, 0))
    mat, _ = make_preset_material("marble_white", name="MarbleFloorMat")
    apply_material("MarbleFloor", mat)


def _make_scifi_platform():
    _make_cylinder("Platform", radius=1.8, depth=0.08, location=(0, 0, 0))
    mat = make_pbr("PlatformMat", base_color="#0a0a10", metallic=0.9, roughness=0.15,
                   emission_color="#0080ff", emission_strength=0.4)
    apply_material("Platform", mat)
    _make_torus("GlowRing", major_radius=1.85, minor_radius=0.02,
                location=(0, 0, -0.02))
    mat_ring = make_pbr("GlowRingMat", base_color="#00c0ff",
                        emission_color="#00e0ff", emission_strength=6.0)
    apply_material("GlowRing", mat_ring)


# ──────────────────────────────────────────────────────────────────────────────
# Primitives + modifiers
# ──────────────────────────────────────────────────────────────────────────────
# Primitive builders — all use bmesh.ops or parametric construction.
# Each entry returns a mesh datablock; EMPTY returns None (no mesh needed).
def _prim_cube(name):
    return _mesh_from_bmesh(f"{name}_mesh",
        lambda bm: bmesh.ops.create_cube(bm, size=1.0))

def _prim_cylinder(name):
    return _mesh_from_bmesh(f"{name}_mesh",
        lambda bm: bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False,
                                         segments=32, radius1=0.5, radius2=0.5, depth=1.0))

def _prim_uv_sphere(name):
    return _mesh_from_bmesh(f"{name}_mesh",
        lambda bm: bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16,
                                             radius=0.5))

def _prim_ico_sphere(name):
    return _mesh_from_bmesh(f"{name}_mesh",
        lambda bm: bmesh.ops.create_icosphere(bm, radius=0.5, subdivisions=3))

def _prim_plane(name):
    # bmesh.ops.create_grid size is half-side, so 0.5 yields a 1-unit plane
    return _mesh_from_bmesh(f"{name}_mesh",
        lambda bm: bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5))

def _prim_cone(name):
    return _mesh_from_bmesh(f"{name}_mesh",
        lambda bm: bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False,
                                         segments=32, radius1=0.5, radius2=0.0, depth=1.0))

def _prim_torus(name):
    return _mesh_from_bmesh(f"{name}_mesh",
        lambda bm: _build_torus_bmesh(bm, major_radius=0.5, minor_radius=0.15))

def _prim_monkey(name):
    return _mesh_from_bmesh(f"{name}_mesh",
        lambda bm: bmesh.ops.create_monkey(bm))


_PRIMITIVE_BUILDERS = {
    "CUBE":       _prim_cube,
    "CYLINDER":   _prim_cylinder,
    "UV_SPHERE":  _prim_uv_sphere,
    "ICO_SPHERE": _prim_ico_sphere,
    "PLANE":      _prim_plane,
    "CONE":       _prim_cone,
    "TORUS":      _prim_torus,
    "MONKEY":     _prim_monkey,
}


def _shade_smooth_data(obj, auto_smooth_deg=30.0):
    """shade_smooth without bpy.ops — set use_smooth on every polygon."""
    me = obj.data
    if me is None or not hasattr(me, "polygons"):
        return
    for poly in me.polygons:
        poly.use_smooth = True
    # Blender 4.1+ deprecated mesh.use_auto_smooth in favour of a modifier;
    # the legacy attribute still exists on older builds and is harmless if
    # present. Set it defensively.
    try:
        if hasattr(me, "use_auto_smooth"):
            me.use_auto_smooth = True
            me.auto_smooth_angle = math.radians(auto_smooth_deg)
    except Exception:
        pass


def make_object(
    name, primitive="CUBE", location=(0, 0, 0), scale=(1, 1, 1), rotation=(0, 0, 0),
    material=None, subdivision=0, shade_smooth=False, auto_smooth_deg=30.0,
):
    """Create a mesh object (or empty) WITHOUT bpy.ops — purely bpy.data + bmesh."""
    p = primitive.upper()
    if p == "EMPTY":
        obj = bpy.data.objects.new(name, None)
        obj.empty_display_type = "PLAIN_AXES"
    else:
        builder = _PRIMITIVE_BUILDERS.get(p, _PRIMITIVE_BUILDERS["CUBE"])
        mesh = builder(name)
        obj = bpy.data.objects.new(name, mesh)
    obj.location = tuple(float(v) for v in location)
    obj.scale = tuple(float(v) for v in scale)
    obj.rotation_euler = tuple(float(v) for v in rotation)
    _link_to_scene(obj)

    if material is not None:
        apply_material(name, material)
    if subdivision > 0:
        apply_subdivision(name, viewport=subdivision, render=max(subdivision, 2),
                          shade_smooth=shade_smooth, auto_smooth_deg=auto_smooth_deg)
    elif shade_smooth and p not in ("PLANE", "EMPTY"):
        _shade_smooth_data(obj, auto_smooth_deg=auto_smooth_deg)
    return obj


def apply_subdivision(obj_name, viewport=2, render=3, shade_smooth=True, auto_smooth_deg=30.0):
    """Attach a SUBSURF modifier + optionally apply smooth shading at data level."""
    obj = bpy.data.objects.get(obj_name)
    if obj is None:
        return False
    mod = obj.modifiers.new("Subdivision", "SUBSURF")
    mod.levels = int(viewport)
    mod.render_levels = int(render)
    if shade_smooth:
        _shade_smooth_data(obj, auto_smooth_deg=auto_smooth_deg)
    return True


def apply_bevel(obj_name, width=0.02, segments=3):
    """Attach a BEVEL modifier — pure bpy.data, no context needed."""
    obj = bpy.data.objects.get(obj_name)
    if obj is None:
        return False
    mod = obj.modifiers.new("Bevel", "BEVEL")
    mod.width = float(width)
    mod.segments = int(segments)
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(30)
    return True


# ──────────────────────────────────────────────────────────────────────────────
# Scene spec builder — the fast path
# ──────────────────────────────────────────────────────────────────────────────
def build_scene_from_spec(spec):
    """Public entry point with explicit error reporting."""
    try:
        return _build_scene_from_spec_impl(spec)
    except Exception as exc:
        tb = traceback.format_exc()
        print(f"BUILD_ERROR: {exc}")
        print(f"BUILD_TRACEBACK:\n{tb}")
        raise


def _build_scene_from_spec_impl(spec):
    """
    Build an entire scene from a JSON spec. Returns a report dict.

    spec = {
      "style": "cinematic",              # triggers apply_style(), optional
      "world": {"hdri_slug"|"hdri_style"|"color", "strength"},
      "render": {"engine", "samples", "resolution": [w,h], "fps", "frames"},
      "filmic": {"look", "exposure"},
      "objects": [
        {"id","primitive","location","scale","rotation_euler","material","purpose",
         "subdivision","shade_smooth"}
      ],
      "materials": [
        {"id","preset"}   or
        {"id","base_color","metallic","roughness","ior","transmission",
         "emission_color","emission_strength","sheen","clearcoat","alpha"}
      ],
      "lights": [
        {"id","type","location","rotation_euler","energy","color","size"}
      ],
      "camera": {"location","look_at","focal_mm","dof_distance","fstop","dutch_deg",
                 "track":"object_id"},
      "animation": {"camera_orbit": bool|{...}, "product_float":{obj,amp,frames},
                    "scale_in_reveal":{obj,start,end}, "bezier_all":bool},
      "compositor": {"preset": "cinematic|commercial|luxury|scifi|minimal", ...overrides}
    }
    """
    report = {"created": [], "errors": [], "warnings": []}

    # 0. Style scaffold (optional — skips individual setup calls if present)
    style = spec.get("style")
    applied_style = False
    if spec.get("scaffold", True) and style in ("commercial", "cinematic", "luxury", "scifi", "minimal"):
        apply_style(style)
        applied_style = True
        report["created"].append(f"style:{style}")
    else:
        clear_scene()

    # 1. Render settings
    r = spec.get("render", {}) or {}
    setup_render(
        engine=r.get("engine", "EEVEE_NEXT"),
        samples=int(r.get("samples", 64)),
        resolution=tuple(r.get("resolution", [1280, 720])),
        fps=int(r.get("fps", 24)),
        frame_start=int(r.get("frame_start", 1)),
        frame_end=int(r.get("frames", r.get("frame_end", 120))),
    )

    fm = spec.get("filmic") or {}
    if fm:
        setup_filmic(fm.get("look", "High Contrast"),
                     float(fm.get("exposure", 0.0)),
                     float(fm.get("gamma", 1.0)))

    # 2. World
    w = spec.get("world") or {}
    if w:
        if w.get("hdri_slug"):
            set_hdri(slug=w["hdri_slug"], resolution=w.get("hdri_resolution", "2k"),
                     strength=float(w.get("strength", 1.0)))
            report["created"].append(f"hdri:{w['hdri_slug']}")
        elif w.get("hdri_style"):
            set_hdri(style=w["hdri_style"], resolution=w.get("hdri_resolution", "2k"),
                     strength=float(w.get("strength", 1.0)))
            report["created"].append(f"hdri_style:{w['hdri_style']}")
        elif w.get("color"):
            set_world_color(w["color"], strength=float(w.get("strength", 1.0)))
            report["created"].append(f"world_color:{w['color']}")

    # 3. Materials (build first so objects can reference them)
    mat_lookup = {}
    for m in spec.get("materials") or []:
        mid = m["id"]
        preset = m.get("preset")
        if preset and preset in MATERIAL_PRESETS:
            mat, ok = make_preset_material(preset, name=mid)
        else:
            mat = make_pbr(
                mid,
                base_color=m.get("base_color", "#808080"),
                metallic=float(m.get("metallic", 0.0)),
                roughness=float(m.get("roughness", 0.5)),
                ior=float(m.get("ior", 1.45)),
                transmission=float(m.get("transmission", 0.0)),
                emission_color=m.get("emission_color", "#000000"),
                emission_strength=float(m.get("emission_strength", 0.0)),
                alpha=float(m.get("alpha", 1.0)),
                sheen=float(m.get("sheen", 0.0)),
                clearcoat=float(m.get("clearcoat", 0.0)),
                clearcoat_roughness=float(m.get("clearcoat_roughness", 0.03)),
            )
        mat_lookup[mid] = mat
        report["created"].append(f"material:{mid}")

    # 4. Objects
    for o in spec.get("objects") or []:
        oid = o["id"]
        mat_ref = o.get("material")
        mat = mat_lookup.get(mat_ref) if mat_ref else None
        if mat is None and mat_ref in MATERIAL_PRESETS:
            mat, _ = make_preset_material(mat_ref, name=f"{oid}_mat")
            mat_lookup[mat_ref] = mat
        make_object(
            name=oid,
            primitive=o.get("primitive", "CUBE"),
            location=tuple(o.get("location", [0, 0, 0])),
            scale=tuple(o.get("scale", [1, 1, 1])),
            rotation=tuple(o.get("rotation_euler", [0, 0, 0])),
            material=mat,
            subdivision=int(o.get("subdivision", 0)),
            shade_smooth=bool(o.get("shade_smooth", False)),
        )
        if o.get("bevel"):
            bv = o["bevel"]
            apply_bevel(oid, width=float(bv.get("width", 0.02)), segments=int(bv.get("segments", 3)))
        report["created"].append(f"object:{oid}")

    # 5. Additional lights (style may have created defaults; these ADD)
    for l in spec.get("lights") or []:
        make_light(
            name=l["id"],
            type=l.get("type", "AREA"),
            location=tuple(l.get("location", [0, 0, 4])),
            rotation=tuple(l.get("rotation_euler", [0, 0, 0])),
            energy=float(l.get("energy", 500)),
            color=l.get("color", "#ffffff"),
            size=float(l.get("size", 2.0)),
        )
        report["created"].append(f"light:{l['id']}")

    # 6. Camera
    c = spec.get("camera") or {}
    if c and not applied_style:
        make_camera(
            name=c.get("id", "Camera"),
            location=tuple(c.get("location", [5, -7, 3])),
            look_at=tuple(c.get("look_at", [0, 0, 0])),
            focal_mm=float(c.get("focal_mm", 50)),
            dof_distance=float(c["dof_distance"]) if c.get("dof_distance") else None,
            fstop=float(c.get("fstop", 2.8)),
            dutch_deg=float(c.get("dutch_deg", 0.0)),
        )
    elif c and applied_style:
        # override specific fields on the style-supplied camera
        cam = bpy.data.objects.get("Camera")
        if cam and c.get("location"):
            cam.location = tuple(c["location"])
        if cam and c.get("focal_mm"):
            cam.data.lens = float(c["focal_mm"])
        if cam and c.get("look_at"):
            _aim_camera(cam, tuple(c["look_at"]))

    if c.get("track"):
        track_to("Camera", c["track"])
        report["created"].append(f"track:{c['track']}")

    # 7. Animation
    a = spec.get("animation") or {}
    frames = int((spec.get("render") or {}).get("frames", 120))
    if a.get("camera_orbit"):
        cfg = a["camera_orbit"] if isinstance(a["camera_orbit"], dict) else {}
        camera_orbit(
            radius=float(cfg.get("radius", 8.0)),
            height=float(cfg.get("height", 4.0)),
            start_deg=float(cfg.get("start_deg", -90)),
            end_deg=float(cfg.get("end_deg", 90)),
            frames=int(cfg.get("frames", frames)),
            target=tuple(cfg.get("target", [0, 0, 0])),
        )
        report["created"].append("anim:camera_orbit")
    if a.get("product_float"):
        cfg = a["product_float"]
        float_animation(
            cfg.get("obj", "Product"),
            amplitude=float(cfg.get("amplitude", 0.15)),
            frames=int(cfg.get("frames", frames)),
        )
        report["created"].append("anim:float")
    if a.get("scale_in_reveal"):
        cfg = a["scale_in_reveal"]
        scale_in_reveal(
            cfg.get("obj", "Product"),
            start_frame=int(cfg.get("start_frame", 1)),
            end_frame=int(cfg.get("end_frame", 20)),
        )
        report["created"].append("anim:scale_in")
    if a.get("bezier_all", True):
        set_bezier_all()

    # 8. Compositor
    comp = spec.get("compositor")
    if comp:
        if isinstance(comp, str):
            compositor_polish(preset=comp)
        else:
            compositor_polish(**{k: v for k, v in comp.items() if k in ("preset", "glow", "vignette", "color_grade", "lens")})
        report["created"].append(f"compositor:{comp if isinstance(comp, str) else comp.get('preset','custom')}")

    return report


# ──────────────────────────────────────────────────────────────────────────────
# Typed Fix DSL — safe, bounded operations for QA-driven scene corrections.
#
# Every fix op uses bpy.data only. No bpy.ops. No transform_apply. No mesh
# mutation. If a fix fails, it returns a structured error instead of silently
# corrupting the scene. QA emits {op, args} dicts; agents NEVER write raw
# Python in the fix path.
# ──────────────────────────────────────────────────────────────────────────────

def _fix_set_light_energy(args):
    light = bpy.data.objects.get(args["light"])
    if not light or light.type != "LIGHT":
        raise ValueError(f"light not found: {args['light']}")
    light.data.energy = float(args["energy"])
    return {"light": args["light"], "energy": light.data.energy}


def _fix_set_light_color(args):
    light = bpy.data.objects.get(args["light"])
    if not light or light.type != "LIGHT":
        raise ValueError(f"light not found: {args['light']}")
    r, g, b, _ = _hex_to_rgb(args["color"])
    light.data.color = (r, g, b)
    return {"light": args["light"], "color": args["color"]}


def _fix_set_light_size(args):
    light = bpy.data.objects.get(args["light"])
    if not light or light.type != "LIGHT":
        raise ValueError(f"light not found: {args['light']}")
    if light.data.type == "AREA":
        light.data.size = float(args["size"])
    return {"light": args["light"], "size": args["size"]}


def _fix_add_light(args):
    obj = make_light(
        name=args["name"],
        type=args.get("type", "AREA"),
        location=tuple(args.get("location", [0, 0, 4])),
        rotation=tuple(args.get("rotation", [0, 0, 0])),
        energy=float(args.get("energy", 400)),
        color=args.get("color", "#ffffff"),
        size=float(args.get("size", 1.5)),
    )
    return {"added": obj.name}


def _fix_delete_object(args):
    obj = bpy.data.objects.get(args["name"])
    if not obj:
        return {"name": args["name"], "status": "already_absent"}
    bpy.data.objects.remove(obj, do_unlink=True)
    return {"deleted": args["name"]}


def _fix_move_camera(args):
    cam = bpy.data.objects.get(args.get("camera", "Camera"))
    if not cam or cam.type != "CAMERA":
        raise ValueError(f"camera not found: {args.get('camera','Camera')}")
    if "location" in args:
        cam.location = tuple(float(v) for v in args["location"])
    if "look_at" in args:
        _aim_camera(cam, tuple(args["look_at"]))
    return {"camera": cam.name, "location": tuple(cam.location),
            "rotation": tuple(cam.rotation_euler)}


def _fix_set_camera_focal(args):
    cam = bpy.data.objects.get(args.get("camera", "Camera"))
    if not cam or cam.type != "CAMERA":
        raise ValueError(f"camera not found: {args.get('camera','Camera')}")
    cam.data.lens = float(args["focal_mm"])
    return {"camera": cam.name, "focal_mm": cam.data.lens}


def _fix_set_camera_fstop(args):
    cam = bpy.data.objects.get(args.get("camera", "Camera"))
    if not cam or cam.type != "CAMERA":
        raise ValueError(f"camera not found: {args.get('camera','Camera')}")
    cam.data.dof.use_dof = True
    cam.data.dof.aperture_fstop = float(args["fstop"])
    return {"camera": cam.name, "fstop": cam.data.dof.aperture_fstop}


def _fix_set_camera_dof_distance(args):
    cam = bpy.data.objects.get(args.get("camera", "Camera"))
    if not cam or cam.type != "CAMERA":
        raise ValueError(f"camera not found: {args.get('camera','Camera')}")
    cam.data.dof.use_dof = True
    cam.data.dof.focus_distance = float(args["distance"])
    return {"camera": cam.name, "dof_distance": cam.data.dof.focus_distance}


def _fix_move_object(args):
    obj = bpy.data.objects.get(args["name"])
    if not obj:
        raise ValueError(f"object not found: {args['name']}")
    obj.location = tuple(float(v) for v in args["location"])
    return {"name": args["name"], "location": tuple(obj.location)}


def _fix_scale_object(args):
    """Object-level scale — does NOT bake into mesh data. Fully reversible."""
    obj = bpy.data.objects.get(args["name"])
    if not obj:
        raise ValueError(f"object not found: {args['name']}")
    s = args["scale"]
    if isinstance(s, (int, float)):
        obj.scale = (float(s), float(s), float(s))
    else:
        obj.scale = tuple(float(v) for v in s)
    return {"name": args["name"], "scale": tuple(obj.scale)}


def _fix_rotate_object(args):
    obj = bpy.data.objects.get(args["name"])
    if not obj:
        raise ValueError(f"object not found: {args['name']}")
    obj.rotation_euler = tuple(float(v) for v in args["rotation"])
    return {"name": args["name"], "rotation": tuple(obj.rotation_euler)}


def _fix_set_material_param(args):
    """Adjust a single PBR param on an existing material. No node recreation."""
    mat = bpy.data.materials.get(args["material"])
    if not mat or not mat.use_nodes:
        raise ValueError(f"material not found / not node-based: {args['material']}")
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        raise ValueError("material has no Principled BSDF")
    param = args["param"]
    value = args["value"]
    # Colour params come in as hex; numeric params come as float.
    if param.lower() in ("base_color", "emission_color"):
        rgba = _hex_to_rgb(value)
        # 4.x uses "Base Color", "Emission Color"
        target = "Base Color" if param.lower() == "base_color" else "Emission Color"
        _bsdf_set(bsdf, target, rgba)
    else:
        # Numeric params: metallic, roughness, ior, transmission_weight, alpha,
        # sheen_weight, coat_weight, coat_roughness, emission_strength
        name_map = {
            "metallic": "Metallic",
            "roughness": "Roughness",
            "ior": "IOR",
            "transmission": "Transmission Weight",
            "alpha": "Alpha",
            "sheen": "Sheen Weight",
            "clearcoat": "Coat Weight",
            "clearcoat_roughness": "Coat Roughness",
            "emission_strength": "Emission Strength",
        }
        target = name_map.get(param.lower(), param)
        _bsdf_set(bsdf, target, float(value))
    return {"material": args["material"], "param": param, "value": value}


def _fix_set_world_strength(args):
    world = bpy.context.scene.world
    if not world or not world.use_nodes:
        raise ValueError("no node-based world")
    bg = world.node_tree.nodes.get("Background")
    if bg is None:
        raise ValueError("world has no Background node")
    bg.inputs["Strength"].default_value = float(args["strength"])
    return {"world_strength": bg.inputs["Strength"].default_value}


def _fix_set_compositor_preset(args):
    """Re-apply a compositor preset wholesale (safe — replaces node tree)."""
    compositor_polish(preset=args.get("preset", "cinematic"),
                      glow=args.get("glow"), vignette=args.get("vignette"),
                      color_grade=args.get("color_grade"), lens=args.get("lens"))
    return {"compositor": args.get("preset", "cinematic")}


def _fix_set_active_camera(args):
    cam = bpy.data.objects.get(args["camera"])
    if not cam or cam.type != "CAMERA":
        raise ValueError(f"camera not found: {args['camera']}")
    bpy.context.scene.camera = cam
    return {"active_camera": cam.name}


def _fix_set_render_samples(args):
    scene = bpy.context.scene
    samples = int(args["samples"])
    if scene.render.engine == "CYCLES":
        scene.cycles.samples = samples
    else:
        # EEVEE — samples attr varies by version
        try:
            scene.eevee.taa_render_samples = samples
        except Exception:
            pass
    return {"engine": scene.render.engine, "samples": samples}


_FIX_OPS = {
    "set_light_energy":         _fix_set_light_energy,
    "set_light_color":          _fix_set_light_color,
    "set_light_size":           _fix_set_light_size,
    "add_light":                _fix_add_light,
    "delete_object":            _fix_delete_object,
    "move_camera":              _fix_move_camera,
    "set_camera_focal":         _fix_set_camera_focal,
    "set_camera_fstop":         _fix_set_camera_fstop,
    "set_camera_dof_distance":  _fix_set_camera_dof_distance,
    "set_active_camera":        _fix_set_active_camera,
    "move_object":              _fix_move_object,
    "scale_object":             _fix_scale_object,
    "rotate_object":            _fix_rotate_object,
    "set_material_param":       _fix_set_material_param,
    "set_world_strength":       _fix_set_world_strength,
    "set_compositor_preset":    _fix_set_compositor_preset,
    "set_render_samples":       _fix_set_render_samples,
}


FIX_OPS_HELP = sorted(_FIX_OPS.keys())


def apply_fixes(fixes):
    """
    Apply a list of typed {op, args} fixes. Returns a structured report with
    per-op success/failure. NEVER calls bpy.ops. NEVER mutates mesh data.
    Safe to call repeatedly — each op is idempotent and reversible.

    Example:
        br.apply_fixes([
            {"op": "set_light_energy", "args": {"light": "KeyLight", "energy": 800}},
            {"op": "move_camera", "args": {"location": [4,-5,2.5], "look_at": [0,0,0.5]}},
        ])
    """
    report = {"applied": [], "failed": []}
    for fix in (fixes or []):
        op = fix.get("op") or fix.get("action")
        args = fix.get("args") or {}
        fn = _FIX_OPS.get(op)
        if fn is None:
            report["failed"].append({"op": op, "reason": f"unknown op — valid: {FIX_OPS_HELP}"})
            continue
        try:
            result = fn(args)
            report["applied"].append({"op": op, "result": result})
        except Exception as exc:
            report["failed"].append({"op": op, "args": args, "reason": str(exc)})
    print(f"FIXES_APPLIED: {len(report['applied'])}/{len(report['applied'])+len(report['failed'])}")
    if report["failed"]:
        for f in report["failed"]:
            print(f"FIX_FAILED: {f}")
    return report


# ──────────────────────────────────────────────────────────────────────────────
# Inspection + QA helpers
# ──────────────────────────────────────────────────────────────────────────────
def scene_summary():
    scene = bpy.context.scene
    return {
        "objects": [o.name for o in bpy.data.objects],
        "meshes":  [m.name for m in bpy.data.meshes],
        "materials": [m.name for m in bpy.data.materials],
        "lights":  [{"name": o.name, "type": o.data.type, "energy": o.data.energy,
                     "color": tuple(o.data.color)}
                    for o in bpy.data.objects if o.type == "LIGHT"],
        "cameras": [{"name": o.name, "lens": o.data.lens,
                     "location": tuple(round(v, 3) for v in o.location)}
                    for o in bpy.data.objects if o.type == "CAMERA"],
        "active_camera": scene.camera.name if scene.camera else None,
        "frame_range": (scene.frame_start, scene.frame_end),
        "fps": scene.render.fps,
        "engine": scene.render.engine,
        "resolution": (scene.render.resolution_x, scene.render.resolution_y),
        "view_transform": scene.view_settings.view_transform,
    }


def qa_checklist():
    """Quick self-diagnosis — returns machine-readable issues to fix."""
    scene = bpy.context.scene
    issues = []
    lights = [o for o in bpy.data.objects if o.type == "LIGHT"]
    if not lights:
        issues.append({"axis": "lighting", "severity": "critical", "msg": "no lights in scene"})
    else:
        total_energy = sum(l.data.energy for l in lights)
        if total_energy < 50:
            issues.append({"axis": "lighting", "severity": "critical",
                           "msg": f"total light energy very low ({total_energy:.0f}W)"})
    if not scene.camera:
        issues.append({"axis": "composition", "severity": "critical", "msg": "no active camera"})
    grey_defaults = []
    for o in bpy.data.objects:
        if o.type != "MESH": continue
        if not o.data.materials:
            grey_defaults.append(o.name)
    if grey_defaults:
        issues.append({"axis": "materials", "severity": "high",
                       "msg": f"objects without material: {grey_defaults[:5]}"})
    # Below-ground check
    for o in bpy.data.objects:
        if o.type == "MESH" and o.location.z < -0.5 and o.name.lower() not in ("floor", "ground", "cyclorama"):
            issues.append({"axis": "geometry", "severity": "medium",
                           "msg": f"{o.name} below floor (z={o.location.z:.2f})"})
    return issues


# ──────────────────────────────────────────────────────────────────────────────
# Namespace export — agents call br.make_pbr(), br.build_scene_from_spec() ...
# ──────────────────────────────────────────────────────────────────────────────
br = SimpleNamespace(
    # constants
    MATERIAL_PRESETS=MATERIAL_PRESETS,
    HDRI_REGISTRY=HDRI_REGISTRY,
    # utilities
    hex_to_rgb=_hex_to_rgb,
    clear_scene=clear_scene,
    setup_render=setup_render,
    setup_filmic=setup_filmic,
    setup_eevee_quality=setup_eevee_quality,
    # materials
    make_pbr=make_pbr,
    make_preset_material=make_preset_material,
    apply_material=apply_material,
    # lights
    make_light=make_light,
    three_point_rig=three_point_rig,
    # world + hdri
    set_hdri=set_hdri,
    set_world_color=set_world_color,
    # camera
    make_camera=make_camera,
    track_to=track_to,
    # animation
    camera_orbit=camera_orbit,
    float_animation=float_animation,
    scale_in_reveal=scale_in_reveal,
    set_bezier_all=set_bezier_all,
    # compositor
    compositor_polish=compositor_polish,
    # style presets
    apply_style=apply_style,
    # primitives + modifiers
    make_object=make_object,
    apply_subdivision=apply_subdivision,
    apply_bevel=apply_bevel,
    # scene builder
    build_scene_from_spec=build_scene_from_spec,
    # typed fix DSL
    apply_fixes=apply_fixes,
    FIX_OPS=FIX_OPS_HELP,
    # inspection
    scene_summary=scene_summary,
    qa_checklist=qa_checklist,
)

# Expose to the module-global scope so agents can call br.xxx() directly
import builtins as _builtins
_builtins.br = br

br.__version__ = "v4"
print("BPY_RUNTIME_LOADED:v4")
print("Material presets:", len(MATERIAL_PRESETS))
print("HDRI registry styles:", list(HDRI_REGISTRY.keys()))
'''

RUNTIME_VERSION = "v4"


def get_runtime_source() -> str:
    """Return the Python source to exec() inside Blender at session start."""
    return BPY_RUNTIME_SOURCE


def install_marker_code() -> str:
    """
    Check if bpy_runtime is loaded AND matches the current version. A version
    mismatch means Blender is running an older copy (from before a bpy_runtime
    code change) and should be re-injected.
    """
    return (
        "import builtins\n"
        f"_needed = '{RUNTIME_VERSION}'\n"
        "_br = getattr(builtins, 'br', None)\n"
        "if _br is None:\n"
        "    print('RUNTIME_MISSING')\n"
        "elif getattr(_br, '__version__', 'v0') != _needed:\n"
        "    print('RUNTIME_OUTDATED:' + getattr(_br, '__version__', 'v0'))\n"
        "else:\n"
        "    print('RUNTIME_PRESENT:' + _needed)\n"
    )
