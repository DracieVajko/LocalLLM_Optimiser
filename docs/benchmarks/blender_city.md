# Blender city benchmark

Task id: `blender_city`. This is the **only** Blender task.

The model writes a Python script that builds a dense low-poly city from a fixed
map excerpt and saves `scene.blend`. **Nothing is rendered** - no `preview.png`,
no frames, no images. The deliverable is the openable `.blend` file.

## Prompt (copy into the model under test)

```text
Build a dense low-poly city in Blender from the map excerpt below. Each
character is one 4 m cell and the grid is 12 x 12 cells.

MAP (rows top to bottom):
##..##..##..
##..##..##..
............
##..##..##..
##..##..##..
~~~~~~~~~~~~
PP..##..##..
##..##..##..
............
##..##..##..
##..##..##..
............

Legend: '#' is a city block that must contain 2-4 separate buildings, '.' is a
street (keep it clear of buildings, 2 cells wide), '~' is a river running
across the city, 'P' is a park with trees.

Requirements:
- Build the entire grid, not a subset: at least 60 buildings total, spread over
  every '#' block.
- Vary the heights: ordinary buildings 2-8 floors, at least 3 landmark towers of
  20 m or more, so the skyline is not flat.
- The park needs at least 4 trees (trunk plus foliage).
- The river must be a separate flat mesh, not a hole in the ground.
- One ground plane under everything, streets visible as lighter strips.
- A sun light and one camera framing the city from above at an angle.
- Give the scene and the main collections clear names.
- Save the scene as scene.blend. Do NOT render anything: no preview.png, no
  frames directory, no images of any kind, and do not call bpy.ops.render.

Output ONLY the complete Python script in a markdown code fence starting with
```python and ending with ```. Do not include any other text.
```

## Acceptance checks

| Check | What it verifies | Weight | Critical |
|---|---|---:|---|
| `script_defines_scene` | uses `bpy.ops.mesh` / primitives | 2.0 | yes |
| `has_buildings` / `has_streets` / `has_park` / `has_river` | the four city elements | 1.0 each | - |
| `has_camera` / `has_light` | scene rig | 1.0 each | - |
| `is_python_code` | the script compiles | 2.0 | yes |
| `saves_blend` | `save_as_mainfile` | 1.0 | yes |
| `no_render` (negated) | no `bpy.ops.render` call | 1.5 | yes |
| `blend_runs` | Blender exited 0 | 1.0 | yes |
| `blend_is_binary` | real `.blend` (zstd/gzip accepted) | 2.0 | yes |
| `blend_min_size` | `.blend` > 16 KB | 1.0 | yes |
| `blend_has_camera` / `blend_has_light` | a camera and a light exist in the opened file | 1.0 each | - |
| `city_mesh_count` | at least 60 mesh objects in the opened file | 2.0 | yes |
| `city_height_variety` | at least 3 meshes >= 15 m, tallest >= 15 m | 1.5 | - |
| `city_footprint` | city spans at least 40 m | 1.0 | - |

The structural checks are measured by opening `scene.blend` in background
Blender (`lm_optimizer/services/blend_inspect.py`), not by grepping the script,
so a comment cannot satisfy them.

## Run

```powershell
python -m lm_optimizer.cli.main lab bakeoff --models <model-id> --tasks blender_city --context 8192 --safe
```

Artifacts: `build_scene.py`, `scene.blend`, `blender.log`, `debug.json`.
The produced `.blend` is also copied to
`results/blends/<model>/blender_city/<timestamp>.blend`, so it can be opened in
Blender after the scratch workdir is cleaned; the path is recorded as
`blend_file` and shown in the web UI history.

## Reference result

The committed DeepSeek V4.1 Flash artifact
(`benchmarks/deepseek_agent/blender_city/build_scene.py`) scores **1.0**. It
builds the full grid procedurally, saves `scene.blend` and never renders.

## Why no images

Rendering 60+ buildings produced hundreds of PNGs and minutes of GPU time per
attempt while adding nothing to the score. The `.blend` file is the artifact a
person can actually inspect, so the task stops at saving it.
