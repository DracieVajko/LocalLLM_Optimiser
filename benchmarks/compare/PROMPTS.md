# Copy-paste prompts (identical for every provider)

Send **exactly** this prompt to DeepSeek, Nemotron (local), ChatGPT and any other
model, then save the answer with the command further down. Same prompt, same
file name, comparable result.

The canonical copies live in [`prompts/`](prompts/) — one `.txt` per task,
generated from the sandbox definitions by `python tools/export_prompts.py`.
`python tools/export_prompts.py --desktop` also builds
`Desktop/frontier_bench/` with the prompts, the DeepSeek references and a short
instruction sheet.

| Task | File the model must produce |
|---|---|
| `email_write` | `email.txt` |
| `minecraft_world` | `index.html` |
| `web_dashboard` | `index.html` |
| `deep_research_report` | `index.html` |
| `blender_city` | `build_scene.py` |
| `blender_skyblock` | `build_scene.py` |

---

## email_write

```text
Write a concise professional follow-up email to a client after a project kickoff. Include a Subject line, a greeting, a 2-3 sentence body with the next step and a concrete deadline, and a closing. Output only the email, with no placeholders such as [name].
```

## minecraft_world

```text
Create one single HTML file named index.html — a Minecraft-style voxel world rendered with Three.js loaded from a CDN. No build step, no bundler, no server, no external assets (no images, sounds or zip files); everything except Three.js must be inside this one file.

The page must contain:
- A hero section that feels like a tiny Minecraft world.
- Procedural terrain made of colored cubes (grass green, dirt brown,   stone gray, water blue).
- Smooth 60fps rendering with requestAnimationFrame.
- A camera that automatically orbits the floating island (no player   controls are required).
- Animated sky / day-night feel (moving sun or color gradient).
- Clean, modern, commented code.

Output ONLY the complete HTML in a markdown code fence starting with ```html and ending with ```. Do not include any other text.
```

## web_dashboard

```text
Build a self-contained HTML dashboard (single file, no external network calls) that shows four metrics, a filter, a model detail view, a light/dark theme toggle, and works on both mobile and desktop widths. Output ONLY the complete HTML starting with <!DOCTYPE html>, no markdown fences, no explanations.
```

## deep_research_report

```text
You are a deep research agent. Write a single self-contained HTML report answering the question: 'What are the real limits of running a 70B MoE model on consumer hardware with 24 GB VRAM, and how should conflicting Q3/Q4 speed claims be resolved?'

Use ONLY the sources below. Cite every factual claim with the source name in square brackets, e.g. [primary_official]. Do not invent sources. If the sources do not answer something, say so explicitly. Include: a title, an executive summary, at least four sections with headings, a 'Conflicting claims' section, a 'Limitations and uncertainty' section, and a References section. Render as a clean print-ready HTML page (inline CSS, no external assets).

SOURCES:
--- primary_official ---
The LM Studio REST API v1 exposes POST /api/v1/models/load with the parameters context_length, flash_attention, offload_kv_cache_to_gpu, eval_batch_size, physical_batch_size, parallel, context_checkpoints, num_experts and speculative_draft_max_tokens. Unknown keys are rejected with HTTP 400 unrecognized_keys before the model is loaded.

--- technical_secondary ---
The llama.cpp server exposes speculative decoding through --spec-type draft-mtp and the MTP head shipped with Qwen3.8 models. On a dense 27B at Q4_K_M the acceptance rate of n=3 drafts was about 73% and decode throughput rose from 31.2 to 40.3 tok/s on a V100.

--- outdated_source ---
Older guides state that a 27B Q4_K_M model needs 17.5 GB of VRAM and therefore cannot run on consumer cards at all. This guidance predates 3-bit quants and KV cache quantization.

--- conflicting_source ---
A community benchmark claims Q3_K_M is faster than Q4_K_M because the model is smaller, while another claims the opposite because Q3 requires more dequantization steps. Both were measured on Apple Silicon, where the Q3 kernel is known to be unusually slow.

--- irrelevant_source ---
A blog post about the history of the BASIC programming language describes how early microcomputers stored programs on cassette tapes.

END OF SOURCES.
```

## blender_city

```text
Write a Blender Python script that builds a simple low-poly city: 4-8 cubic buildings of varied heights on a ground plane, a road, a sun light and a camera looking at the city. Save the scene first as scene.blend, then render exactly ONE preview image named preview.png (PNG, at least 640x480) using bpy.ops.render.render(write_still=True). Do NOT render an animation and do not create a frames/ directory. Output ONLY the complete Python script in a markdown code fence starting with ```python and ending with ```.
```

## blender_skyblock

```text
Write a Blender Python script named build_scene.py that builds a floating block island scene: a grass/dirt/stone block island, a tree, a chest, a block avatar, a sun light, and a camera that orbits the island. Save the .blend file as scene.blend first, then render frames 1-120 into the frames/ directory with a path relative to the saved file (scene.render.filepath = '//frames/frame_') and call bpy.ops.render.render(animation=True). Output ONLY the complete Python script in a markdown code fence, starting with ```python and ending with ```. Do not include any other text.
```

---

# Saving an answer

Copy the whole model answer (fences included are fine), then either:

```powershell
# straight from the clipboard (Windows)
python tools/compare_models.py --provider chatgpt --task minecraft_world --clipboard

# or from a saved file
python tools/compare_models.py --provider chatgpt --task minecraft_world --file answer.md
```

The importer strips a markdown fence, writes
`benchmarks/compare/chatgpt/minecraft_world/index.html`, and then the normal run
scores and screenshots it:

```powershell
$env:PATH += ";C:\Program Files\Blender Foundation\Blender 5.3"
python tools/compare_models.py --tasks all
```

Open `results/compare/gallery.html` for the visual side-by-side.

Provider folder names are free-form (`chatgpt`, `gemini`, `perplexity`,
`odysseus`, `nemotron`, `qwen9b`, ...). Keep local-model artifacts in
`results/compare/local/<model>/<task>/` so they stay out of git.
