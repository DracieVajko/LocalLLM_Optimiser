# Sandbox v2 — redesign, re-test plan, output contract

Companion to `results/DEBUG-REPORT-20261106.md` (what is broken) — this document is
**what to build instead**, **how to test differently**, and **what files to write**.

Status: proposal. Nothing here is implemented. Ordered so each step is independently shippable.

**Already shipped alongside this document**

| file | what it does |
| --- | --- |
| `tools/selfcheck_sandbox.py` | 6 deterministic lints + 15 golden fixtures; reproduces every bug in ~1 s with no model. Currently: **26 findings**. |
| `tools/build_scoreboard.py` | builds `results/SCOREBOARD.md` + `results/scoreboard.csv` using only comparable metrics |
| `results/SCOREBOARD.md`, `results/scoreboard.csv` | the honest cross-model table (§6.4) |
| `docs/plans/schemas/attempt-manifest.example.json` | the per-attempt manifest shape (§6.2) |

---

## 1. Why the current design fails (one paragraph)

A sandbox task is scored by running ~10 regexes over the model's **entire raw output**
(`sandbox_lab.py:800-812`) and the result is a single weighted average. That design has three
fatal consequences, all observed in `results/`:

1. **It cannot tell code from talk about code.** A file containing zero HTML scores 0.75
   (`web_dashboard/20261106_053418`); 7.7 KB of reasoning scores 1.00 on a Blender task.
2. **It cannot tell "produced" from "valid".** `scene.blend` is text; nothing checks the magic
   bytes, so nothing notices.
3. **A weighted average hides catastrophes.** One unreachable criterion (`calendar_end`) silently
   caps every model at 0.826 forever; a truncated script still earns 0.92.

Two more structural issues: **artifacts are never executed** (`lab.py:789` omits `command=`), and
**criteria are not verified as reachable from the prompt** (the sources in `RESEARCH_PACKAGE` are
never sent).

---

## 2. Principles

| # | Principle | Consequence |
| --- | --- | --- |
| P1 | **Grade the artifact, never the transcript.** | Score only files the task declares. Reasoning, fences and apologies are moved aside before grading. |
| P2 | **Validity gates quality.** | A file that does not parse/open/run scores 0, not 0.75. Gates are boolean and multiplicative. |
| P3 | **Execute whenever execution is possible.** | Blender, Python and HTML all have deterministic checkers available locally. Regex is the fallback of last resort and is marked as such. |
| P4 | **Every criterion must be reachable.** | A check that demands a value the prompt does not supply is a task bug — lint it in CI, not in production. |
| P5 | **Strict instructions are gates, not penalties.** | "Output only JSON" / "no placeholders" ⇒ `critical=True`, score 0 on violation. |
| P6 | **Separate "can it" from "is it good".** | Report `valid_artifact_rate` next to `quality`: two models at 0.9 are not equal if one failed 4 of 10 artifacts. |
| P7 | **Unknown ≠ zero.** | A timeout is `not_measured`, never `0.0`. |
| P8 | **The suite must prove it can distinguish.** | Golden fixtures run in CI (see `tools/selfcheck_sandbox.py`). |

---

## 3. Scoring model (replaces the single weighted average)

Five layers. The score is `(sum of L2..L4 weights earned) × Π(L1 gates)`.

```
L0  produced      bytes on disk, non-empty                      (diagnostic only)
L1  valid         parses / opens / exits 0 / magic bytes        GATE  — binary, zeroes L2..L4
L2  conformance   exact contract: JSON keys, ISO-8601, schema,
                  required objects present, no placeholder text   weighted
L3  quality       graded rubric, needs a judge or a measurement  weighted
L4  behaviour     constraints: no fences, word limit, no invented
                  facts, tool-error honesty                      weighted, negated checks critical
```

Reporting a model then becomes four numbers, not one:

