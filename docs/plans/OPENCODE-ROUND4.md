# OpenCode — round 4: fix the benchmark ceiling, Blender fairness, and the optimizer's empty search

> Paste as the task. Everything below is **verified on this machine (Randall) on 2026-11-17**
> by running the real artifacts, not by reading code. Each work package has the exact evidence,
> the change, and an acceptance test. Work top-down, one package per PR.

---

## 0. Verified state — do not redo these

Already working, confirmed this round:

| item | proof |
| --- | --- |
| `/api/sandbox/files` URLs in the WebUI | all 6 call sites now use `/api/...` (`sandbox.js:123,528,535,571,578`, `history.js:255`) |
| formatted text/JSON artifact preview | `routes.py:2328-2330` wraps non-HTML in `<pre>` |
| `not measured` instead of fake 0 | 12 rows in `results/bakeoff/runs.jsonl` |
| `load_s = None` instead of 30.0 | bakeoff summaries 20261112+ |
| pixel-based `renders_content` | `services/render_check.py` + `services/png_stats.py`; caught `prism-ml/bonsai` minecraft = blank |
| `long_context` really long | optimizer run `4ac063c0`: `prompt_tokens=4125` at ctx 8192 (was 297) |
| Blender located | `blender_locate.find_blender()` → `C:\Program Files\Blender Foundation\Blender 5.3\blender.exe` |
| `city_mesh_count` / `city_height_variety` / `city_footprint` validators registered | `sandbox_runner.py:619-627` |

**Do not touch** those. The problems below are what remains.

---

## WP R4-1 — `no_repeated_paragraphs` caps every long document at 0.91–0.93 (P0)

**Evidence.** `deep_research_report` scored 0.91–0.93 for **four of six models**, with one model at
0.913 because of a *single* repeated paragraph:

```
google/gemma-4-26b-a4b-qat      0.9348  crit=[]
swift-qwen3.8-27b               0.9348  crit=[]
nvidia-nemotron-3.5-bolt-e4b    0.9348  crit=[]
mirothinker-v1.5-30b            0.9348  crit=['no_repeated_paragraphs (paragraphs=15 repeats=6 looped_tail=False)']
nvidia-nemotron-3.5-bolt-74b    0.9130  crit=['no_repeated_paragraphs (paragraphs=12 repeats=1 looped_tail=False)']
```

`sandbox_lab.py:1310` builds the duplicate key from the **first 12 words** and requires
`repeats == 0`, while the check is `critical=True` (`:703`). One shared line — a caption, a
"Sources" line, a repeated bullet — fails the whole task. After tag-stripping, headings and short
lines collide easily.

**Change.**

```python
# lm_optimizer/services/sandbox_lab.py:1310
elif check.name == "no_repeated_paragraphs":
    combined = "\n".join(files.values())
    text = re.sub(r"<[^>]+>", " ", combined)
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    # headings, captions and one-line list items are not "repeated paragraphs"
    candidates = [p for p in paragraphs if len(p.split()) >= 20]
    seen, repeats = set(), 0
    for p in candidates:
        key = " ".join(p.lower().split()[:20])          # 12 -> 20 words
        if key in seen:
            repeats += 1
        seen.add(key)
    looped = text[-200:].strip().lower() == text[:200].strip().lower() and len(text) > 400
    allowed = max(1, len(candidates) // 10)              # 10 % tolerance
    ok = repeats <= allowed and not looped
    detail = (
        f"paragraphs={len(candidates)} repeats={repeats} "
        f"allowed={allowed} looped={looped}"
    )
```

Also set `critical=False` on both definitions (`:633` essay task, `:703` deep_research_report):
this is a quality signal, not a correctness gate.

**Acceptance.**
- Unit test: 15 paragraphs of 30 words, one duplicated → `pass`, `repeats=1 allowed=1`.
- Unit test: 10 identical paragraphs repeated 5× → `fail` (real loop).
- A real `deep_research_report` run on `e4b` must reach ≥ 0.98 (it is 0.9348 today).

---

## WP R4-2 — a result can be `score=1.0` **and** carry a critical failure (P0)

**Evidence.** `swift-qwen3.8-27b` / `vision_objects_living_room`:

```
score=1.0  crit=['counts_three_dogs (miss)']  tok=637
```

A report that says "1.0" and "critical: counts_three_dogs (miss)" is unusable. Commit `02eda70`
("clear stale critical failures after a repaired success") did not cover this path.

**Change.** In `sandbox_runner.py` after `score_attempt` (around `:663-716`), enforce the invariant
in code rather than by comment:

```python
if passed and critical:
    logger.error(
        "passed with critical failures - clearing",
        task=self.task.id, critical=critical,
    )
    critical = []          # a passed attempt cannot carry critical failures
if score >= 0.999 and critical:
    passed = False         # a perfect score with a critical failure is a bug, not a pass
    score = min(score, 0.99)
```

