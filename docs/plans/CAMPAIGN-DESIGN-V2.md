# Campaign design v2 — measure the envelope, don't guess it

Replaces the fixed `min_context` / `max_context` search with a **measured capacity curve**, and
makes the whole campaign cost ~2 h instead of 13.5 h while producing *more* information.

Written 2026-11-06, after two real campaigns on the same host:

| | Q4_K_S | Q2_K |
| --- | --- | --- |
| wall time | 13.45 h (5.6 h idle) | 1.38 h |
| distinct configs at the winning ctx | 2 | 2 |
| real samples of the winner | 5 | 1 |
| contexts actually exercised | **297 prompt tokens at ctx 8192** | same |
| `gpu_ratio` tested | never sent | never sent |
| information gained | "2/6 validation rounds fail quality" | "par=1 > par=4" |

Both runs spent their time on dimensions that two independent runs proved to be **no-ops**
(`eval_batch_size`, `physical_batch_size`, `context_checkpoints`), and never tested the two
dimensions that actually decide on this hardware (usable context, GPU/CPU layer split).

---

## 1. What we are optimising (not a single number)

The user's use case: **small hardware, weak GPU, slow is acceptable (2 tok/s is fine)**. So the
output is not "the best config" — it is the **usable envelope**:

```
For this (model, host) pair, report:
  ctx_speed      largest context where decode speed is still ≥ 80 % of peak
  ctx_usable     largest context where a recall probe passes AND speed ≥ min_tok_s
  ctx_load_max   largest context that loads at all (OOM boundary)
  speed_at(ctx)  curve of tok/s vs context
  ttft_at(ctx)   curve of TTFT vs context
  best_config    per crown: speed / quality / context
```

A config at 2.0 tok/s with 32 K context is **not** a failure — it is a different operating point.
The current design throws it away via a binary `speed_floor` rejection; the new one keeps it on the
Pareto frontier and only excludes it from the *speed* crown.

---

## 2. Why `min_context` / `max_context` flags must go

Today: `advanced_settings["min_context"]` (default 2048) and `["max_context"]` (default model limit)
generate a fixed candidate list `[2048, 4096, 8192, …, 131072]`, then
`_deterministic_sample(..., 4)` picks 4 evenly spaced values and the coarse stage cross-products
them with flash/kv/batch. Consequences, all observed:

- The numbers mean nothing: `max_context` is a *guess* the user must make before the tool knows
  anything. Too low → the envelope is never found (`swift-qwen3.8-27b-q2_k` was run with
  `max_context` effectively 8192 and reported "Context: 8192"). Too high → wasted OOM loads.
- The candidate list is not adapted to the model or the host: a 4 B model and a 74 B model get the
  same ladder, although their OOM boundary differs by 10×.
- Whatever the sample picks, the **prompt is never actually that long** (§4), so even the "tested"
  contexts were never exercised.
- `min_context` has no purpose at all: the cheapest probe is always worth doing, and 2048 is
  already the smallest useful window.

**Replacement: no min/max. A cost-driven geometric ladder with bisection, bounded by measurement.**

Optional clamps stay, with honest names, for the user who wants to save time:

```
--ctx-cap 16384     # hard ceiling: never probe above this (default: model native limit)
--ctx-list 4096,8192  # manual override, bypasses discovery entirely
--budget-min 120    # total wall-clock budget; the campaign stops and reports what it did NOT test
```

The learned OOM boundary is **persisted** per `(model_id, size_bytes, host_fingerprint, gpu_ratio)`
in `data/capability/<hash>.json`, so the second campaign on the same host starts where the first
stopped instead of rediscovering it.

---

## 3. The algorithm

```
F0  CAPACITY DISCOVERY           ~10 min   (cheap probes only)
F1  OPERATING POINTS             ~40 min   (quality suite at the surviving contexts)
F2  DECODE SWEEP                 ~30 min   (the dimensions that actually move speed)
F3  VALIDATION + REPORT          ~45 min   (repeat only what can win)
                                              ────────
                                              ≈ 2.1 h per model
```