```
valid_artifact_rate   = L1 passes / attempts         e.g. 6/10
conformance           = mean L2                      e.g. 0.94
quality               = mean L3                      e.g. 0.81
behaviour             = mean L4                      e.g. 1.00
pass@1                = fraction of tasks fully passing on the first attempt
```

`valid_artifact_rate` is the number that exposes a model like `recursivesi/flint`, which currently
just looks "low quality" when in fact it mostly produces nothing usable.

---

## 4. The artifact contract (the fix for Blender)

Today: `artifacts[0]` is where the model's *text* is written, and `artifacts` doubles as
"what we expect to find". Those are two different things. Split them.

```python
# lm_optimizer/services/sandbox_lab.py

@dataclass
class ArtifactSpec:
    path: str                      # e.g. "build_scene.py" / "scene.blend"
    kind: str                      # text|json|html|python|blender|png|csv
    produced_by: str               # "model" | "runner"
    validator: str = ""            # key in VALIDATORS; "" = L0 only
    min_bytes: int = 1
    critical: bool = False         # a failed L1 gate zeroes the attempt


@dataclass
class SandboxTask:
    ...
    outputs: tuple[ArtifactSpec, ...] = ()   # replaces `artifacts`
    command: str = ""                        # e.g. "blender --background --python build_scene.py"
    max_output_tokens: int = 2048            # per task, not a global 2048
```

Blender becomes:

```python
BLENDER_TASK = SandboxTask(
    id="blender_skyblock",
    outputs=(
        ArtifactSpec("build_scene.py", "python", "model",
                     validator="python_parses", critical=True),
        ArtifactSpec("scene.blend", "blender", "runner",
                     validator="blend_opens", critical=True, min_bytes=100_000),
        ArtifactSpec("frames/", "png", "runner", validator="frames_rendered"),
        ArtifactSpec("introspection.json", "json", "runner",
                     validator="json_schema", critical=True),
    ),
    command="blender --background --python build_scene.py",
    max_output_tokens=6144,
    ...
)
```

The prompt must then say exactly that:

> *"Write `build_scene.py`. The runner will execute it with
> `blender --background --python build_scene.py`. Your script must save `scene.blend`, render
> frames into `frames/`, and print one JSON object to stdout describing the scene."*

**Rules that follow from the contract**

1. `produced_by == "model"` → `_materialise` writes there. `produced_by == "runner"` → the runner
   asserts the file exists afterwards. A model output is *never* written to a `runner` path.
2. `build_command_for` is not optional: `SandboxRunner` raises `MissingCommand` when a task has
   `outputs` with `produced_by == "runner"` and `command == ""`. This single assertion turns the
   current silent false-pass into a loud configuration error.
3. `max_output_tokens` lives on the task. Truncation is detected by
   `finish_reason == "length"` and reported as `truncated: true` in the manifest; a truncated
   artifact fails L1 for `code`/`blender` kinds.

### Blender validator (the one that would have caught everything)

`blend_opens(workdir, spec)` runs, not greps:

```python
INTROSPECT = """
import bpy, json, sys
d = bpy.context.scene
print("@@JSON@@" + json.dumps({
  "objects": {t: sum(1 for o in bpy.data.objects if o.type == t)
              for t in {o.type for o in bpy.data.objects}},
  "materials": [m.name for m in bpy.data.materials],
  "frame_range": [d.frame_start, d.frame_end],
  "animated_objects": [o.name for o in bpy.data.objects
                       if o.animation_data and o.animation_data.action],
  "camera": d.camera.name if d.camera else None,
  "lights": [o.name for o in bpy.data.objects if o.type == "LIGHT"],
  "render_engine": d.render.engine,
  "resolution": [d.render.resolution_x, d.render.resolution_y],
}))
"""
subprocess.run(["blender", "--background", "scene.blend", "--python-expr", INTROSPECT], ...)
```

Then L2 checks are *facts*, not words: `objects.MESH >= 8`, a material named like grass exists, a
camera exists, `abs(frame_end - frame_start) >= 48`, `animated_objects >= 1`,
`frames_rendered >= 5`, `black_frame_ratio < 0.9`.