And add the check to `tools/check_run_integrity.py`: for every bakeoff row,
`FAIL if final_score >= 0.999 and critical_failures`.

**Acceptance.** No row in a new bakeoff has `score == 1.0` together with a non-empty
`critical_failures`. `vision_objects_living_room` on swift reports either `1.0` with no criticals,
or a score < 1.0 that explains the dog count.

---

## WP R4-3 — `blender_city` is unfair: models target Blender 3.x/4.x API on a 5.3 install (P0)

**Evidence — three real runs, three different reasons, none produced a `.blend`:**

```
20261116_124537  AttributeError: bpy_struct: attribute "name" from "Collection" is read-only
                 -> scene.collection.name = 'City_Collection'
20261116_122348  TypeError: 'module' object is not callable
                 -> bpy.ops.camera_add(...)          (correct: bpy.ops.object.camera_add)
20261116_123708  SyntaxError: unmatched ')'
```

The task prompt (`sandbox_lab.py`, `BLENDER_CITY_TASK`) **never states the Blender version**, so
models emit pre-5.x idioms that break. The harness is correct to fail them; the task is unfair.

**Change.**

1. **State the target in the prompt**, at the top:

   > Target environment: **Blender 5.3, `bpy` Python API, headless**
   > (`blender --background --python build_scene.py`). Blender 5 notes:
   > `bpy.context.scene.collection` is read-only — create a new collection and link it;
   > the camera op is `bpy.ops.object.camera_add`, the light op `bpy.ops.object.light_add`.

2. **Ship a known-good skeleton in the task prompt** (verified working on 5.3 this round — it
   produced a 97 KB, zstd-compressed `scene.blend`):

```python
import bpy, math
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
root = bpy.data.collections.new("City")
bpy.context.scene.collection.children.link(root)   # master collection stays unnamed

def cube(name, loc, scale, coll):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    ob = bpy.context.object
    ob.name = name
    ob.scale = scale
    for c in list(ob.users_collection):
        c.objects.unlink(ob)
    coll.objects.link(ob)
    return ob

bpy.ops.object.camera_add(location=(30, -30, 25))
bpy.context.scene.camera = bpy.context.object
bpy.ops.object.light_add(type='SUN', location=(10, 10, 30))
bpy.ops.wm.save_as_mainfile(filepath="scene.blend")
```

3. **Blender version must be recorded** in the attempt manifest (`blender_version`) and printed in
   the report, so a 5.3-vs-4.2 difference is never silent again.

**Acceptance.** After the prompt change, at least one model produces a `scene.blend` that passes
`blend_is_binary` (`looks_like_blend`), i.e. ≥ 16 KB and `BLENDER` or zstd-with-BLENDER payload.
If none do, print the exact traceback tail from `blender.log` in the report — never a bare `0.00`.

---

## WP R4-4 — coverage is uneven and vision is silently skipped (P0)

**Evidence.** Newest run per (model, task):

| model | tasks measured | of 24 |
| --- | --- | --- |
| swift-27b | 13 | 13 |
| nemotron-74b | 13 | 13 |
| gemma-26b | 9 | 9 |
| gpt-oss-20b | **5** | 5 |
| e4b | **4** | 4 |
| mirothinker | **3** | 3 |

A mean over 3 tasks (mirothinker 0.964) is printed next to a mean over 13 (swift 0.972) as if
comparable. And the vision row is absent — not marked — for models that **cannot** do vision at all.
Confirmed by the files on disk: `mmproj-*.gguf` exists only for **74b (1.7 GB), gemma (1.2 GB),
swift (0.9 GB)**. **e4b, gpt-oss-20b and mirothinker have no vision projector.**

**Change.**

1. `services/model_eligibility.py` (or a new helper): `has_vision(model_id)` = an `mmproj-*.gguf`
   exists in the model's directory.
2. The bakeoff writes a row for **every** model × task with an explicit outcome:
   `measured` | `not_measured` (run failed) | `not_applicable` (no vision projector) |
   `skipped` (out of budget).
3. Summaries print `passed / applicable` (not `passed / attempted`) and a `coverage` column.
4. **Never** include `not_applicable` rows in the mean.

**Acceptance.** A bakeoff summary shows `e4b 4/10 applicable (6 not applicable: vision)` and
`swift 13/13`. Means are only printed with their `n`.

---

## WP R4-5 — vision tasks are unstable for the same model (P1)

**Evidence.** `vision_dense_city_traffic`, newest scores per run, same weights:

```
gemma-26b   0.6279 -> 0.8478
nemotron-74b 0.7209 -> 0.7826
swift-27b   0.7209 -> 1.0000
```

Same model, same image, different score. Either the thresholds moved (commit `3ab882c` relaxed them)
or the generation is not deterministic.

**Change.** Pick one and document it:

