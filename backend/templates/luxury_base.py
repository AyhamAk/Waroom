"""
Luxury Base Template — marble floor, warm amber rim, 85mm portrait camera, ultra-shallow DOF.
Style: opulent, warm, premium. Think Rolex, Chanel, Porsche product photography.
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
scene.view_settings.exposure = 0.2
scene.view_settings.gamma = 1.0

# ── 3. World — deep warm charcoal ───────────────────────────────────────────
world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
bg_node = world.node_tree.nodes.get("Background")
if bg_node:
    bg_node.inputs["Color"].default_value = (0.06, 0.05, 0.04, 1.0)
    bg_node.inputs["Strength"].default_value = 1.0

# ── 4. Marble floor — white with grey veining simulation ─────────────────────
bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 0, 0))
floor = bpy.context.active_object
floor.name = "MarbleFloor"
mat_marble = bpy.data.materials.new(name="MarbleMat")
mat_marble.use_nodes = True
nodes_m = mat_marble.node_tree.nodes
links_m = mat_marble.node_tree.links
nodes_m.clear()

# Marble shader using noise + color ramp for veining
output_m = nodes_m.new('ShaderNodeOutputMaterial')
bsdf_m = nodes_m.new('ShaderNodeBsdfPrincipled')
noise = nodes_m.new('ShaderNodeTexNoise')
color_ramp = nodes_m.new('ShaderNodeValToRGB')
mix_rgb = nodes_m.new('ShaderNodeMixRGB')

noise.inputs['Scale'].default_value = 3.5
noise.inputs['Detail'].default_value = 8.0
noise.inputs['Roughness'].default_value = 0.6
noise.inputs['Distortion'].default_value = 0.4

# Marble: white base with grey veins
color_ramp.color_ramp.elements[0].color = (0.85, 0.83, 0.80, 1.0)  # warm white
color_ramp.color_ramp.elements[1].color = (0.55, 0.52, 0.50, 1.0)  # grey vein
color_ramp.color_ramp.elements[0].position = 0.3
color_ramp.color_ramp.elements[1].position = 0.7

links_m.new(noise.outputs['Fac'], color_ramp.inputs['Fac'])
links_m.new(color_ramp.outputs['Color'], bsdf_m.inputs['Base Color'])

bsdf_m.inputs['Roughness'].default_value = 0.05
bsdf_m.inputs['Metallic'].default_value = 0.0
try:
    bsdf_m.inputs['Specular IOR Level'].default_value = 0.6
except (KeyError, TypeError):
    pass

links_m.new(bsdf_m.outputs['BSDF'], output_m.inputs['Surface'])
floor.data.materials.append(mat_marble)

# ── 5. Luxury warm lighting ──────────────────────────────────────────────────

# KEY — warm soft light, slightly overhead, left-center
bpy.ops.object.light_add(type='AREA', location=(-2.0, -2.5, 4.8))
key = bpy.context.active_object
key.name = "KeyLight"
key.data.energy = 320
key.data.color = (1.0, 0.92, 0.78)
key.data.size = 2.2
key.rotation_euler = (math.radians(48), 0, math.radians(-25))

# RIM — strong warm amber, the signature luxury look, upper-back-right
bpy.ops.object.light_add(type='AREA', location=(2.8, 3.5, 4.5))
rim = bpy.context.active_object
rim.name = "AmberRim"
rim.data.energy = 500
rim.data.color = (1.0, 0.82, 0.42)
rim.data.size = 0.8
rim.rotation_euler = (math.radians(60), 0, math.radians(152))

# TOP LIGHT — clean overhead, enhances product surface quality
bpy.ops.object.light_add(type='AREA', location=(0, 0, 5.5))
top = bpy.context.active_object
top.name = "TopLight"
top.data.energy = 180
top.data.color = (1.0, 0.95, 0.88)
top.data.size = 2.5
top.rotation_euler = (0, 0, 0)

# FLOOR REFLECTION — catches in the marble, adds depth
bpy.ops.object.light_add(type='AREA', location=(0, 0, -1.2))
floor_light = bpy.context.active_object
floor_light.name = "FloorReflection"
floor_light.data.energy = 40
floor_light.data.color = (1.0, 0.94, 0.82)
floor_light.data.size = 6.0
floor_light.rotation_euler = (math.radians(180), 0, 0)

# ── 6. Camera — 85mm portrait, extreme shallow DOF ──────────────────────────
bpy.ops.object.camera_add(location=(3.5, -6.5, 2.8))
cam = bpy.context.active_object
cam.name = "Camera"
cam.data.lens = 85.0
cam.data.clip_start = 0.1
cam.data.clip_end = 500.0
cam.data.dof.use_dof = True
cam.data.dof.focus_distance = 7.5
cam.data.dof.aperture_fstop = 1.8
constraint = cam.constraints.new(type='TRACK_TO')
constraint.target = floor
constraint.track_axis = 'TRACK_NEGATIVE_Z'
constraint.up_axis = 'UP_Y'
scene.camera = cam

# ── 7. EEVEE quality — SSR for marble reflections ───────────────────────────
eevee = scene.eevee
try:
    eevee.use_bloom = True
    eevee.bloom_threshold = 0.85
    eevee.bloom_intensity = 0.2
    eevee.bloom_radius = 3.0
except AttributeError:
    pass
try:
    eevee.use_ssr = True
    eevee.ssr_quality = 0.75
    eevee.ssr_max_roughness = 0.15
except AttributeError:
    pass
try:
    eevee.use_gtao = True
    eevee.gtao_distance = 0.2
except AttributeError:
    pass

print("LUXURY_BASE_READY")
print("Objects:", [o.name for o in bpy.data.objects])
print("Camera:", scene.camera.name if scene.camera else "NONE")
print("Next: add product at (0,0,0), reassign TRACK_TO to product object")
