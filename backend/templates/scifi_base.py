"""
Sci-Fi Base Template — void black environment, neon cyan + purple lighting, floating platform.
Style: futuristic, glowing, holographic. Think product reveal from the future.
Execute this FIRST, then add product geometry at (0, 0, 0.15) (above platform).
"""
import bpy
import math

# ── 1. Full scene reset ──────────────────────────────────────────────────────
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for mat in list(bpy.data.materials):
    bpy.data.materials.remove(mat)
for mesh in list(bpy.data.meshes):
    bpy.data.meshes.remove(mesh)
for img in list(bpy.data.images):
    if img.users == 0:
        bpy.data.images.remove(img)

# ── 2. Render settings ───────────────────────────────────────────────────────
scene = bpy.context.scene
try:
    scene.render.engine = 'BLENDER_EEVEE_NEXT'
except Exception:
    scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.fps = 24
scene.frame_start = 1
scene.frame_end = 120
scene.view_settings.view_transform = 'Filmic'
scene.view_settings.look = 'High Contrast'
scene.view_settings.exposure = 0.0
scene.view_settings.gamma = 1.0

# ── 3. World — pure void with faint blue-purple gradient ────────────────────
world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
bg_node = world.node_tree.nodes.get("Background")
if bg_node:
    bg_node.inputs["Color"].default_value = (0.01, 0.01, 0.03, 1.0)
    bg_node.inputs["Strength"].default_value = 1.0

# ── 4. Floating platform ─────────────────────────────────────────────────────
bpy.ops.mesh.primitive_cylinder_add(radius=1.8, depth=0.08, location=(0, 0, 0))
platform = bpy.context.active_object
platform.name = "Platform"
mat_plat = bpy.data.materials.new(name="PlatformMat")
mat_plat.use_nodes = True
nodes_p = mat_plat.node_tree.nodes
bsdf_p = nodes_p.get("Principled BSDF")
bsdf_p.inputs["Base Color"].default_value = (0.05, 0.05, 0.08, 1.0)
bsdf_p.inputs["Metallic"].default_value = 0.9
bsdf_p.inputs["Roughness"].default_value = 0.15
# Subtle cyan emission on platform edge — glow effect
bsdf_p.inputs["Emission Color"].default_value = (0.0, 0.7, 1.0, 1.0)
bsdf_p.inputs["Emission Strength"].default_value = 0.4
platform.data.materials.append(mat_plat)

# Thin glowing ring under the platform
bpy.ops.mesh.primitive_torus_add(
    major_radius=1.85, minor_radius=0.02, location=(0, 0, -0.02)
)
ring = bpy.context.active_object
ring.name = "GlowRing"
mat_ring = bpy.data.materials.new(name="GlowRingMat")
mat_ring.use_nodes = True
bsdf_ring = mat_ring.node_tree.nodes.get("Principled BSDF")
bsdf_ring.inputs["Base Color"].default_value = (0.0, 0.8, 1.0, 1.0)
bsdf_ring.inputs["Emission Color"].default_value = (0.0, 0.8, 1.0, 1.0)
bsdf_ring.inputs["Emission Strength"].default_value = 5.0
ring.data.materials.append(mat_ring)

# ── 5. Neon lighting ─────────────────────────────────────────────────────────

# MAIN — cyan key from slightly above-front
bpy.ops.object.light_add(type='AREA', location=(-2.5, -3.5, 3.0))
key = bpy.context.active_object
key.name = "CyanKey"
key.data.energy = 280
key.data.color = (0.0, 0.85, 1.0)
key.data.size = 2.0
key.rotation_euler = (math.radians(48), 0, math.radians(-25))

# RIM — purple/magenta from upper-back
bpy.ops.object.light_add(type='AREA', location=(3.0, 3.5, 4.0))
rim = bpy.context.active_object
rim.name = "PurpleRim"
rim.data.energy = 350
rim.data.color = (0.85, 0.1, 1.0)
rim.data.size = 1.2
rim.rotation_euler = (math.radians(56), 0, math.radians(148))

# UNDER-GLOW — cyan from below, through the platform
bpy.ops.object.light_add(type='AREA', location=(0, 0, -2.0))
under = bpy.context.active_object
under.name = "UnderGlow"
under.data.energy = 150
under.data.color = (0.0, 0.7, 1.0)
under.data.size = 3.0
under.rotation_euler = (math.radians(180), 0, 0)

# SIDE ACCENT — faint warm fill to break pure blue monochrome
bpy.ops.object.light_add(type='AREA', location=(4.5, -1.5, 2.0))
accent = bpy.context.active_object
accent.name = "WarmAccent"
accent.data.energy = 60
accent.data.color = (1.0, 0.9, 0.6)
accent.data.size = 2.5
accent.rotation_euler = (math.radians(35), 0, math.radians(55))

# ── 6. Camera — 24mm wide, slight dutch tilt ────────────────────────────────
bpy.ops.object.camera_add(location=(4.2, -6.8, 2.8))
cam = bpy.context.active_object
cam.name = "Camera"
cam.data.lens = 24.0
cam.data.clip_start = 0.1
cam.data.clip_end = 500.0
cam.data.dof.use_dof = True
cam.data.dof.focus_distance = 8.0
cam.data.dof.aperture_fstop = 2.8
# Subtle dutch tilt
cam.rotation_euler[2] = math.radians(4)
constraint = cam.constraints.new(type='TRACK_TO')
constraint.target = platform
constraint.track_axis = 'TRACK_NEGATIVE_Z'
constraint.up_axis = 'UP_Y'
scene.camera = cam

# ── 7. EEVEE quality with bloom for glow ────────────────────────────────────
eevee = scene.eevee
try:
    eevee.use_bloom = True
    eevee.bloom_threshold = 0.5
    eevee.bloom_intensity = 0.8
    eevee.bloom_radius = 7.0
except AttributeError:
    pass
try:
    eevee.use_gtao = True
    eevee.gtao_distance = 0.2
except AttributeError:
    pass

print("SCIFI_BASE_READY")
print("Objects:", [o.name for o in bpy.data.objects])
print("Camera:", scene.camera.name if scene.camera else "NONE")
print("Next: add product at (0,0,0.15) above platform, reassign TRACK_TO to product object")
