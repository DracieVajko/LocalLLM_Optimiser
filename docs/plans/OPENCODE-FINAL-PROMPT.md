# OpenCode final task — fix the optimiser + add Creative 3D (voxel island) benchmark

> Paste as the task. This supersedes ROUND-1/ROUND-2/ROUND-3 briefs. Work top-down, one work
> package at a time. Stop after each package and run its acceptance commands. Do not batch all
> packages into one PR. Everything below is measured from real runs on this machine — no
> assumptions, no estimates.

---

## 0. Where we are (verified against `data/optimizer.db`, `results/`, and 5 new campaigns)

| Item | State | Proof |
| --- | --- | --- |
| `long_context` document scaling | LANDED | `benchmark/suite.py:178-193`; prompt tokens 297 → ~4200 |
| Real repetitions (no cache replay) | LANDED via `--preset standard`, reps=3 | Runs now take 3.7–5.1 h; validation failures real |
| Validation failures persisted | LANDED | `check_run_integrity` reports `pass_rate 0/2` |
| `duration_ms` recorded | MOSTLY | 1/20 missing (was 17/19) |
| Sandbox: research sources injected | LANDED | `research_synthesis` 0.00–0.13 → **0.87** |
| Sandbox: email+calendar duration | LANDED | 0.83 → **1.00** |
| Sandbox sweep timeout | LANDED | 3600 s (`b5f91ec`) |
| Blender filename | LANDED | `build_scene.py` instead of `scene.blend` |
| **Quality gate 0.98** | **UNREACHABLE** | Every new model scored 0.83–0.917 < 0.98 → 0 winners |
| **`long_context` grades wrong thing** | **BLOCKER** | Asks "harbour access code", grader looks for "solar/wind/hydro" → 0.584 every model |
| **Pareto frontier empty** | **UNREACHABLE** | Empty with 17–19 passed configs |
| **Stage-4 no-op sweep** | **STILL RUNNING** | 12–15 configs at ctx 4096, batch/phys/par/ck |
| **Sandbox selfcheck** | **23 findings** | `tools/selfcheck_sandbox.py` exits 1 |

Result: **5 models × 14.4 h = 0 winners.** All ended `completed_no_validated_winner`.

**Your first job is the one-line fix + gate recalibration.** Do not start another campaign until
that's merged.

---

## 1. The blocker — fix before anything else

### 1.1 `long_context` asks one question, grades another (P0)

`benchmark/suite.py:188-191` now asks "What is the harbour access code?" (needle `7-TANGO`)
but `scoring/evaluator.py:338-342` still grades keywords `solar/wind/hydro/geothermal/biomass`
from the OLD renewable-energy question, plus `task_completion = min(1, tokens/150)`.

A one-token answer `7-TANGO` scores:
`0.007 + 0 + 1.0 + 0.5 + 1.0 + 1.0 = 3.507 / 6 = **0.584**` — exactly what every model got.

**Change R3-1:** Keep the scaled document (4200 tokens at ctx 8192). Restore the ORIGINAL question
so the grader's keywords match:

```python
# suite.py:191 — replace the needle question with the original summarisation question
prompt = doc_text[:doc_start] + repeated + doc_text[doc_end:]
```

`doc_text[doc_end:]` is `"\n\nQUESTION: Summarize the main renewable energy sources…"` — the grader
expects exactly this.

**Guard against regression** — add `tests/test_suite_grader_consistency.py`:
```python
def test_context_case_grades_what_it_asks():
    case = next(c for c in create_benchmark_cases(8192) if c.category == "context")
    text = case.prompt.lower()
    assert ("access code" in text) == ("7-tango" in text)
    grader_words = ["solar", "wind", "hydro", "geothermal", "biomass"]
    if "summarize" in text:
        assert sum(w in text for w in grader_words) >= 3
```

### 1.2 Recalibrate the quality gate (P0)

Even fixed, `long_context` is now genuinely hard (4200 tokens). A single test at 5/6 gives
aggregate `0.967 < 0.98` → winner rejected forever. The gate was calibrated against a test that
measured nothing.

**Change R3-2:** `services/quality.py` `passes_threshold`:
```python
def passes_threshold(self, quality) -> bool:
    if quality.critical_failed:
        return False
    return quality.overall >= self.config.minimum_score   # default 0.90
```
- Add `QualityScore.critical_failed: bool` (empty output, invalid JSON in `structured_output`,
  non-compiling code in `coding_task`, missing required keys).
- `profiles/registry.py`: balanced `0.90`, speed `0.88`, context `0.90`, quality-profile `0.93`.
  Keep old `0.98` readable via `--quality-threshold` for reproducibility.
- Fix contradictory message: `optimizer.py:4690` prints `minimum_score` but compared against a
  different value — one threshold, one source of truth.

**Acceptance:** unit test aggregate 0.916 no-critical → passes; with `critical_failed=True` → fails.

---

## 2. Pareto + validation persistence (P0)

