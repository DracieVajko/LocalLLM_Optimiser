# Scoreboard

Two tables, two different questions:

- **Tier-A text tasks** — can the model follow a precise instruction? Scored by
  deterministic checks, no pixels involved.
- **Rendered artifacts** — does the output actually show something? Scored by
  measuring the screenshot, because the text checks cannot see the canvas.

## Method

- A run counts only if the model produced text. A crashed engine or an empty
  completion is `not_measured` and never enters a mean as `0.00`.
- A legacy run is also excluded when it scored `0.00` after less than a second:
  that is the same non-run, recorded before the status field existed.
- `research_synthesis` used to cap at 0.87 for every model; the unreachable
  check (`mentions_unknown`) accepted only "not stated/provided/mentioned" and
  rejected "not specified", "unclear", "the sources do not say". It now accepts
  those forms, so the ceiling is gone.
- Screenshots are classified by `lm_optimizer/services/png_stats.py`:
  `blank` (>= 97 % dark), `flat` (one tone), `weak` (sd < 6), `ok`. The
  `renders_content` sandbox check is critical, so a blank/flat render can no
  longer score 1.00.
- The `.blend` of a Blender run is copied to
  `results/blends/<model>/<task>/<stamp>.blend` for inspection.

## Frontier providers (measured 2026-11-10)

| provider | email | company_website | minecraft_world | blender_city |
|---|---:|---:|---:|---:|
| DeepSeek V4.1 Flash | 1.00 | 1.00 | 1.00 | 1.00 |
| Gemini | 1.00 | 1.00 | 1.00 | not run (new prompt) |
| ChatGPT | **0.00** | 1.00 | 1.00 | not run (new prompt) |

ChatGPT's email has no `Subject:` line, so it fails `has_subject` exactly like
the local models that leak reasoning. The Blender task was redefined on
2026-11-10 (dense city, `.blend` only, no renders), so the earlier frontier city
scripts no longer apply; regenerate them with the current prompt.

## Tier-A text tasks (reviewer audit, 2026-11-10)

Source: the 2026-11-10 audit of `sandbox_runs.jsonl` (241 rows), after removing
62 contaminated rows (`HTTPStatusError`, missing workdir, sub-second `0.00`).
The raw artifacts behind these numbers were removed from `results/` during the
same cleanup, so the table is a recorded measurement rather than something
`tools/scoreboard.py` can rebuild today. Re-run
`python tools/sandbox_all_models.py` to regenerate it.

| model | email | cal | deep | res | fetch | search | Tier-A | n |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **nemotron-e4b** | 1.00 | 1.00 | 1.00 | 0.87 | 1.00 | 1.00 | **0.98** | 6/6 |
| swift-27b (bez suffixu) | 1.00 | – | – | 0.87 | 1.00 | 1.00 | 0.97 | 4/6 |
| **swift-27b Q4_K_S** | 1.00 | 1.00 | 1.00 | 0.13 | 1.00 | 1.00 | **0.86** | 6/6 |
| **swift-27b Q2_K** | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | **0.83** | 6/6 |
| **qwen3-coder-30b** | 0.73 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.79 | 6/6 |
| **qwen3.6-35b-a3b** | 1.00 | 1.00 | 0.67 | 0.00 | 1.00 | 1.00 | 0.78 | 6/6 |
| bonsai-27b | 0.00 | 0.56 | 1.00 | 0.87 | 0.60 | 1.00 | 0.67 | 6/6 |
| mirothinker-30b | 0.47 | 1.00 | 1.00 | 0.00 | 0.40 | 1.00 | 0.64 | 6/6 |
| nemotron-74b | 1.00 | 0.44 | – | 0.00 | 1.00 | – | 0.61 | 4/6 |
| gpt-oss-20b heretic | 0.00 | 0.56 | 1.00 | 0.00 | 1.00 | 1.00 | 0.59 | 6/6 |
| qwen3.8-9b-distill | 0.00 | 0.22 | 0.56 | 0.73 | 0.27 | 1.00 | 0.46 | 6/6 |
| gemma-4-26b | 0.00 | 0.56 | – | – | 0.60 | – | 0.39 | 3/6 |
| recursivesi/flint | – | 0.11 | 0.11 | 0.00 | 0.13 | 0.00 | **0.07** | 5/6 |

Notes:

- The `res` column for the 0.87 rows is the `mentions_unknown` ceiling described
  above, not a model difference.
- `email` failures are reasoning leakage: the artifact starts with "Here's a
  thinking process" or "The user is requesting…". That is a real failure, and
  `--no-thinking` fixes it for Bonsai, Gemma and Swift (verified: Bonsai 3/3
  tasks to 1.00, Gemma email 1.00, Swift dashboard 1.00).

## Rendered artifacts (pixel verdict)

| provider | task | mean | sd | dark | tones | verdict |
|---|---|---:|---:|---:|---:|---|
| chatgpt | company_website | 236.3 | 35.5 | 0% | 57 | **ok** |
| chatgpt | minecraft_world | 62.7 | 51.0 | 0% | 151 | **ok** |
| deepseek | company_website | 243.9 | 37.9 | 0% | 70 | **ok** |
| deepseek | deep_research_report | 246.3 | 37.3 | 0% | 51 | **ok** |
| deepseek | minecraft_world | 137.1 | 81.0 | 7% | 128 | **ok** |
| gemini | company_website | 246.1 | 28.9 | 0% | 35 | **ok** |
| gemini | minecraft_world | 161.3 | 43.8 | 0% | 102 | **ok** |
| nvidia_nemotron_3_5_bolt_74b_a9b | minecraft_world | 181.6 | 22.1 | 0% | 17 | **ok** |
| nvidia_nemotron_3_5_bolt_e4b | minecraft_world | 164.4 | 20.3 | 0% | 46 | **ok** |
| openai_gpt_oss_20b_claude_4_5_opus_heretic_uncensored_i1 | minecraft_world | 188.0 | 0.0 | 0% | 1 | **flat** |
| prism_ml_bonsai_27b | minecraft_world | 2.3 | 23.0 | 99% | 21 | **blank** |
Before the pixel check, `bonsai` and `gpt-oss` both scored **1.00** for these
artifacts. They now score **0.00** with `renders_content (… verdict=blank)` and
`renders_content (… verdict=flat)`.

## Keep / delete

From the clean Tier-A data:

- **Q2_K vs Q4_K_S is undecided** (0.83 vs 0.86, one task apart). Q2_K is ~29 %
  faster and 5.5 GB smaller, so on a 6 GB card Q2_K is the rational keep.
- **Delete:** `flint` (0.07), `nemotron-74b` (0.61, TTFT 9.7 s, ctx 2048),
  `gemma-4-26b` (0.39, 11 % load failures), `mirothinker` (0.64),
  `qwen3.8-9b-distill` (0.46), and the `swift` Q4_K_S duplicate.
- **Keep:** `nemotron-e4b` (6.2 GB), `bonsai-27b` (4.7 GB), `swift-27b Q2_K`
  (11.9 GB), `qwen3-coder-30b` (18.6 GB), `qwen3.6-35b-a3b` (22.1 GB — check
  the 2048 context before keeping).

## Reproduce

```powershell
python tools/sandbox_all_models.py          # text tasks -> results/sandbox_runs.jsonl
python tools/compare_models.py --tasks all --include-bakeoff
python tools/scoreboard.py                  # -> results/scoreboard.md
python tools/scoreboard.py --out SCOREBOARD.md
```
