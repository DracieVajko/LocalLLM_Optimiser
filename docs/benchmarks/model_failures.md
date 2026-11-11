# Why each local model failed

Evidence-based status of every downloaded model. Raw artifacts live in
`results/bakeoff/` (gitignored); re-score them at any time with:

```powershell
python tools/explain_failures.py      # newest artifact per model/task, current scorer
```

A **model bug** means the generated file is genuinely wrong. A **host issue**
means LM Studio could not load or generate at all. A **host slowness** means the
run is possible but impractical on this machine.

## Current status (2026-11-11)

| Model | email | company_site | minecraft | blender_city | deep_research |
|---|---:|---:|---:|---:|---:|
| `nvidia-nemotron-3.5-bolt-e4b` | 1.00 | 1.00 | 1.00 | 0.00 | 0.93 |
| `nvidia-nemotron-3.5-bolt-74b-a9b` | 1.00 | 1.00 | 0.00 | — (too slow) | — |
| `swift-qwen3.8-27b` | 1.00 | 1.00 | — | 0.00 | — |
| `prism-ml/bonsai-27b` | 1.00 | 1.00 | 0.00 | 0.00 | — |
| `openai-gpt-oss-20b-…-heretic` | 0.00 | 1.00 | 1.00 | 0.00 | — |
| `qwen3.8-9b-distill` | 0.73 | 0.85 | — | 0.00 | — |
| `google/gemma-4-26b-a4b-qat` | 1.00 | — (timeout) | — | — | — |
| `qwen/qwen3.6-35b-a3b` | — (engine 500) | — | — | — | — |
| `qwen3.8-27b-twin-turbo-…` | — (engine 500) | — | — | — | — |
| `mirothinker-v1.5-30b…` | **not tested** | **not tested** | **not tested** | **not tested** | **not tested** |

`—` means the task was never run for that model. `tiny` details below.

## Failure details

| Model | Task | Result | Root cause |
|---|---|---|---|
| `e4b` | all | 1.0 | — |
| `e4b` | blender_city | 0.0 | Model bug: the script dies on `is_python_code` (`did you forget parentheses around the comprehension target?`) and the repair attempt writes nothing, so no `.blend` is produced. |
| `e4b` | deep_research_report | 0.93 | Wrote a valid report with citations, but only 370 words where the task requires 800. |
| `74b` | minecraft | 0.0 | Model bug: no Three.js `<script src>` and a duplicate `function generateWorld()` → `SyntaxError: Identifier 'generateWorld' has already been declared`. Page renders a static splash. |
| `74b` | web | not run | Host slowness: 0.4 tok/s; a 4096-token page needs ~3 hours. |
| `swift` | blender_city | 0.0 | Model bug: `location=(0.5, -1, 0.6])` bracket mismatch in all attempts. |
| `bonsai` | minecraft | 0.0 | Blank page (`mean=3.0 sd=25.2 dark=98%`) even with `--no-thinking`. |
| `bonsai` | blender_city | 0.0 | Model bug: `from mathutils import Vector, Matrix4f` — `Matrix4f` does not exist. |
| `gpt-oss` | email | 0.0 | Reasoning dump instead of an email (no `Subject:`). |
| `gpt-oss` | blender_city | 0.0 | Model bug: `verts = [(x, y, 0) for x in range(-10, 11)) for y ...]` — mismatched brackets. |
| `qwen9b` | email | 0.73 | Attempt 0 lacked a closing; repair attempt 1 introduced a bracketed placeholder. |
| `qwen9b` | company_site | 0.85 | Real HTML now, but no `@media` query and no table/grid layout. |
| `qwen9b` | blender_city | 0.0 | Model bug: `SyntaxError: invalid decimal literal`. |
| `gemma` | web | timeout | Timed out after 45 min during `web_dashboard` (engine stall). |
| `qwen35b` | all | host issue | Loads, then `500 Engine protocol startup was aborted` on the first chat. |
| `twin` | all | host issue | Same engine 500. |

## What is impossible to finish here

1. **qwen3.6-35b and twin-turbo** — the engine aborts on this host's LM Studio
   build. Every retry ends in 500; not a prompt or scoring problem.
2. **74B web / minecraft at speed** — the model works (email and company site
   pass) but 0.4 tok/s makes a 4096-token page a ~3-hour run. Possible, not
   practical.
3. **Blender `.blend` inspection without Blender** — `blend_runs` and the city
   structural checks need `blender` on `PATH`. `tools/explain_failures.py` now
   adds it automatically.

## What is worth retrying

1. **mirothinker-v1.5-30b** — never benchmarked. Start with `email_write` and
   `company_website` (`--safe --no-thinking`).
2. **gemma company_site / blender_city** — email passed after `--no-thinking`;
   the web run timed out, so one fresh attempt is justified.
3. **qwen35b / twin** — only if the LM Studio engine build changes; otherwise
   mark as not runnable on this host.
4. **bonsai minecraft** — unlikely to change (the page is dark by construction),
   but a single retry is cheap.

## Failure families

1. **Reasoning leakage.** Bonsai, qwen 9B, gemma and gpt-oss write their thinking
   into the artifact. `--no-thinking` fixes the artifact (Bonsai 2/3, Gemma
   email, Swift dashboard). Remaining failures are ordinary generation quality.
2. **Engine crash on this host.** qwen 3.6 35B and twin-turbo accept the load
   and then return 500 on the first chat. Gemma was wrongly suspected; it
   generates normally with `--no-thinking`.

## Scoring bugs found during the audit (fixed)

- Prose passed as HTML → critical `html_document`.
- Broken JavaScript scored 1.0 → `js_parses`.
- Blank / flat canvas scored 1.0 → `renders_content` (pixel verdict).
- Empty completion scored 0.00 → `not_measured`.
- `load_s=30.0` was a response timeout → `null` + `load_measured=false`.
- `research_synthesis` capped at 0.867 → broader gap wording.
- ES-module Three.js and Blender 4.x engine names were rejected → accepted /
  normalised.
