# Blender Studio — Studio in a Folder method

A coding agent that builds 3D product films in Blender from code, answering to
your direction. Every frame is rendered in Blender; none of it is AI footage.

## When to use
- "Render a 3D product film", "make a hero render", "model this product in Blender"
- "Build a scene in Blender", "create a 3D animation"
- User provides a product photo and wants a 3D recreation

## Prerequisites
- Blender 4.2+ installed (`blender --version`)
- Blender MCP (MCP-Link) connected, or run headless: `blender --background --python build.py`
- Read `docs/BLENDER_MCP.md` for setup

## The method (gate by gate)

1. **Interview** — ask the user what the film must say, the audience, the
   deliverable (still / 10 s / 30 s), and the style direction. Do not start
   building before you have a one-sentence film law.
2. **References** — find 3–5 reference films/products. Measure (composition,
   lighting, materials, timing). Adapt principles, never surfaces.
3. **Direction** — pick one of the 24 directions (D01 product film default).
   Write the direction as data (rules, not a filter).
4. **Brief** — one physical law per film. Propose 3–5 far-apart routes.
5. **Hero frame** — build one frame at final quality, iterate beside the
   reference until the look is fixed. No mass render before approval.
6. **Proof in motion** — render the hardest 5–10 s at final quality, approve
   as motion before any mass render.
7. **Build** — code the scene in Blender Python (`bpy`). Use `build.py` with
   `--preview` first (half size, few samples), then `--final`.
8. **Measure** — every render is measured: silhouette reads at phone size,
   materials in physical ranges (30–240 sRGB), one hero near centre (≤4 %W),
   light shapes the product first.
9. **Deliver** — code the master to a bitrate ≥ 50 Mbit/s; upload by hand.

## Rules that matter most
- Light first, then materials, then effects (LGT-01)
- One move per shot, on one line (CAM-02)
- One clock names every moment (MOT-01)
- The maker never judges its own work (AGT-09): propose, then let the user approve
- Materials from real data, not renders (MOD-01)
- Model by design: parts and sections, not carving (MOD-02)

## Blender Python skeleton (Blender 5.x)
```python
import bpy
# Clear scene
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
# Create collection (read-only scene.collection in 5.x)
root = bpy.data.collections.new('Studio')
bpy.context.scene.collection.children.link(root)
def cube(name, loc, scale, coll):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    ob = bpy.context.object
    ob.name = name
    ob.scale = scale
    for c in list(ob.users_collection):
        c.objects.unlink(ob)
    coll.objects.link(ob)
    return ob
# Camera + light
bpy.ops.object.camera_add(location=(30, -30, 25))
bpy.context.scene.camera = bpy.context.object
bpy.ops.object.light_add(type='SUN', location=(10, 10, 30))
# Save
bpy.ops.wm.save_as_mainfile(filepath='scene.blend')
```

## Output conventions
- `--preview`: half size, few samples, full duration
- `--final`: full quality master
- Always render at phone size first; judge with sound off, then on
- Step through every frame at move ends (±10 frames)

## Integration with LM Studio Optimizer
- The optimizer benchmarks a model's ability to generate Blender code via
  the `blender_city` sandbox task.
- A simpler `blender_simple_scene` task (create 3 objects + render) is
  available for faster capability checks.
- Generated scripts are executed headless: `blender --background --python build.py`
- MCP-Link connects Blender to LM Studio for live control (see docs/BLENDER_MCP.md).

## Honest limits
- Modelling a real product is the slowest step for an agent.
- The agent does not have your taste — use the gates and references.
- Final renders: 5–8 s/frame on RTX 4090; 1–2 h for a 30 s film.
- macOS and Linux are untested.
