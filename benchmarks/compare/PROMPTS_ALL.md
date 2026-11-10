# All frontier prompts

Paste one prompt per conversation. Do not add follow-ups, do not ask for
a different design. Save each answer with the importer below.

## email_write

Save the answer as `email.txt` via:

```powershell
python tools/compare_models.py --provider chatgpt --task email_write --clipboard
```

Prompt:

```text
Write a concise professional follow-up email to a client after a project kickoff. Include a Subject line, a greeting, a 2-3 sentence body with the next step and a concrete deadline, and a closing. Output only the email, with no placeholders such as [name].
```

## minecraft_world

Save the answer as `index.html` via:

```powershell
python tools/compare_models.py --provider chatgpt --task minecraft_world --clipboard
```

Prompt:

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

## company_website

Save the answer as `index.html` via:

```powershell
python tools/compare_models.py --provider chatgpt --task company_website --clipboard
```

Prompt:

```text
Build a complete single-file marketing website for a fictional company called "Northwind Studio", a small design and engineering consultancy. Everything must live in one index.html: inline CSS, no build step, no external assets, no network calls (no CDN fonts, images, scripts or stylesheets).

The page must contain:
- A sticky header with the company name and section navigation.
- A hero section with a headline, one sentence of supporting copy and a primary call-to-action button.
- A services section with at least three services, each with a title and a short description.
- An about section that explains who the company is.
- At least one customer testimonial with a named author.
- A contact section with a working-looking form (name, email, message) and a submit button.
- A footer with the company name and a copyright line.
- Responsive layout that works on mobile (<= 600px) and desktop, with a real media query.
- Accessible markup: semantic sections, one h1, labels for inputs.

Output ONLY the complete HTML document starting with <!DOCTYPE html>, no markdown fences, no explanations.
```

## deep_research_report

Save the answer as `index.html` via:

```powershell
python tools/compare_models.py --provider chatgpt --task deep_research_report --clipboard
```

Prompt:

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

Save the answer as `build_scene.py` via:

```powershell
python tools/compare_models.py --provider chatgpt --task blender_city --clipboard
```

Prompt:

```text
Build a dense low-poly city in Blender from the map excerpt below. Each character is one 4 m cell and the grid is 12 x 12 cells.

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

Legend: '#' is a city block that must contain 2-4 separate buildings, '.' is a street (keep it clear of buildings, 2 cells wide), '~' is a river running across the city, 'P' is a park with trees.

Requirements:
- Build the entire grid, not a subset: at least 60 buildings total, spread over every '#' block.
- Vary the heights: ordinary buildings 2-8 floors, at least 3 landmark towers of 20 m or more, so the skyline is not flat.
- The park needs at least 4 trees (trunk plus foliage).
- The river must be a separate flat mesh, not a hole in the ground.
- One ground plane under everything, streets visible as lighter strips.
- A sun light and one camera framing the city from above at an angle.
- Give the scene and the main collections clear names.
- Save the scene as scene.blend. Do NOT render anything: no preview.png, no frames directory, no images of any kind, and do not call bpy.ops.render.

Output ONLY the complete Python script in a markdown code fence starting with ```python and ending with ```. Do not include any other text.
```
