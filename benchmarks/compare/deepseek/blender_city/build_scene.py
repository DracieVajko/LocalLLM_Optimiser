"""Dense low-poly city built from the benchmark map excerpt.

Layout: 12 x 12 cells, one cell is 4 m. '#' blocks hold three buildings each,
'P' is a park with trees, '~' is a river, '.' are streets. The scene is saved
as scene.blend and nothing is rendered.
"""

import random

import bpy
from mathutils import Vector

CELL = 4.0
MAP = [
    "##..##..##..",
    "##..##..##..",
    "............",
    "##..##..##..",
    "##..##..##..",
    "~~~~~~~~~~~~",
    "PP..##..##..",
    "##..##..##..",
    "............",
    "##..##..##..",
    "##..##..##..",
    "............",
]

random.seed(7)


def material(name, color, roughness=0.85):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = roughness
    return mat


def box(name, location, size, mat, collection):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = size
    obj.data.materials.append(mat)
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


def plane(name, location, size, mat, collection):
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = (size[0], size[1], 1.0)
    obj.data.materials.append(mat)
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


def new_collection(name):
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    ground_mat = material("Ground", (0.16, 0.17, 0.16))
    street_mat = material("Street", (0.36, 0.36, 0.38))
    park_mat = material("Park", (0.13, 0.42, 0.18))
    water_mat = material("River", (0.09, 0.30, 0.55), roughness=0.15)
    trunk_mat = material("Trunk", (0.29, 0.19, 0.11))
    leaf_mat = material("Leaves", (0.10, 0.35, 0.14))
    facade = [
        material("FacadeWarm", (0.66, 0.55, 0.42)),
        material("FacadeStone", (0.55, 0.56, 0.58)),
        material("FacadeBlue", (0.32, 0.42, 0.55)),
        material("FacadeSand", (0.72, 0.66, 0.54)),
        material("FacadeSlate", (0.30, 0.32, 0.36)),
    ]
    roof_mat = material("Roof", (0.22, 0.14, 0.12))

    city = new_collection("City")
    terrain = new_collection("Terrain")
    water = new_collection("River")
    trees = new_collection("Trees")
    streets = new_collection("Streets")

    size = len(MAP) * CELL
    half = size / 2.0
    plane("Ground", (0, 0, 0), (size, size), ground_mat, terrain)

    # Street strips: every cell that is '.', one thin plane per run.
    for row, line in enumerate(MAP):
        for col, cell in enumerate(line):
            if cell != ".":
                continue
            x = (col + 0.5) * CELL - half
            y = half - (row + 0.5) * CELL
            plane(f"Street_{row}_{col}", (x, y, 0.02), (CELL, CELL), street_mat, streets)

    buildings = 0
    landmarks = 0
    for row, line in enumerate(MAP):
        for col, cell in enumerate(line):
            x = (col + 0.5) * CELL - half
            y = half - (row + 0.5) * CELL
            if cell == "P":
                plane(f"Park_{row}_{col}", (x, y, 0.03), (CELL, CELL), park_mat, terrain)
                for index in range(3):
                    tx = x + random.uniform(-1.2, 1.2)
                    ty = y + random.uniform(-1.2, 1.2)
                    box(f"TreeTrunk_{row}_{col}_{index}", (tx, ty, 0.9),
                        (0.28, 0.28, 1.8), trunk_mat, trees)
                    box(f"TreeLeaves_{row}_{col}_{index}", (tx, ty, 2.4),
                        (1.5, 1.5, 1.3), leaf_mat, trees)
            elif cell == "#":
                spots = [(-1.9, -1.9), (1.9, -1.9), (0.0, 1.9)]
                for index, (dx, dy) in enumerate(spots):
                    if landmarks < 4 and random.random() < 0.12:
                        height = random.uniform(21.0, 32.0)
                        landmarks += 1
                    else:
                        height = random.uniform(6.0, 17.0)
                    name = f"Building_{row}_{col}_{index}"
                    box(name, (x + dx, y + dy, height / 2.0),
                        (3.4, 3.4, height), random.choice(facade), city)
                    box(name + "_Roof", (x + dx, y + dy, height + 0.2),
                        (3.6, 3.6, 0.4), roof_mat, city)
                    buildings += 1
            elif cell == "~":
                plane(f"Water_{row}_{col}", (x, y, 0.04), (CELL, CELL), water_mat, water)

    # Landmark towers on the central avenue if randomness produced too few.
    while landmarks < 4:
        x = random.uniform(-half + 6, half - 6)
        y = random.uniform(-half + 6, half - 6)
        height = random.uniform(24.0, 34.0)
        box(f"Landmark_{landmarks}", (x, y, height / 2.0), (5.0, 5.0, height),
            facade[-1], city)
        landmarks += 1
        buildings += 1

    bpy.ops.object.light_add(type="SUN", location=(30, -35, 60))
    sun = bpy.context.object
    sun.name = "SunLight"
    sun.data.energy = 3.5
    sun.rotation_euler = (0.7, 0.15, 0.9)

    bpy.ops.object.camera_add(location=(half + 16, -half - 16, 42))
    camera = bpy.context.object
    camera.name = "CityCamera"
    target = Vector((0.0, 0.0, 6.0))
    direction = target - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scene.camera = camera
    camera.data.lens = 38

    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720

    bpy.ops.wm.save_as_mainfile(filepath="scene.blend", compress=True)
    print(f"City saved: {buildings} buildings, {landmarks} landmarks")


if __name__ == "__main__":
    main()
