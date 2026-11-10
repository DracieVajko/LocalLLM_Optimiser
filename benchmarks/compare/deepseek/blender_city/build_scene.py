"""Low-poly city: save scene.blend and render exactly one preview image."""

import math
import os

import bpy
from mathutils import Vector


def material(name, color):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.9
    return mat


def cube(name, location, scale, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(mat)
    return obj


def build_city():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    road = material("Road", (0.16, 0.17, 0.19))
    wall = material("Wall", (0.62, 0.62, 0.66))
    wall_blue = material("WallBlue", (0.30, 0.42, 0.62))
    wall_warm = material("WallWarm", (0.72, 0.58, 0.40))
    roof = material("Roof", (0.45, 0.16, 0.14))
    green = material("Green", (0.16, 0.48, 0.20))

    # Ground and a simple road strip.
    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0))
    ground = bpy.context.object
    ground.name = "Ground"
    ground.data.materials.append(green)

    cube("Road", (0, 0, 0.02), (30, 4, 0.04), road)

    # Six low-poly buildings with varied heights, all on the ground plane.
    specs = [
        ("BuildingA", (-9, -3, 3.0), (4, 4, 6.0), wall),
        ("BuildingB", (-3, -3, 4.5), (4, 4, 9.0), wall_blue),
        ("BuildingC", (3, -3, 2.5), (4, 4, 5.0), wall_warm),
        ("BuildingD", (9, -3, 3.5), (4, 4, 7.0), wall),
        ("BuildingE", (-6, 5, 2.0), (4, 4, 4.0), wall_warm),
        ("BuildingF", (6, 5, 4.0), (4, 4, 8.0), wall_blue),
    ]
    for name, location, scale, mat in specs:
        cube(name, location, scale, mat)
        # Flat roof cap.
        cube(name + "Roof", (location[0], location[1], location[2] + scale[2] / 2 + 0.15),
             (scale[0] + 0.4, scale[1] + 0.4, 0.3), roof)

    # Street lamps: thin poles with a warm block on top.
    for x in (-12, 0, 12):
        cube("LampPole", (x, 2.5, 1.0), (0.15, 0.15, 2.0), road)
        cube("Lamp", (x, 2.5, 2.1), (0.5, 0.5, 0.3), roof)

    # Sun and camera.
    bpy.ops.object.light_add(type="SUN", location=(15, -12, 20))
    sun = bpy.context.object
    sun.name = "SunLight"
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(45), 0, math.radians(30))

    bpy.ops.object.camera_add(location=(26, -26, 20))
    camera = bpy.context.object
    camera.name = "CityCamera"
    target = Vector((0, 0, 3))
    direction = target - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = camera

    scene = bpy.context.scene
    scene.render.resolution_x = 800
    scene.render.resolution_y = 600
    scene.render.image_settings.file_format = "PNG"

    # Save the .blend first; the preview is relative to the saved file.
    bpy.ops.wm.save_as_mainfile(
        filepath=os.path.abspath("scene.blend"), compress=False
    )
    scene.render.filepath = "//preview.png"
    bpy.ops.render.render(write_still=True)
    print("Saved scene.blend and preview.png")


if __name__ == "__main__":
    build_city()
