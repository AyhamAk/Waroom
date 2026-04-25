"""
Commercial Base Template — white cyclorama studio, 4-light rig, 50mm camera.
Style: clean, bright, aspirational. Think Apple product photography.
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
scene.view_settings.exposure = 0.0
scene.view_settings.gamma = 1.0

# ── 3. World — soft warm off-white ──────────────────────────────────────────
world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
bg_node = world.node_tree.nodes.get("Background")
if bg_node:
    bg_node.inputs["Color"].default_value = (0.94, 0.94, 0.96, 1.0)
    bg_node.inputs["Strength"].default_value = 0.6

# ── 4. Cyclorama floor — seamless white sweep ────────────────────────────────
bpy.ops.mesh.primitive_plane_add(size=16, location=(0, 1.5, 0))
floor = bpy.context.active_object
floor.name = "Cyclorama"
mat_cyc = bpy.data.materials.new(name="CycloramaMat")
mat_cyc.use_nodes = True
bsdf_cyc = mat_cyc.node_tree.nodes.get("Principled BSDF")
bsdf_cyc.inputs["Base Color"].default_value = (0.95, 0.95, 0.97, 1.0)
bsdf_cyc.inputs["Roughness"].default_value = 0.85
bsdf_cyc.inputs["Metallic"].default_value = 0.0
floor.data.materials.append(mat_cyc)

# ── 5. Four-light rig ────────────────────────────────────────────────────────

# KEY — warm, upper-left, creates primary shape and shadow
bpy.ops.object.light_add(type='AREA', location=(-3.5, -2.0, 4.8))
key = bpy.context.active_object
key.name = "KeyLight"
key.data.energy = 450
key.data.color = (1.0, 0.96, 0.88)
key.data.size = 1.6
key.rotation_euler = (math.radians(50), 0, math.radians(-35))

# FILL — cool, right side, softens shadows without flattening
bpy.ops.object.light_add(type='AREA', location=(3.8, -1.8, 2.5))
fill = bpy.context.active_object
fill.name = "FillLight"
fill.data.energy = 110
fill.data.color = (0.88, 0.92, 1.0)
fill.data.size = 3.2
fill.rotation_euler = (math.radians(38), 0, math.radians(44))

# RIM — warm gold, upper-back-right, separates product from bg
bpy.ops.object.light_add(type='AREA', location=(2.5, 3.8, 4.2))
rim = bpy.context.active_object
rim.name = "RimLight"
rim.data.energy = 300
rim.data.color = (1.0, 0.92, 0.78)
rim.data.size = 1.0
rim.rotation_euler = (math.radians(58), 0, math.radians(148))

# BOUNCE — subtle under-fill simulating light bouncing off the floor
bpy.ops.object.light_add(type='AREA', location=(0, 0, -1.5))
bounce = bpy.context.active_object
bounce.name = "BounceFill"
bounce.data.energy = 55
bounce.data.color = (1.0, 0.97, 0.93)
bounce.data.size = 5.0
bounce.rotation_euler = (math.radians(180), 0, 0)

# ── 6. Camera — 50mm, slight low angle ──────────────────────────────────────
bpy.ops.object.camera_add(location=(5.0, -7.2, 3.0))
cam = bpy.context.active_object
cam.name = "Camera"
cam.data.lens = 50.0
cam.data.clip_start = 0.1
cam.data.clip_end = 500.0
cam.data.dof.use_dof = True
cam.data.dof.focus_distance = 8.8
cam.data.dof.aperture_fstop = 4.0
constraint = cam.constraints.new(type='TRACK_TO')
constraint.target = floor
constraint.track_axis = 'TRACK_NEGATIVE_Z'
constraint.up_axis = 'UP_Y'
scene.camera = cam

# ── 7. EEVEE quality ─────────────────────────────────────────────────────────
eevee = scene.eevee
try:
    eevee.use_bloom = True
    eevee.bloom_threshold = 0.95
    eevee.bloom_intensity = 0.25
    eevee.bloom_radius = 4.0
except AttributeError:
    pass
try:
    eevee.use_ssr = True
    eevee.ssr_quality = 0.5
except AttributeError:
    pass
try:
    eevee.use_gtao = True
    eevee.gtao_distance = 0.25
except AttributeError:
    pass

print("COMMERCIAL_BASE_READY")
print("Objects:", [o.name for o in bpy.data.objects])
print("Camera:", scene.camera.name if scene.camera else "NONE")
print("Next: add product at (0,0,0), reassign TRACK_TO to product object")
