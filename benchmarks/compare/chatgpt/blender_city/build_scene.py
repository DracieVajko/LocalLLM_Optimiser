import bpy
import math
import os
import random
from mathutils import Vector

# ------------------------------------------------------------
# LOW-POLY CITY GENERATOR
# Creates a simple city, saves scene.blend, then renders
# exactly one still image named preview.png.
# ------------------------------------------------------------

random.seed(12)

# Output directory: Blender's current working directory
OUTPUT_DIR = os.getcwd()
BLEND_PATH = os.path.join(OUTPUT_DIR, "scene.blend")
PREVIEW_PATH = os.path.join(OUTPUT_DIR, "preview.png")

# ------------------------------------------------------------
# RESET SCENE
# ------------------------------------------------------------

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

for datablocks in (
    bpy.data.meshes,
    bpy.data.curves,
    bpy.data.materials,
    bpy.data.cameras,
    bpy.data.lights,
):
    for datablock in datablocks:
        if datablock.users == 0:
            datablocks.remove(datablock)

scene = bpy.context.scene

# ------------------------------------------------------------
# MATERIALS
# ------------------------------------------------------------

def make_material(name, color, roughness=0.85):
    material = bpy.data.materials.new(name=name)
    material.diffuse_color = (*color, 1.0)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    return material


grass_mat = make_material("Grass Green", (0.28, 0.52, 0.25))
road_mat = make_material("Road Asphalt", (0.12, 0.14, 0.17))
sidewalk_mat = make_material("Sidewalk", (0.55, 0.55, 0.51))
line_mat = make_material("Road Markings", (0.95, 0.85, 0.58))

building_mats = [
    make_material("Warm Cream", (0.78, 0.64, 0.46)),
    make_material("Terracotta", (0.68, 0.31, 0.23)),
    make_material("Pastel Blue", (0.35, 0.55, 0.68)),
    make_material("Muted Yellow", (0.82, 0.70, 0.39)),
    make_material("Concrete Gray", (0.52, 0.55, 0.57)),
    make_material("Sage Green", (0.42, 0.58, 0.43)),
]

window_mats = [
    make_material("Dark Blue Glass", (0.10, 0.22, 0.30)),
    make_material("Light Blue Glass", (0.35, 0.58, 0.68)),
]

roof_mat = make_material("Roof Dark Gray", (0.20, 0.22, 0.24))

# ------------------------------------------------------------
# OBJECT HELPERS
# ------------------------------------------------------------