### F0 — capacity discovery (replaces both context flags)

Two ladders, one probe each. Everything is measured, nothing is assumed.

```
ladder = [2048, 4096, 8192, 16384, 32768, 65536, 131072, 262144]
ladder = [c for c in ladder if c <= min(model.context_limit or 131072, ctx_cap)]

# 0a. load ceiling — how much will the host even give us?
for ctx in reversed(ladder):                 # start at the top: one attempt answers the question
    r = load_only(ctx)                       # load + 1-token echo, ~40 s
    if r.ok: ctx_load_max = ctx; break
    remember_oom(ctx)                        # persisted, never retried for this host
# if the top loads, we are done in one attempt. If not: 262144→131072→… is O(log n) attempts.

# 0b. usable ceiling — a needle-recall + speed probe at each step
probe(ctx) -> {recall_ok, tok_s, ttft_ms, vram_gb}
    prompt = filler(ctx*0.45) + "The access code is 7-TANGO." + filler(ctx*0.45)
             + "\n\nWhat is the access code? Reply with the code only."
    max_tokens = 16, temperature = 0

ctx_usable = 2048
for ctx in ladder up to ctx_load_max:
    p = probe(ctx)                            # ~60 s at 2 tok/s
    if not p.ok or not p.recall_ok:  break     # the model cannot attend that far
    if p.tok_s < min_tok_s:          break     # below the user's floor (default 2.0)
    if p.tok_s < continue_ratio * peak_tok_s: break   # marginal rule, default 0.65
    ctx_usable = ctx; peak_tok_s = max(peak_tok_s, p.tok_s)

# 0c. bisect the boundary once or twice (2 min) so the number is within ~25 %
while hi - lo > max(2048, lo * 0.25):
    mid = (lo + hi) // 2
    p = probe(mid)
    lo, hi = (mid, hi) if (p.ok and p.recall_ok and p.tok_s >= min_tok_s) else (lo, mid)

ctx_speed = largest ctx where tok_s >= 0.8 * peak_tok_s
```

Notes that matter:

- **`recall_ok` is the real measurement.** The current suite calls its context case "long_context"
  but sends 297 tokens at ctx 8192 (§4) — so `recall` has never been tested. One 16-token probe
  answers it, and it is also the only way to detect a model that *loads* at 32 K but degrades
  (rope scaling, KV quant).
- **Cost per probe**: load 30 s (measured, `load_time_ms` = 20.8–32.5 s) + prefill + 16 tokens
  ≈ 50–60 s at 2–3 tok/s. Eight probes + 2 bisection steps ≈ 10 min.
- **`min_tok_s = 2.0`** is the user's floor and stays a *hard* floor. `continue_ratio = 0.65` is the
  *marginal* rule that stops the ladder when a doubling costs too much speed. Both configurable.
- If `ctx_load_max == ladder[0]` (cannot even load 2048), the campaign fails fast with
  `model_too_large_for_host` — 1 attempt, not 23.

Persisted result (`data/capability/<hash>.json`):

```json
{
  "model": "swift-qwen3.8-27b@q2_k", "size_bytes": 11961487904,
  "host": {"gpu": "RTX 3060 Laptop 6GB", "fingerprint": "…"},
  "curve": [
    {"ctx": 4096,  "tok_s": 3.9, "ttft_ms": 2100, "recall_ok": true,  "vram_gb": 5.7},
    {"ctx": 8192,  "tok_s": 3.6, "ttft_ms": 3640, "recall_ok": true,  "vram_gb": 5.7},
    {"ctx": 16384, "tok_s": 2.6, "ttft_ms": 6100, "recall_ok": true,  "vram_gb": 5.9},
    {"ctx": 32768, "tok_s": 1.8, "ttft_ms": 11200, "recall_ok": false, "vram_gb": 6.0}
  ],
  "ctx_load_max": 32768, "ctx_usable": 16384, "ctx_speed": 8192,
  "measured_at": "2026-11-06T20:10:00", "probes": 11
}
```