`check_run_integrity` on new runs:
```
FAIL Pareto frontier empty with 17 passed configurations -> impossible
FAIL validation: 1 measurements ... pass_rate=0/1
```

**Change R3-3:**
1. Recompute frontier after quality validation; assert `len(frontier) >= 1` when any config passed.
2. Keep **every** validation round in `tested_configs`; compute `validation_pass_rate`,
   `quality_median`, `speed_median`, `speed_iqr`.
3. Report `Quality: 0.83 (median) · validation pass rate 0/2`, never a bare number.
4. Winner with `n_measured < 2` → `success_single_sample`, not `success`.

---

## 3. Make the filled prompt actually reach the window (P1)

At ctx 8192 the prompt sends 4118–4264 tokens = 50–52% of window, below the 60% honesty gate.
Builder assumes 3.6 chars/token; real is ~3.9.

**Change R3-4:** calibration loop (`OPENCODE-WP-C2-RECALL-PROBE.md` §2.5):
- build prompt, read server's `prompt_tokens`;
- if below `0.6 * ctx`, rebuild once with `chars_per_token *= target / measured`;
- persist per-model calibration in `data/capability/token_calibration.json`;
- assert `prompt_tokens >= 0.6 * context_length` before scoring; else `insufficient_context`
  (hard failure, never silent pass).

**Acceptance:** ctx 8192 → `prompt_tokens >= 4900`; ctx 16384 → `>= 9800`. Measured value printed
next to context size in report.

---

## 4. Blender end-to-end (P1)

Round 2 fixed the filename (`build_scene.py`) but not the pipeline:
- Model output wrapped in ` ```python ` fence → Blender can't parse it.
- Blender not on PATH → `.blend` never produced, yet task scores 0.70–0.76 from text markers.
- `selfcheck_sandbox.py` still: `blender perfect_script 0.76`, `prose_dump 0.70` (must be ≤ 0.20).

**Change R3-5:**
1. `_materialise` strips markdown fences from `code`/`python` kinds before writing
   (`fences_stripped: true`).
2. Validate by **executing**: `blender --background --python build_scene.py`, then introspect
   `scene.blend` (object counts, materials, camera, animated objects, frame range, rendered frames).
   Blender absent → `not_measured (blender_missing)`, task **cannot score above 0.2**.
   Never award text-marker points for an unrun file.
3. Reject `ast.parse` failures as `invalid_python`.
4. Add `blender_path` to manifest.

**Blender install note (verified 2026-11-07):** Microsoft Store Blender 5.2 lives at
`%LOCALAPPDATA%\Microsoft\WindowsApps\blender-launcher.exe` and **does** honour
`--background --python <file>`. There is no `C:\Program Files\Blender Foundation` and no uninstall
registry entry. `find_blender()` must scan `WindowsApps` and accept `blender-launcher.exe`.

**Blender .blend is zstd-compressed:** header is `28 B5 2F FD`, not `BLENDER`. Decompressed header
reads `BLENDER17-01` (format 17). Validator accepting only literal `BLENDER` prefix rejects every
modern `.blend`:

```python
def blend_is_valid(path):
    head = path.read_bytes()[:4096]
    if head[:7] == b"BLENDER": return True
    if head[:4] == bytes.fromhex("28b52ffd"):
        try:
            from compression import zstd
            return zstd.ZstdDecompressor().decompress(path.read_bytes())[:7] == b"BLENDER"
        except Exception:
            return True  # magic matches; don't fail what we can't decompress
    return False