If `blender` is not on PATH: `status: not_measured, reason: "blender_missing"` — **never a pass**
(see P7).

---

## 5. How to test differently

### 5.1 Stop testing one task per domain; split each domain by what it isolates

The current 9 tasks each conflate 4–5 skills, so a failure tells you nothing. Replace with
**families of small, single-skill tasks**, each with a deterministic checker. Suggested suite
(16 tasks, ~4 of which need a GPU-heavy model):

| family | task | deliverable | L1/L2 checker | what it isolates | cost |
| --- | --- | --- | --- | --- | --- |
| **format** | `json_strict` | `out.json` | `json.loads` after fence-strip; jsonschema | obey "ONLY JSON" | ~80 tok |
| **format** | `json_negative` | `out.json` | same, but a fenced/prose answer must score 0 | fence discipline | ~80 tok |
| **format** | `iso_datetime` | `out.json` | `datetime.fromisoformat` + tz required | exact schema | ~80 tok |
| **format** | `no_placeholder` | `out.txt` | regex on **model-only** text, `critical` | placeholder avoidance | ~200 tok |
| **code** | `python_exec` | `solve.py` | run it, compare stdout to golden | code that runs | ~250 tok |
| **code** | `python_stdlib_only` | `solve.py` | run in a venv with no packages | dependency honesty | ~250 tok |
| **tool** | `tool_protocol_ok` | `call.json` | jsonschema on the tool call | tool-use format | ~100 tok |
| **tool** | `tool_error_honest` | `call.json` | must emit the error object, **not** facts | hallucination under failure | ~100 tok |
| **web** | `html_dom` | `index.html` | html.parser + `@media` in `<style>` + `#theme-toggle` exists | real DOM | ~800 tok |
| **web** | `html_no_external` | `index.html` | DOM walk: no `src`/`href` to http | offline self-containment | ~600 tok |
| **research** | `corpus_cite` | `answer.txt` | every claim carries a source key present in the prompt | grounding | ~400 tok |
| **research** | `corpus_gap` | `answer.txt` | must name what the corpus does **not** answer | uncertainty | ~300 tok |
| **3d** | `blender_exec` | `build_scene.py` → `scene.blend` | introspection JSON (above) | 3D that opens | 3–8 min |
| **context** | `needle_4k/8k/16k` | `answer.txt` | exact needle string returned | real context ceiling | 3× |
| **agentic** | `notes_to_event` | `response.txt` | email part + calendar part parsed separately | multi-part output | ~350 tok |
| **repair** | `repair_under_feedback` | patched artifact | delta of named checks | repair efficiency | 2× |

Two things this buys you: most tasks cost <10 s at �2 tok/s, so you can run the cheap families on
**every** model and only the 3D/context ones on candidates; and a failure now names the skill.

### 5.2 Sample k=3, report pass@1 and pass^3

Today n=1 everywhere, so nothing measures reliability — yet `*-best.md` prints
`stability: normalized 0.884`. That number is unsupported.

```
pass@1  = tasks where attempt 1 alone passes
pass^3  = tasks where all 3 attempts pass   (reliability — the one you want on a 6 GB GPU)
median_latency, p90_latency
```

At 2.8 tok/s a flaky model shows up in `pass^3` and nowhere else.

### 5.3 Measure the context ceiling, don't infer it

`_context_trio` (`reporting.py:669`) reports the **largest tested** context as "maximum stable".
Replace with a recall probe: place a unique token at 10/50/90 % depth, ask for it back, verify
exactly. Do it at 4096/8192/16384. The ceiling is the largest size with 3/3 recall at 90 % depth.
That is a measurement, and it takes ~2 min instead of a 13.5 h campaign.

### 5.4 Judge quality with a rubric, not a keyword list

`has_synthesis` currently means "contains the word synthesis". Two cheap upgrades:

- **Schema-checked structure** instead of vocabulary (`json_schema` on the plan: 3+ subquestions,
  3+ queries, criteria present as fields).
