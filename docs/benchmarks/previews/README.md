# Reference previews (1 frontier vs 1 local)

A deliberately small set of screenshots kept in the repository so the visual
difference between a frontier model and a local model is visible without running
anything. Each image is a real headless-Chrome capture of the committed/scored
artifact, not an illustration.

| Task | Frontier (DeepSeek V4.1 Flash) | Local (Nemotron E4B) |
|---|---|---|
| `company_website` | [deepseek/company_website.png](deepseek/company_website.png) | [nemotron-e4b/company_website.png](nemotron-e4b/company_website.png) |
| `minecraft_world` | [deepseek/minecraft_world.png](deepseek/minecraft_world.png) | [nemotron-e4b/minecraft_world.png](nemotron-e4b/minecraft_world.png) |

Both minecraft images are captured through the canvas-scoped check, so they show
the rendered scene rather than the page chrome. A blue background with a title
and no island is a **failure** (`renders_content (no <canvas> element)` or a
flat canvas), not a pass.

`blender_city` has no image on purpose: the task produces only `scene.blend`
(no renders). Open `results/blends/<model>/blender_city/<stamp>.blend` in
Blender to inspect it.

Regenerate these images with:

```powershell
python tools/compare_models.py --tasks company_website,minecraft_world --include-bakeoff
# then copy the two providers from results/compare/visuals/ here
```
