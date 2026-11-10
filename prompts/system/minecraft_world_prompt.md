# Minecraft-style voxel world — benchmark prompt

Task id: `minecraft_world` (registered in `lm_optimizer/services/sandbox_lab.py`).

## Prompt (copy into the model under test)

```text
Create one single HTML file named index.html — a Minecraft-style voxel world
rendered with Three.js loaded from a CDN. No build step, no bundler, no server,
no external assets (no images, sounds or zip files); everything except
Three.js must be inside this one file.

The page must contain:
- A hero section that feels like a tiny Minecraft world.
- Procedural terrain made of colored cubes (grass green, dirt brown,
  stone gray, water blue).
- Smooth 60fps rendering with requestAnimationFrame.
- First-person look controls (pointer lock or mouse move) and a crosshair
  in the center of the screen.
- A simple block-break / block-place interaction (click to remove or add
  a cube).
- Animated sky / day-night feel (moving sun or color gradient).
- Clean, modern, commented code.

Output ONLY the complete HTML in a markdown code fence starting with
```html and ending with ```. Do not include any other text.
```

## Optional predefined texture atlas

A ready-made 16x16 pixel-art atlas is included in
`benchmarks/deepseek_agent/minecraft_world/texture_atlas.js`. Paste it inside
the same `<script>` block and use it instead of inventing textures:

```js
const textures = createVoxelAtlas(THREE);
const geo = textures.blockGeometry(
  textures.tile.grassTop,
  textures.tile.grassSide,
  textures.tile.dirt
);
```

It provides grass top/side, dirt, stone, wood side/top, leaves, water, chest,
planks, roof, path, furnace, crafting table, bed and glass tiles, all generated
at runtime (no image files).

## Custom scene variations

The base skyblock stays the same; only the requested details change. Use
`--scene` for a short brief:

```powershell
python -m lm_optimizer.cli.main lab sandbox --task minecraft_world ^
  --model <model-id> --scene "fewer trees, a lighthouse and a bigger pond"
```

Or replace the whole prompt with `--custom-prompt "..."` if you need complete
control. Both are passed through the same acceptance checks, so keep the base
grass/dirt/stone island and (optionally) water elements present; a scene that
deliberately removes one of them will score lower on the corresponding check.

## Acceptance checks

| Check | Weight | Critical |
|---|---:|---|
| `index_html_exists` | 1.0 | yes |
| `single_file_html` | 1.0 | yes |
| `has_threejs` | 1.0 | — |
| `has_voxel_cubes` | 1.5 | — |
| `has_grass` | 1.0 | — |
| `has_stone` | 1.0 | — |
| `has_water` | 1.0 | — |
| `has_controls` | 1.5 | — |
| `has_render_loop` | 1.5 | — |
| `no_external_assets` (negated) | 1.0 | — |

The static web validator additionally checks HTML parsing, title, lang,
viewport, a single `h1`, inline JS syntax, labelled inputs and no external
scripts/styles.

## Run locally

```powershell
python -m lm_optimizer.cli.main lab sandbox --task minecraft_world --model <model-id>
```

Output: `results/sandbox/minecraft_world/<timestamp>_<model-slug>/index.html`,
plus a record in `results/sandbox_runs.jsonl`.

## Frontier example

The committed frontier example, the exact result table and the reproduction
commands live in [`docs/benchmarks/README.md`](../../docs/benchmarks/README.md).