- **A second model as judge** with a 1–5 rubric and the source documents, scored
  `judge_score` separately from the deterministic checks. Keep them apart in the report; never let
  a judge's opinion zero a deterministic gate.

### 5.5 Make the harness prove itself (highest value / lowest cost)

`tools/selfcheck_sandbox.py` already does this — 6 lints, ~1 s, no model:

| lint | catches |
| --- | --- |
| `fixtures` | scores 15 golden answers (perfect / prose / empty / fenced) and compares to expected |
| `reachable` | a check demanding `10:45` that the prompt never states |
| `wiring` | `has_viewport` vs `has_viewport_meta` (discarded validator results) |
| `contract` | text written into `scene.blend`; `no_*` checks missing `negate=True` |
| `material` | "using the provided documents" with no documents |
| `critical` | strict instructions that are only partial-credit |

Current output: **26 findings**, reproducing every bug in the debug report with no GPU.
Wire it as a pre-flight: `lab sandbox` refuses to run while it is red, and as
`tests/test_sandbox_selfcheck.py` in CI.

---

## 6. Output files

### 6.1 Layout

```
results/
  runs/
    <run_id>/
      manifest.json                       # run level: host, versions, models, task set
      models/<model-slug>/
        <task_id>/
          attempt-1/
            manifest.json                 # ← schema below
            checks.json                   # per-criterion pass/fail + evidence
            exec.json                     # command, exit code, stdout/stderr tails
            files/                        # the declared artifacts, verbatim
              build_scene.py
              scene.blend
              frames/0001.png
          attempt-2/ ...
  scoreboard.csv                          # one row per model (comparable metrics only)
  SCOREBOARD.md                           # readable, with exclusions stated
  DEBUG-REPORT-20261106.md
```

Rules:

1. **Append-only.** The current `lab sandbox` overwrites `results/sandbox-<task>.json` on every run
   — that is why `tools/backfill_sandbox_runs.py` had to reconstruct history from a log. One
   directory per run, never rewritten.
2. **No cross-model retention.** `apply_retention(keep_last_10)` is per task, so model #11 deletes
   model #1's evidence. Keep per `(model, task)`, and never prune a path referenced by a jsonl row.
3. **The model's raw text is kept** at `files/raw.txt` for debugging, but **never graded**.
4. **`not_measured` is a first-class status**, distinct from `failed`.

### 6.2 `attempt manifest` (schema in `docs/plans/schemas/attempt-manifest.example.json`)

```json
{
  "schema": "lmopt/sandbox-attempt@2",
  "run_id": "7ae5ffae",
  "model": "swift-qwen3.8-27b@q2_k",
  "model_sha256": "…",
  "task_id": "blender_skyblock",
  "attempt": 1,
  "started_at": "2026-11-06T04:18:14+01:00",
  "duration_s": 1531.8,
  "load": {"channel": "REST", "verification": "MATCH", "context_length": 8192},
  "generation": {"finish_reason": "stop", "truncated": false,
                 "completion_tokens": 4180, "generation_tok_s": 2.8},
  "exec": {"command": "blender --background --python build_scene.py",
           "exit_code": 0, "duration_s": 41.2},
  "artifacts": [
    {"path": "build_scene.py", "kind": "python", "bytes": 14877,
     "sha256": "…", "valid": true, "validator": "python_parses"},
    {"path": "scene.blend", "kind": "blender", "bytes": 1208349,
     "sha256": "…", "valid": true, "validator": "blend_opens",
     "facts": {"objects": {"MESH": 34, "CAMERA": 1, "LIGHT": 1},
               "frame_range": [1, 120], "animated_objects": ["Camera"],
               "materials": ["grass", "dirt", "stone", "trunk", "leaves", "chest"]}}
  ],
  "layers": {"L1_valid": true, "L2_conformance": 0.94, "L3_quality": 0.80,
             "L4_behaviour": 1.00},
  "score": 0.75,
  "status": "passed",
  "repair": {"attempts_used": 1, "fixed_checks": ["has_keyframes"],
             "added_tokens": 412, "efficiency": 0.0024}
}
```