- **Option A (preferred):** run vision tasks 3× at temperature 0 and report the **median** plus
  `min/max`. Cost: 3× the slowest tests — the vision suite is 0.2–2.7 tok/s, so cap it: run 3× only
  for tasks whose first pass is within 0.15 of the pass threshold.
- **Option B:** mark all `vision_*` tasks `experimental=True`; print them in a separate block and
  exclude them from any mean or ranking.

Either way, **score rows must carry the task-definition version** so a threshold change cannot be
mistaken for a model change.

**Acceptance.** Two consecutive runs of the same model on `vision_dense_city_traffic` produce the
same score, or the report shows `median 0.72 (0.63–0.85, n=3)`.

---

## WP R4-6 — the optimizer's search returns the default config for every model (P0)

**Evidence.** Three different architectures, three "successful" runs, **one identical winner**:

```
gemma-26b      ctx 8192  flash on  KV-GPU  batch 2048  phys 512  par 4   24 configs   6.2 h
nemotron-74b   ctx 8192  flash on  KV-GPU  batch 2048  phys 512  par 4   25 configs   8.8 h
e4b            ctx 8192  flash on  KV-GPU  batch 2048  phys 512  par 4   41 configs   1.3 h
```

That is LM Studio's default. 24–41 configurations per model bought nothing model-specific.
Also: `e4b` finished with `quality = 0.9116` while the run row stores `quality_threshold = 0.98`,
yet `status = success` — the gate is not enforcing the recorded threshold.

**Change.**

1. **Delete the stage-4 sweep for interactive loads** (same reasoning that produced three identical
   winners): freeze `eval_batch_size=2048`, `physical_batch_size=512`, `context_checkpoints=32`,
   `parallel=1`; no configuration may differ only in those four fields.
2. **Promote `gpu_ratio`** to a first-class dimension via the CLI channel
   (`lms load --gpu 0.5|0.7|max`): it is the only lever that changes how many layers sit on a 6 GB
   card. Sweep `{auto, 0.7, 0.5}` with 3 speed probes each, early stop when two agree within 6 %.
3. **One quality threshold.** `optimizer.py:4690` prints `self.quality.config.minimum_score` but the
   comparison used a different value. Make `passes_threshold` the single decision point and print the
   number it enforced. If `quality < threshold` the run cannot be `success` — it is
   `completed_no_validated_winner`, as it was before.

**Acceptance.**
- A new run on any model shows **at most 9 speed probes** in that stage and ≥ 1 configuration with a
  `gpu_ratio` different from `auto`.
- No two models produce an identical winner config unless that is genuinely the measured optimum —
  and the report states which dimension was tuned.
- `e4b`-style mismatch cannot occur: `quality 0.9116` with `threshold 0.98` must end
  `completed_no_validated_winner`.

---

## WP R4-7 — report what the user actually asks (P1)

For each model the final report must answer "what is this model good for", so print, next to the
score, the three facts the choice depends on:

1. **speed** — median tok/s on the two cheapest tasks (e.g. `email_write`, `company_website`);
   `e4b 45–50`, `swift 1.2–4.8`, `74b 0.6–3.0`, `gpt-oss 7–9`, `gemma 0.2–3.4`.
2. **capability flags** — `vision: yes/no`, `thinking: yes/no` (from `thinking_chars`),
   `context tested: <measured, not configured>`.
3. **failure modes** — reasoning leaked into the artifact, empty render (pixel verdict), missing
   subject line. These are the reasons a model is unusable in practice, and they are already
   detected; they are just not summarised.

**Acceptance.** `results/bakeoff/summary_*.md` gains a "Fit" table:
`model | tok/s | vision | text score | vision score | known failure modes`.

---

## Definition of done

1. `python tools/selfcheck_sandbox.py` → exit 0.
2. `python tools/check_run_integrity.py --all` → no *new* FAIL kinds (historical rows may still fail).
3. A fresh `deep_research_report` run on `e4b` scores ≥ 0.98 without a repeated-paragraph critical.
4. `blender_city` either produces a valid `scene.blend` on at least one model, or every row carries
   `not_measured` + the Blender traceback tail — never a silent `0.00` after 80 minutes.
5. A bakeoff summary prints coverage per model and never averages `not_applicable` rows.
6. A new optimizer run prints ≤ 9 stage-4 probes, at least one non-default `gpu_ratio`, and its
   `status` agrees with its recorded `quality_threshold`.

---

## Report back with

- the diff of `no_repeated_paragraphs` + the two unit tests, and the new `deep_research_report` score;
- whether any model produced a real `.blend` after the Blender 5.3 prompt change, and with which
  error message the others failed;
- the coverage table after WP R4-4 (`applicable` per model);
- the new optimizer run's tested-config table (how many probes, which `gpu_ratio` won);
- anything in this brief that turned out to be wrong — say it plainly, do not work around it.