```

**Acceptance:** `selfcheck_sandbox.py` `blender` fixtures ≤ 0.2. `tools/preview_blender.py --run
<dir> --launch` produces a `scene.blend` that `blend_is_valid()` accepts and ≥1 PNG in `frames/`.

---

## 5. NEW — Creative 3D / Voxel World Benchmark (P1, new category)

A whole new benchmark category based on your Tiny World Builder / Minecraft Skyblock idea.
Full spec already written under `benchmarks/creative_3d/voxel_island/`:

- `runtime/index.html` — Three.js shell, canvas, HUD, orbit controls, rotate/zoom/screenshot buttons
- `runtime/runtime.js` — docs
- `runtime/vendor/` — Three.js ES module + OrbitControls (vendored, no network)
- `prompts/voxel_island.txt` — the fixed prompt every model receives
- `prompts/reference_scene.js` — example good model output
- `runner/playwright_runner.js` — headless Chromium: screenshots before/after rotation, HUD read,
  `results/result.json`
- `scoring.md` — 40% visual / 25% geometry / 20% technical / 15% stability
- `README.md` — how to run

**What the model must generate:** exactly one file `scene.js` exporting
`createScene({ THREE, random })` returning a `THREE.Group`. No HTML, CSS, camera, lights,
renderer — the runtime handles those.

**What changes in the optimiser:**
- New sandbox/task kind `creative_3d` (artifact = `scene.js`, kind = `javascript`).
- Run via the same load/verify/preheat/measure skeleton; the "execution" is the Playwright runner.
- Score reported separately from tok/s: quality 0–100 + automatic checks pass/fail.
- Add to the sandbox task registry (`SANDBOX_TASKS` in `sandbox_lab.py`).

**Do not vendor Three.js by downloading in the prompt** — note in README that `vendor/` must be
populated once (CDN unpkg or local copy). The sandbox must not make network calls during
evaluation.

---

## 5b. NEW — Simpler Blender alternative: city + bridge (P2)

The skyblock task is good but heavy. Add a lighter Blender task:

**`blender_city_bridge`**: build a small city (4–6 blocks of varying height) + one bridge spanning
a gap, with a camera orbiting and a sun light. Save `scene.blend`, render 24 frames.

- `artifacts=("build_scene.py", "scene.blend", "frames/")` — same contract as skyblock.
- Prompt: "Write a Blender Python script that builds a small city of 4-6 cubic buildings of varying
  heights connected by a bridge, with a sun light and a camera that orbits. Set frame range
  1-120, render frames, save scene.blend."
- Checks: `bpy.ops.mesh`, `keyframe_insert`, `frame_start/frame_end`, `save_as_mainfile`,
  `bpy.ops.render`, plus the real `blend_is_valid()` gate.

Add to `SANDBOX_TASKS` and register in the sandbox task list.

---

## 6. View integration (P2) — show artifacts, don't hide them

The user wants to SEE what models produced:

| Task type | View behavior |
| --- | --- |
| `web` (HTML) | View button opens `index.html` in the default browser (or renders inline) |
| `text` (email, calendar, research, deep_research) | Popup / read-only view with formatted text (syntax-highlighted JSON where applicable) |
| `blender` | View button launches Blender with `scene.blend` (preview: one frame; `--full` for all frames) |

**Change:** Add a `view_artifact(task_id, run_id, artifact_name)` helper in `cli/result_view.py`
or a small CLI command:
```
python tools/view_artifact.py --run <run> --task web_dashboard --artifact index.html   # opens browser
python tools/view_artifact.py --run <run> --task calendar_event --artifact calendar.json  # popup
python tools/view_artifact.py --run <run> --task blender_skyblock --artifact scene.blend  # launches Blender
```

For text/JSON: write to a temp `.html` with `<pre>` + syntax highlight, open in browser (works as
a "popup"). For web HTML: open the file directly. For blend: launch Blender (use
`tools/preview_blender.py --launch --full`).

---

## 7. Work packages & PR order

| PR | Packages | Why this order |
| --- | --- | --- |
| A | R3-1, R3-2 | Without these, every campaign produces 0 winners |
| B | R3-3 | Makes verdicts explainable and stable |
| C | R3-7, R3-8 | Cuts ~1 h + several failed loads per campaign |
| D | R3-4 | Turns "context" from guess into measurement |
| E | R3-5, R3-6, 5b | Blender + sandbox wiring |
| F | 5 (creative_3d), view integration | New benchmark + view buttons |

**Hard rule:** Do not start another model campaign until PR A is merged. The last one cost 14.4 h
and produced zero winners because of a one-line question/grader mismatch. Verify with a single
model first:

```bash
python -m lm_optimizer.cli.main run --model nvidia-nemotron-3.5-bolt-e4b --preset standard
python tools/check_run_integrity.py --run <id>
```

That run must end `success` with a non-empty Pareto frontier and a stated validation pass rate
before any other model is touched.

---

## 8. Definition of done

1. `python tools/selfcheck_sandbox.py` → exit 0 (was 23 findings).
2. `python tools/check_run_integrity.py --run <new>` → zero FAIL.
3. New report shows:
   - `long_context` scores what its own question asks (perfect answer ≥ 0.95),
   - `Quality` with validation pass rate + threshold actually enforced,
   - Pareto non-empty,
   - exactly one `parallel` value (= 1),
   - phase timings sum to ≥90 % of each config duration,
   - `long_context` prompt ≥ 60 % of context, printed next to context size.
4. `nemotron-3.5-bolt-e4b` reaches `status=success` with a real winner.
5. Blender: `not_measured (blender_missing)` OR a `scene.blend` passing `blend_is_valid()`.
6. `benchmarks/creative_3d/voxel_island/` complete: model can run `scene.js` through the runtime,
   Playwright runner produces `results/result.json` with `score` and checks.
7. View integration works for web / text / blender artifact types.

---

## 9. Report back with

- The one-line diff of R3-1 + the test proving prompt and grader agree.
- `long_context` scores before/after for the same model (~0.58 → 0.85–1.00 expected).
- Whether `nemotron-e4b` finally produced a winner and at what quality.
- Phase-timing breakdown for one ctx-8192 configuration.
- `benchmarks/creative_3d/voxel_island/` runner output (`result.json`) with a sample model scene.
- What is still deferred and why — say it plainly, do not work around it.
