import bpy
import random
import math
import os

# Clear existing scene
bpy.ops.wm.read_factory_settings(use_empty=True)

scene = bpy.context.scene

# Set render settings
scene.render.engine = 'EEVEE'
scene.render.resolution_x = 800
scene.render.resolution_y = 600
scene.render.image_settings.file_format = 'PNG'

# Helper function to create simple materials
def create_material(name, color):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs['Base Color'].default_value = color
    return mat

mat_ground = create_material("GroundMat", (0.1, 0.4, 0.1, 1.0))
mat_road = create_material("RoadMat", (0.05, 0.05, 0.05, 1.0))
mat_bldg = create_material("BuildingMat", (0.7, 0.7, 0.7, 1.0))

# Create Ground
bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, 0))
ground = bpy.context.active_object
ground.data.materials.append(mat_ground)

# Create Road
bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, 0.01))
road = bpy.context.active_object
road.scale = (1.0, 0.15, 1.0)
road.data.materials.append(mat_road)

# Create Buildings (4 to 8)
num_buildings = random.randint(4, 8)
for i in range(num_buildings):
    height = random.uniform(2.0, 8.0)
    width = random.uniform(1.0, 2.5)
    depth = random.uniform(1.0, 2.5)
    
    # Place along the X axis, offset on Y to be beside the road
    x_pos = random.uniform(-10.0, 10.0)
    y_dir = 1 if random.random() > 0.5 else -1
    y_pos = y_dir * (2.5 + random.uniform(0.5, 3.0))
    z_pos = height / 2.0
    
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x_pos, y_pos, z_pos))
    bldg = bpy.context.active_object
    bldg.scale = (width, depth, height)
    bldg.data.materials.append(mat_bldg)

# Create Sun Light
bpy.ops.object.light_add(type='SUN', location=(10, 5, 15))
sun = bpy.context.active_object
sun.data.energy = 3.0
sun.rotation_euler = (math.radians(45), math.radians(15), math.radians(45))

# Create Camera
bpy.ops.object.camera_add(location=(15, -18, 12))
cam = bpy.context.active_object
scene.camera = cam

# Aim Camera at Center
bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 2))
target = bpy.context.active_object
track_constraint = cam.constraints.new(type='TRACK_TO')
track_constraint.target = target
track_constraint.track_axis = 'TRACK_NEGATIVE_Z'
track_constraint.up_axis = 'UP_Y'

# Save the scene
blend_path = os.path.abspath("scene.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend_path)

# Render the preview image
render_path = os.path.abspath("preview.png")
scene.render.filepath = render_path
bpy.ops.render.render(write_still=True)