def add_cube(name, location, scale, material, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = scale
    bpy.ops.object.transform_apply(
        location=False,
        rotation=False,
        scale=True
    )

    if material:
        obj.data.materials.append(material)

    if bevel > 0:
        modifier = obj.modifiers.new("Small Edge Bevel", "BEVEL")
        modifier.width = bevel
        modifier.segments = 1

        obj.modifiers.new("Weighted Corner Normals", "WEIGHTED_NORMAL")

    return obj


def add_building_windows(x, y, width, depth, height, material):
    """Add simple small cube windows to the front and side faces."""

    window_width = 0.22
    window_height = 0.30
    window_depth = 0.045

    floors = max(1, int(height / 1.0))
    columns = max(1, int(width / 0.7))

    # Front-facing windows (toward the camera at negative Y)
    for floor in range(floors):
        z = 0.55 + floor * 0.95
        if z + window_height / 2 >= height:
            continue

        for column in range(columns):
            x_offset = (
                -width / 2
                + (column + 1) * width / (columns + 1)
            )

            add_cube(
                "Front Window",
                (x + x_offset, y - depth / 2 - 0.025, z),
                (window_width, window_depth, window_height),
                random.choice(window_mats),
            )

    # A few windows on the right side
    side_columns = max(1, int(depth / 0.8))

    for floor in range(floors):
        z = 0.55 + floor * 0.95
        if z + window_height / 2 >= height:
            continue

        for column in range(side_columns):
            y_offset = (
                -depth / 2
                + (column + 1) * depth / (side_columns + 1)
            )

            add_cube(
                "Side Window",
                (x + width / 2 + 0.025, y + y_offset, z),
                (window_depth, window_width, window_height),
                random.choice(window_mats),
            )


def add_building(name, x, y, width, depth, height, material):
    add_cube(
        name,
        (x, y, height / 2),
        (width, depth, height),
        material,
        bevel=0.035,
    )

    # Flat rooftop detail
    add_cube(
        name + " Roof",
        (x, y, height + 0.06),
        (width + 0.08, depth + 0.08, 0.12),
        roof_mat,
    )

    # Small rooftop utility block
    if height > 3.5:
        add_cube(
            name + " Rooftop Structure",
            (x + width * 0.22, y, height + 0.28),
            (width * 0.30, depth * 0.30, 0.38),
            material,
        )

    add_building_windows(x, y, width, depth, height, material)


# ------------------------------------------------------------
# GROUND AND ROAD
# ------------------------------------------------------------

add_cube(
    "Large Grass Ground",
    (0, 0, -0.18),
    (24, 22, 0.35),
    grass_mat,
)

# Main road running horizontally through the city
add_cube(
    "Main Asphalt Road",
    (0, -3.6, 0.015),
    (24, 3.3, 0.08),
    road_mat,
)

# Sidewalks alongside the road
add_cube(
    "Front Sidewalk",
    (0, -5.42, 0.035),
    (24, 0.35, 0.12),
    sidewalk_mat,
)

add_cube(
    "Back Sidewalk",
    (0, -1.78, 0.035),
    (24, 0.35, 0.12),
    sidewalk_mat,
)

# Dashed road center markings
for x in range(-10, 12, 2):
    add_cube(
        "Road Center Line",
        (x, -3.6, 0.065),
        (1.0, 0.09, 0.025),
        line_mat,
    )

# ------------------------------------------------------------
# CITY BUILDINGS
# Six buildings with varied heights and proportions.
# ------------------------------------------------------------

building_data = [
    ("Building 1", -8.0, 2.2, 3.0, 3.0, 3.8, 0),
    ("Building 2", -4.0, 3.2, 2.8, 3.2, 6.0, 2),
    ("Building 3", 0.0, 2.5, 3.2, 3.0, 4.5, 1),
    ("Building 4", 4.2, 3.0, 3.0, 3.2, 7.0, 4),
    ("Building 5", 8.0, 2.0, 2.8, 3.0, 5.2, 5),
    ("Building 6", -1.5, 7.2, 3.0, 3.0, 3.2, 3),
]

for name, x, y, width, depth, height, material_index in building_data:
    add_building(
        name,
        x,
        y,
        width,
        depth,
        height,
        building_mats[material_index],
    )

# Small decorative trees made from low-poly cubes and cones
trunk_mat = make_material("Tree Trunk", (0.30, 0.19, 0.10))
leaf_mat = make_material("Tree Leaves", (0.18, 0.40, 0.20))

tree_positions = [
    (-10.0, -0.8),
    (-6.5, -0.8),
    (2.0, -0.8),
    (7.0, -0.8),
    (10.0, 0.0),
    (-10.0, 6.5),
    (6.0, 7.0),
]

for index, (x, y) in enumerate(tree_positions):
    add_cube(
        f"Tree {index + 1} Trunk",
        (x, y, 0.65),
        (0.28, 0.28, 1.3),
        trunk_mat,
    )

    bpy.ops.mesh.primitive_cone_add(
        vertices=6,
        radius1=0.95,
        radius2=0.12,
        depth=1.8,
        location=(x, y, 1.95),
    )
    tree = bpy.context.object
    tree.name = f"Tree {index + 1} Foliage"
    tree.data.materials.append(leaf_mat)

# ------------------------------------------------------------
# SUN LIGHT
# ------------------------------------------------------------

bpy.ops.object.light_add(
    type="SUN",
    location=(0, -8, 14),
)

sun = bpy.context.object
sun.name = "City Sun"
sun.data.energy = 2.0
sun.data.angle = math.radians(12)
sun.rotation_euler = (
    math.radians(25),
    math.radians(-20),
    math.radians(-30),
)

# ------------------------------------------------------------
# WORLD LIGHTING
# ------------------------------------------------------------

world = bpy.data.worlds.new("City Sky") if not scene.world else scene.world
scene.world = world
world.use_nodes = True

background = world.node_tree.nodes.get("Background")
background.inputs["Color"].default_value = (0.28, 0.38, 0.52, 1.0)
background.inputs["Strength"].default_value = 0.65

# ------------------------------------------------------------
# CAMERA
# ------------------------------------------------------------

bpy.ops.object.camera_add(location=(17, -24, 17))
camera = bpy.context.object
camera.name = "City Camera"

target = Vector((0, 1.5, 2.3))
direction = target - camera.location
camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

camera.data.type = "ORTHO"
camera.data.ortho_scale = 25
camera.data.lens = 50

scene.camera = camera

# ------------------------------------------------------------
# RENDER SETTINGS
# ------------------------------------------------------------

scene.render.engine = "BLENDER_EEVEE_NEXT"

scene.render.resolution_x = 960
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100

scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.render.film_transparent = False
scene.render.filepath = PREVIEW_PATH

scene.render.image_settings.color_depth = "8"

# Ambient occlusion and shadows
scene.render.image_settings.compression = 15

# Color management
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.view_settings.exposure = 0.0
scene.view_settings.gamma = 1.0

# ------------------------------------------------------------
# SAVE SCENE FIRST, THEN RENDER EXACTLY ONE PREVIEW
# ------------------------------------------------------------

# Save the complete Blender scene before rendering.
bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)

# Render one still image only. No animation or frame sequence.
scene.render.filepath = PREVIEW_PATH
bpy.ops.render.render(write_still=True)

print("Low-poly city scene created successfully.")
print(f"Blender scene: {BLEND_PATH}")
print(f"Preview image: {PREVIEW_PATH}")