### 6.3 `checks.json` — one row per criterion, with evidence

```json
[
  {"name": "blend_opens", "layer": "L1", "critical": true,
   "passed": true, "detail": "opened in Blender 4.2.1",
   "evidence": {"command": "blender --background scene.blend --python-expr …",
                "exit_code": 0}},
  {"name": "objects_mesh_gte_8", "layer": "L2", "critical": false,
   "passed": true, "detail": "34 mesh objects (need >= 8)"},
  {"name": "frames_rendered", "layer": "L2", "critical": false,
   "passed": false, "detail": "0 frames in frames/",
   "evidence": {"glob": "frames/*.png", "count": 0}}
]
```

The rule: **no check may pass without evidence**. If a check can only say "the word appears",
it must be marked `"layer": "L4", "kind": "heuristic"` and weighed accordingly — this is what makes
the difference between the current false 1.00 and an honest 0.6.

### 6.4 The two reports

- `results/scoreboard.csv` + `SCOREBOARD.md` — generated by `tools/build_scoreboard.py`
  (already in the repo, re-runnable). Absolute metrics only, broken tasks excluded with a reason,
  timeouts marked `TMO`/`not_measured`.
- `results/<model>-best.md` — keep, but add: a **Sandbox** section (per-task, per-layer), a
  `valid_artifact_rate`, `pass@1` / `pass@^3`, and the sentence *"score is a within-run rank and is
  not comparable across models"*.

---

## 7. Migration order

| step | change | acceptance |
| --- | --- | --- |
| 1 | Add `tools/selfcheck_sandbox.py` to CI; make `lab sandbox` refuse to run while red | tool exits 0 |
| 2 | `SandboxTask.outputs` + `ArtifactSpec`; keep `artifacts` as a deprecated alias | selfcheck `contract` lint green |
| 3 | `_materialise` honours `produced_by`; `MissingCommand` when a runner artifact needs a command | blender writes `build_scene.py`, not `scene.blend` |
| 4 | Per-task `max_output_tokens`; record `finish_reason`/`truncated` | no blender output ends mid-identifier |
| 5 | Fix the 4 broken tasks: inject `RESEARCH_PACKAGE`, add the 45-minute duration, `negate=True`, rename `has_viewport` | selfcheck `reachable`/`material`/`wiring` green |
| 6 | Fence-strip + JSON extraction before `json.loads`; add the L1 "is it really HTML/JSON" gate | `fenced_json` fixture → 1.00; prose fixture → 0.00 |
| 7 | `blend_opens` validator + `not_measured` when Blender is absent | `prose_dump` fixture → 0.00 |
| 8 | Append-only run dirs; delete the 10 invalid `scene.blend` files | `results/runs/` populated |
| 9 | `tools/sandbox_all_models.py`: timeout 900 → 3600 s, record timeout vs load failure | no more `no workdir` rows |
| 10 | Scoreboard regeneration + merge sandbox into `*-best.md` | `SCOREBOARD.md` regenerated from real runs |

Steps 1–7 are all offline and testable without a model. **Do those first**; the 12-model re-run is
only worth ~2.5 h per model once they are green.

---

## 8. What to delete

- The 10 files under `results/sandbox/blender_skyblock/*/scene.blend` — invalid, cannot be opened,
  will never be opened.
- `results/sandbox_all_models.jsonl` — 90 rows of `ok: true` that mean "the CLI exited 0".
- `results/duels/*` — the speed/TTFT fields are hardcoded zeros (`lab.py:706`).
- `results/sandbox-<task>.json` as a *history* file (it is a single overwritten file); keep the last
  one only as a convenience pointer.
- Empty `results/campaign/`, `results/deep/`.

Keep everything under `results/sandbox/` until the re-run completes — the retained model outputs are
the only evidence of how each model actually behaves.
