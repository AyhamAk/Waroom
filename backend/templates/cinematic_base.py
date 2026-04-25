"""
Cinematic Base Template — dark moody studio, dramatic single key + strong rim, 35mm camera.
Style: atmospheric, high-contrast, premium. Think perfume or luxury car advertising.
Execute this FIRST, then add product geometry at (0, 0, 0).
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
scene.view_settings.exposure = -0.3
scene.view_settings.gamma = 1.0

# ── 3. World — near black, very subtle deep navy ────────────────────────────
world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
bg_node = world.node_tree.nodes.get("Background")
if bg_node:
    bg_node.inputs["Color"].default_value = (0.02, 0.02, 0.04, 1.0)
    bg_node.inputs["Strength"].default_value = 1.0

# ── 4. Dark matte floor ──────────────────────────────────────────────────────
bpy.ops.mesh.primitive_plane_add(size=14, location=(0, 0, 0))
floor = bpy.context.active_object
floor.name = "DarkFloor"
mat_floor = bpy.data.materials.new(name="DarkFloorMat")
mat_floor.use_nodes = True
bsdf_floor = mat_floor.node_tree.nodes.get("Principled BSDF")
bsdf_floor.inputs["Base Color"].default_value = (0.04, 0.04, 0.05, 1.0)
bsdf_floor.inputs["Roughness"].default_value = 0.6
bsdf_floor.inputs["Metallic"].default_value = 0.0
floor.data.materials.append(mat_floor)

# ── 5. Dramatic two-light setup ──────────────────────────────────────────────

# KEY — sharp, intense, upper-left, creates dramatic shadow fall
bpy.ops.object.light_add(type='AREA', location=(-3.8, -1.5, 5.5))
key = bpy.context.active_object
key.name = "KeyLight"
key.data.energy = 700
key.data.color = (1.0, 0.95, 0.85)
key.data.size = 0.9
key.rotation_euler = (math.radians(55), 0, math.radians(-32))

# RIM — strong warm-orange separation, upper-back-right
bpy.ops.object.light_add(type='AREA', location=(3.2, 4.0, 4.5))
rim = bpy.context.active_object
rim.name = "RimLight"
rim.data.energy = 420
rim.data.color = (1.0, 0.82, 0.55)
rim.data.size = 0.8
rim.rotation_euler = (math.radians(62), 0, math.radians(152))

# SUBTLE FILL — barely-visible, keeps shadow areas from pure black
bpy.ops.object.light_add(type='AREA', location=(4.0, -3.0, 1.8))
fill = bpy.context.active_object
fill.name = "SubtleFill"
fill.data.energy = 35
fill.data.color = (0.6, 0.7, 1.0)
fill.data.size = 4.0
fill.rotation_euler = (math.radians(30), 0, math.radians(50))

# ── 6. Camera — 35mm, slightly low, shallow DOF ──────────────────────────────
bpy.ops.object.camera_add(location=(4.5, -7.5, 2.2))
cam = bpy.context.active_object
cam.name = "Camera"
cam.data.lens = 35.0
cam.data.clip_start = 0.1
cam.data.clip_end = 500.0
cam.data.dof.use_dof = True
cam.data.dof.focus_distance = 8.5
cam.data.dof.aperture_fstop = 2.0
constraint = cam.constraints.new(type='TRACK_TO')
constraint.target = floor
constraint.track_axis = 'TRACK_NEGATIVE_Z'
constraint.up_axis = 'UP_Y'
scene.camera = cam

# ── 7. EEVEE quality ─────────────────────────────────────────────────────────
eevee = scene.eevee
try:
    eevee.use_bloom = True
    eevee.bloom_threshold = 0.7
    eevee.bloom_intensity = 0.4
    eevee.bloom_radius = 6.0
except AttributeError:
    pass
try:
    eevee.use_gtao = True
    eevee.gtao_distance = 0.3
except AttributeError:
    pass

print("CINEMATIC_BASE_READY")
print("Objects:", [o.name for o in bpy.data.objects])
print("Camera:", scene.camera.name if scene.camera else "NONE")
print("Next: add product at (0,0,0), reassign TRACK_TO to product object")
