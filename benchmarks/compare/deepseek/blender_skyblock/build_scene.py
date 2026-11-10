"""Minecraft-style floating skyblock scene, rendered headless by Blender.

The script saves scene.blend before rendering so the validated artifact
exists even when the render is slow, then renders 120 frames into a
frames/ directory relative to the saved .blend file.
"""

import math
import os

import bpy
from mathutils import Vector


def make_material(name, color, roughness=0.8):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = roughness
    return material


def add_block(name, location, scale, material):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    block = bpy.context.object
    block.name = name
    block.scale = scale
    if block.data.materials:
        block.data.materials[0] = material
    else:
        block.data.materials.append(material)
    return block


def build_scene():
    # Clean start.
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    grass = make_material("GrassMat", (0.10, 0.55, 0.12))
    dirt = make_material("DirtMat", (0.36, 0.20, 0.09))
    stone = make_material("StoneMat", (0.52, 0.54, 0.57), roughness=0.95)
    wood = make_material("WoodMat", (0.40, 0.24, 0.10))
    leaves = make_material("LeavesMat", (0.08, 0.45, 0.10))
    chest_mat = make_material("ChestMat", (0.62, 0.35, 0.10))
    avatar_mat = make_material("AvatarMat", (0.15, 0.32, 0.55))

    # Floating block island: grass on top, dirt under it, stone at the base.
    size = 4
    for x in range(-size, size + 1):
        for y in range(-size, size + 1):
            if abs(x) + abs(y) > size + 2:
                continue
            add_block("GrassBlock", (x, y, 1.0), (1, 1, 1), grass)
            add_block("DirtBlock", (x, y, 0.0), (1, 1, 1), dirt)
            add_block("StoneBlock", (x, y, -1.0), (1, 1, 1), stone)
            add_block("StoneBlock", (x, y, -2.0), (1, 1, 1), stone)

    # Tree: a wood trunk with a leafy canopy.
    for z in range(2, 6):
        add_block("TreeTrunk", (2, 0, z), (1, 1, 1), wood)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            add_block("TreeLeaves", (2 + dx, dy, 5), (1, 1, 1), leaves)
    add_block("TreeLeaves", (2, 0, 6), (1, 1, 1), leaves)

    # A chest and a blocky avatar.
    add_block("Chest", (-3, 0, 2.0), (1, 1, 1), chest_mat)
    add_block("Avatar", (0, 3, 2.0), (1, 1, 2), avatar_mat)

    # Sun light.
    bpy.ops.object.light_add(type="SUN", location=(10, -8, 12))
    sun = bpy.context.object
    sun.name = "SunLight"
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(50), 0.0, math.radians(35))

    # Camera with an orbit animation around the island.
    bpy.ops.object.camera_add(location=(14, 0, 8))
    camera = bpy.context.object
    camera.name = "OrbitCamera"
    target = Vector((0.0, 0.0, 1.5))

    scene = bpy.context.scene
    scene.camera = camera
    scene.frame_start = 1
    scene.frame_end = 120

    for frame, angle in ((1, 0.0), (30, math.pi / 2), (60, math.pi),
                         (90, 3 * math.pi / 2), (120, 2 * math.pi)):
        camera.location = (
            math.cos(angle) * 14.0,
            math.sin(angle) * 14.0,
            8.0,
        )
        direction = target - camera.location
        camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        camera.keyframe_insert(data_path="location", frame=frame)
        camera.keyframe_insert(data_path="rotation_euler", frame=frame)

    # Render settings: 120 PNG frames, path relative to the saved .blend.
    scene.render.image_settings.file_format = "PNG"
    scene.render.resolution_x = 640
    scene.render.resolution_y = 360
    scene.render.resolution_percentage = 100
    scene.render.filepath = "//frames/frame_"

    # Save the .blend first (uncompressed so the size gate is meaningful).
    blend_path = os.path.abspath("scene.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path, compress=False)
    print("Saved scene.blend to", blend_path)

    # Render every frame of the animation.
    bpy.ops.render.render(animation=True)
    print("Rendered frames 1-120 into frames/")


if __name__ == "__main__":
    build_scene()