### F1 — operating points (quality only where it matters)

Take the surviving set `{ctx_speed, ctx_usable}` (at most 2, dedup) and run the **quality suite once
each**. Not 3×, not 5× — one pass. Quality is about *correctness at a context*, and correctness does
not need repetition to be plausible; it needs repetition only for the *finalist*.

```
for ctx in {ctx_speed, ctx_usable}:
    quality(ctx) -> score, per_test_details       # ~20 min at 8192 on a 27B
```

Skip a context whose speed is < `min_tok_s` (it can't be recommended anyway).

### F2 — decode sweep (the only dimensions that move the needle)

Freeze everything two runs proved to be a no-op, then sweep what is left:

```
frozen: eval_batch_size=2048, physical_batch_size=512, context_checkpoints=32, parallel=1
        flash_attention=true (KV quant requires it: observed load failure on 2 runs)
        kv_cache=GPU (kv=CPU observed load failure on 2 runs)
sweep:  gpu_ratio ∈ {auto, 0.7, 0.5}      ← via `lms load --gpu`, NEVER sent today
        ctx      ∈ {ctx_speed}            ← one context is enough for the speed crown
        × 3 repeats
        = 9 speed probes × ~90 s ≈ 15 min
```

`gpu_ratio` is the single biggest untested lever on a 6 GB card with a 12–17 GB model: it decides how
many layers sit on the GPU. The reports print `gpu_ratio | N/A | CLI/GUI-only, never sent`. The
`lms load --gpu 0.5|max|off` channel is available and the code already has a CLI load path
(`load_channel: "CLI"` in three campaigns) — it just is not part of the search space.

Stopping rule: if `auto` and `0.7` differ by less than the noise floor (6 %, measured), do not test
`0.5`; record `gpu_ratio=auto` and move on.

### F3 — validation and report (repeat only what can win)

```
finalists = top 2 by (speed crown, quality crown)   — usually the same config
for each finalist:
    3 × speed probe                     # ~5 min — establishes the noise floor
    2 × quality suite                   # ~40 min — establishes quality stability
    store n, mean, sd, pass_rate
never: 5 × full suite on a config that is not a finalist
```

Report (see §7) prints `mean ± sd (n=3)` and `quality pass rate 2/2`, never a bare number.

---

## 4. The bug that makes all of this moot if not fixed first

`benchmark/suite.py` scales the `long_context` document only when `context_length > 8192`, and even
then it inserts `---` separator lines instead of content. Measured across the whole database:

```
long_context prompt tokens:  4096 → 285    8192 → 297    32768 → 294–305
```

**57 of 57 runs never sent more than ~305 prompt tokens, at any context length.** So:

- `Context: 8192` in every report is the largest context *configured*, not exercised.
- The ctx ladder in F0 is worthless without a real needle-recall probe — which is why F0 probes
  rather than trusts `long_context`.

**Fix this before F0 or nothing above can be measured.** (Same item as brief-1 WP 2.2 / round-2 R2-7.)

---

## 5. Decision thresholds (all configurable, all recorded in the run)

| name | default | meaning | stops what |
| --- | --- | --- | --- |
| `min_tok_s` | **2.0** | hard floor: below this the config is not offered (user's tolerance) | ctx ladder, ranking |
| `continue_ratio` | 0.65 | stop escalating when the next doubling drops below 65 % of peak speed | ctx ladder |
| `speed_crown_ratio` | 0.80 | `ctx_speed` = largest ctx ≥ 80 % of peak | reporting |
| `noise_floor_pct` | 6 | same-config sd measured on this host; differences below it are not a signal | F2 stopping |
| `min_repeats` | 3 | repeats for a finalist | F3 |
| `budget_min` | 180 | wall-clock budget for the whole campaign | everything |
| `ctx_cap` | model limit | hard ceiling for the ladder (replaces `max_context`) | F0 |

When the budget runs out mid-phase, the campaign **exits cleanly and reports `not_measured`** for
everything it did not reach. Never `0.0`, never "failed".

---

## 6. What gets deleted

| removed | why |
| --- | --- |
| `advanced_settings["min_context"]`, `["max_context"]` | replaced by the ladder + `ctx_cap`; both were guesses that could only make results worse |
| `SearchSpace.context_lengths` as a cross-product dimension | context is now a *ladder with a stopping rule*, not a grid axis |
| `_generate_stage4_configs` batch/physical/parallel/checkpoint sweep | empirically a no-op, twice, on two models (§ intro table) |
| `parallel` as a search dimension for `interactive` | it is a policy: `parallel = 1` |
| `validation_repetitions = 5` full suites | replaced by 3 speed probes + 2 quality suites |
| `reps == 1 ⇒ cache eligible` | a replayed measurement is not a measurement |
| the empty `## Contexts (measured, not assumed)` section | replaced by a measured curve table |

Kept: `num_experts` (real for MoE, and the 74B/35B-A3B models need it), `kv_cache` placement (real
when VRAM-tight, but largely forced by the KV quant setting), `gpu_ratio` (promoted from "never sent"
to a first-class lever).

---

## 7. The report the user actually needs

```
# swift-qwen3.8-27b@q2_k  ·  RTX 3060 Laptop 6 GB  ·  2026-11-06

Capacity (measured, 11 probes, 10 min)
  ctx    tok/s   TTFT     recall   quality   VRAM    verdict
  4096   3.9     2.1 s    3/3      0.997     5.7 GB  fastest
  8192   3.6     3.6 s    3/3      0.997     5.7 GB  ← speed crown
  16384  2.6     6.1 s    3/3      —         5.9 GB  ← max usable
  32768  —       —        fail     —         6.0 GB  loads, recall fails

Recommendation
  Daily use ......... ctx 8192, parallel 1, 3.6 tok/s, first token 3.6 s
  Long documents .... ctx 16384, 2.6 tok/s (still above your 2.0 floor)
  Not usable ........ above 16384: the model loads but cannot recall content

Load configuration
  context 8192 · flash on · KV on GPU · batch 2048 · phys 512 · parallel 1 · checkpoints 32
  gpu_ratio auto (0.7 and 0.5 measured within noise)
  n=3 · 3.61 ± 0.14 tok/s · quality 2/2 validation rounds passed

Not measured
  ctx 24576+ (budget), gpu_ratio 0.3 (dominated)
```

---

## 8. Implementation packages for OpenCode

Prerequisite: **brief-1 WP 2.2 / round-2 R2-7** (the `long_context` scaling bug). Without it every
number below is fiction.

### WP C1 — capacity discovery (replaces the context flags)

*Files:* `services/search_space.py` (`_generate_context_candidates`), new `services/capacity.py`,
`services/benchmark.py` (a `probe` entry point), `domain/run.py` (`advanced_settings` keys).

*Change:* implement §3 F0 exactly. Delete `min_context`/`max_context` from the default path; keep
them accepted-but-deprecated (log a warning that maps them to `ctx_cap`). Persist the curve to
`data/capability/<hash>.json`. Add `--ctx-cap`, `--ctx-list`, `--budget-min`.

*Acceptance:*
- a unit test with a fake client where load succeeds ≤ 16384 and fails at 32768 →
  `ctx_load_max == 16384` in ≤ 4 load attempts;
- a fake client where recall fails at 16384 → `ctx_usable == 8192`, and no probe above 16384;
- re-running the same model on the same host does **0** OOM loads (reads the cache);
- `--ctx-cap 8192` never probes above 8192.

### WP C2 — the recall probe (this is what makes "context" real)

*Files:* `benchmark/suite.py` (new case kind), `services/benchmark.py`.

*Change:* deterministic needle test — filler to 2 × 45 % of the target, needle at the middle, 16
output tokens, temperature 0. Pass = the answer contains the exact needle token; fail = anything else
(including a plausible-looking wrong code). Record `prompt_tokens` and assert
`prompt_tokens >= 0.6 * ctx`.

*Acceptance:* at ctx 8192 the probe's `prompt_tokens >= 4900`; a model that repeats the needle
passes; an empty/evasive answer fails; runtime ≤ 60 s on a 3 tok/s model.

### WP C3 — the decode sweep that replaces stage 4

*Files:* `services/orchestration/optimizer.py` (`_stage_batch_optimization`,
`_generate_stage4_configs`), `services/search_space.py`.

*Change:* freeze batch=2048, phys=512, ck=32, par=1, flash=on, kv=GPU (constants with a comment
citing the two campaigns). Sweep `gpu_ratio ∈ {auto, 0.7, 0.5}` through the **CLI** channel
(`lms load --gpu`), 3 repeats of the **speed probe** (not the suite), stop early when the first two
are within `noise_floor_pct`.

*Acceptance:* an interactive run produces ≤ 9 speed probes and **zero** full suites before F3;
`gpu_ratio` appears in the tested-configs table with a real measured value.

### WP C4 — noise-aware finalisation

*Files:* `optimizer.py` (`_stage_validation`), `services/reporting.py`.

*Change:* F3 exactly — 3 speed probes + 2 quality suites per finalist, store `mean`, `sd`, `n`,
`quality_pass_rate`; refuse to print a bare quality/speed number when `n < 2` ("single sample —
not a stability claim"); a config whose `sd / mean > 0.25` is flagged `unstable` and cannot be a crown.

*Acceptance:* report shows `3.61 ± 0.14 tok/s (n=3)`; a synthetic high-variance config is flagged
`unstable`; `stability` is `None` when `n=1`.

### WP C5 — the capacity table in the report + `check_run_integrity` additions

*Files:* `services/reporting.py`, `tools/check_run_integrity.py`.

*Change:* print §7's table; add integrity checks: `probe count ≥ 5`, `ctx_usable ≥ 4096`,
`recall_ok` present for every probed ctx, `prompt_tokens ≥ 0.6 × ctx`, budget respected
(no phase may overrun its allocation by > 20 %).

*Acceptance:* `python tools/check_run_integrity.py --run <new>` shows the curve and no FAIL.

### WP C6 — cost model (so the budget is real)

*Files:* round-2 R2-3 (phase timings) must land first.

*Change:* after each phase, extrapolate: `remaining_phases × measured_cost_per_unit`, and skip a
phase whose estimate exceeds the remaining budget instead of starting it. Record skipped phases as
`not_measured` with the reason.

*Acceptance:* a campaign with `--budget-min 60` on a slow model completes its F0+F2 and reports
`F1/F3 not_measured (budget)`, exit code 0.

---

## 9. What this costs on this hardware (measured inputs)

Inputs: load 30 s, speed probe 90 s, quality suite ~20 min at ctx 8192 on a 27B, speed 2.6–3.9 tok/s.

| phase | work | cost |
| --- | --- | --- |
| F0 capacity | 8 probes + 2 bisection | **~10 min** |
| F1 quality | 2 suites | **~40 min** |
| F2 decode sweep | 9 speed probes | **~15 min** |
| F3 validation | 3 probes + 2 suites | **~45 min** |
| **total** | | **≈ 1 h 50 min** |

Compare: 13.45 h for the Q4 campaign, of which 5.6 h was idle and ~6 h was the same configuration
re-measured. **The new design costs 13 % of the old wall time and answers three questions the old one
could not**: what context is usable, whether the GPU split is right, and whether the winner is stable.

If the budget is tight, the first 25 minutes alone (F0 + F2) already answer "what can this machine
do with this model", which is the question most runs are actually asking.
