# Why each local model failed

Evidence-based failure table. Every raw artifact lives in `results/bakeoff/`
(gitignored); re-score them at any time with:

```powershell
python tools/explain_failures.py            # current scorer, newest artifact per model/task
```

A "model bug" means the generated file is genuinely wrong. A "host issue" means
LM Studio could not load or generate at all, so no artifact exists.

## Status after the 2026-11-10 scoring fixes

| Model | Task | Result | Root cause |
|---|---|---|---|
| `nvidia-nemotron-3.5-bolt-e4b` | email, minecraft, web | **1.0** | — |
| `nvidia-nemotron-3.5-bolt-e4b` | blender_skyblock | 0.0 | Model bug: the script creates a camera at line 70 but never assigns `scene.camera`, so the render aborts with `RuntimeError: Cannot render, no camera` and no frames are written. |
| `nvidia-nemotron-3.5-bolt-74b-a9b` | email | **1.0** | — |
| `nvidia-nemotron-3.5-bolt-74b-a9b` | minecraft | 0.0 | Model bug: no Three.js `<script src>` at all and a duplicate `function generateWorld()` — `SyntaxError: Identifier 'generateWorld' has already been declared`. Page renders a static splash. |
| `nvidia-nemotron-3.5-bolt-74b-a9b` | web | not run | Host slowness: 0.4 tok/s, a 4096-token page needs ~3 hours. Run cancelled. |
| `nvidia-nemotron-3.5-bolt-74b-a9b-24gb` | email | 1.0 | — |
| `nvidia-nemotron-3.5-bolt-74b-a9b-24gb` | web, blender | 0.0 / load error | Host: needs 41.9 GB with a second model resident; HTTP 400 on load, HTTP 500 on chat. |
| `swift-qwen3.8-27b` | email | 1.0 | — |
| `swift-qwen3.8-27b` | web | **1.0** | Fixed by `--no-thinking`: 1128 s, 3.6 tok/s, no reasoning in the file. |
| `swift-qwen3.8-27b` | blender | 0.0 | Model bug with thinking on: reasoning prose is written *into* `build_scene.py` (`line 66: SyntaxError: unterminated string literal`). Retried with `--no-thinking`. |
| `qwen3.8-9b-distill` | web | 0.84 | Model weakness: no `@media` query and no table/grid layout. The retry with `--no-thinking` produces real HTML now (it scored 0.0 before because the file was prose). |
| `qwen3.8-9b-distill` | email | 0.73 | Model weakness: attempt 0 lacked a closing (`has_closing`), repair attempt 1 introduced a bracketed placeholder. |
| `prism-ml/bonsai-27b` | web | **1.0** | — |
| `prism-ml/bonsai-27b` | minecraft, email | **1.0** | Fixed by `--no-thinking`: minecraft 140 s at 22 tok/s, email 3 s at 25 tok/s. The first run's failures were reasoning leakage, not capability. |
| `google/gemma-4-26b-a4b-qat` | email | **1.0** | Fixed by `--no-thinking` (161 s at 0.4 tok/s). The earlier "engine 500" was the reasoning path, not a dead engine. |
| `google/gemma-4-26b-a4b-qat` | blender_skyblock | 0.0 | Model bug: the script starts mid-file with an indented `def create_material(...)` → `IndentationError` at line 1. |
| `qwen/qwen3.6-35b-a3b` | email | host issue | Engine 500 on chat after a successful load. |
| `qwen3.8-27b-twin-turbo-...` | email, web, minecraft | host issue | Minimal config loads, chat returns 500. |
| `openai-gpt-oss-20b-...-heretic` | minecraft | **1.0** | — |
| `openai-gpt-oss-20b-...-heretic` | web | 0.0 | Model bug: `document.getElementById("avgLatency")).innerText` — unbalanced parenthesis, also missing the viewport meta. |
| `openai-gpt-oss-20b-...-heretic` | blender_skyblock | 0.0 | Model bug: `verts = [(x, y, 0) for x in range(-10, 11)) for y ...]` — mismatched brackets; no `save_as_mainfile`. |
| `openai-gpt-oss-20b-...-heretic` | email | 0.0 | Model bug: reasoning dump instead of an email. |

## The two failure families

1. **Reasoning leakage.** Bonsai, qwen 9B, gemma and gpt-oss write their thinking
   into the artifact. LM Studio advertises only `off`/`on` for reasoning, and
   even `reasoning: "off"` does not strip the template's thinking block for
   these models. Retries run with `--no-thinking`, which fixed Bonsai (3/3
   tasks to 1.0), Gemma (email to 1.0) and Swift (dashboard to 1.0). Where a
   model still fails after that, the remaining cause is ordinary generation
   quality (qwen 9B misses a media query; Swift writes `location=(0.5, -1, 0.6])`).
2. **Engine crash on this host.** qwen 3.6 35B and twin-turbo accept the load
   request and then return `500 Engine protocol startup was aborted` on the
   first chat. Gemma was suspected of the same, but with `--no-thinking` it
   generated normally, so that diagnosis was wrong.

## Fixed scoring bugs found during this audit

These made earlier scores wrong in both directions:

- **Prose passed as HTML** (qwen 9B dashboard scored 0.81): now blocked by the
  critical `html_document` check.
- **Broken JavaScript scored 1.0** (bonsai, gpt-oss, 74B): now blocked by
  `js_parses`.
- **Blender syntax errors cost a full render** before being reported: now
  `is_python_code` fails fast.
- **`has_subject` rejected "Subject line:"** even though the prompt uses that
  exact wording.
