# OpenCode fix round 2 — findings from run `e70e5e40` (Q2_K, 2026-11-06)

> Paste as the task. This **amends** `docs/plans/OPENCODE-TASK-BRIEF.md`: the packages below are
> higher priority than the ones they overlap, and two of them are new. Everything here is measured
> from a real run that completed on this machine — no estimates, no assumptions.

---

## 0. What happened, in one paragraph

The user re-ran `swift-qwen3.8-27b@q2_k` after the first review. The run is a **big improvement**:
19 configurations instead of 1, a real winner (`ctx 8192, batch 2048, phys 512, parallel 1` →
**3.6 tok/s**, TTFT 3640 ms, quality 0.997), 83 min instead of 21 min of nothing, and `parallel=1`
discovered as a genuine win over LM Studio's default of 4. But the run also **reproduced the cache
bug in the most visible possible way** (5 "independent" validation rounds with identical TTFT to the
millisecond), it **never finalised in the database** (the report says `success`, the DB says
`running`), and 87 % of the wall time per configuration is still unattributed. Fix these before
trusting any number this tool prints.

**Do not start the sandbox work here.** This round is measurement integrity + time accounting only.

---

## 1. Ground rules

Same as `OPENCODE-TASK-BRIEF.md` §1, plus:

- **Do not "fix" the cache by deleting it.** The user's history must stay reproducible. Fix the
  eligibility rule and the reporting; add a flag.
- **Do not change the winner of any historical run.** These fixes change *what future runs report*,
  not past data.
- Every package below needs a test that fails on the current code. If you cannot write one, say so
  and stop that package.
- Run `python tools/check_run_integrity.py --run e70e5e40` before and after; the number of FAIL lines
  must go down and never up.

---

## WP R2-1 — Cache replay is visible in the output (P0, proven)

**Evidence.** `results/swift-qwen3.8-27b-q2_k-best.md`, tested-configurations table, rows 18–23:

```
18 | 8192 | 2048 | 512 | 1 | 3.6 | 19 | 3640 | 5.7 | 0.997
19 | 8192 | 2048 | 512 | 1 | 3.6 | 19 | 3640 | 5.6 | 0.997
20 | 8192 | 2048 | 512 | 1 | 3.6 | 19 | 3640 | 5.6 | 0.997
21 | 8192 | 2048 | 512 | 1 | 3.6 | 19 | 3640 | 5.6 | 0.997
22 | 8192 | 2048 | 512 | 1 | 3.6 | 19 | 3640 | 5.6 | 0.997
23 | 8192 | 2048 | 512 | 1 | 3.6 | 19 | 3640 | 5.6 | 0.997
```

Six measurements of one configuration cannot share a TTFT of exactly **3640 ms**. The run's
`benchmark_repetitions` is `1`, so `cache_eligible = reps == 1` (`benchmark.py:701`) is `True`, and
the five validation rounds were served from `data/benchmark_cache/`. The "beautifully stable"
validation block is one measurement copied five times.

**Change.**

1. `services/benchmark.py`
   - `cache_eligible = reps == 1 and cache_reads_enabled()`.
   - Tag every served-from-cache metric: set `from_cache=True` on the `BenchmarkMetrics` instance
     and keep it through `_aggregate_results` (aggregate `from_cache_all` when every sample came from
     cache; `from_cache_some` otherwise).
   - Persist `generation["cache_hits"]` / `generation["cache_misses"]`.
2. `services/benchmark_cache.py`
   - Default reads **off**; honour `LM_OPTIMIZER_BENCHMARK_CACHE_RW=off|on` (default `off`).
   - Add `host_fingerprint` and `ttl_days` to the key (see brief 1, WP 1.1).
3. `services/orchestration/optimizer.py`
   - **Refuse to use cached data for a validation round**: pass `repetitions=1` *and*
     `allow_cache=False` (new parameter) for `_stage_validation`, so validation always measures.
     Validation is the only place where a replay destroys the meaning of the result.
   - If any round in `_stage_validation` came from cache, log a warning and mark the run
     `validation_from_cache=True`.
4. `services/reporting.py`
   - In "Tested configurations", append `· cached` to the row when `from_cache_all`.
   - In "Winner typical across identical runs", if fewer than 2 rounds were *measured*, print
     `single measurement — no stability claim` instead of a median.
   - In `stability` scoring, return `None` (not a number) when `n < 2` real measurements exist.

**Acceptance.**

```
test_validation_rounds_are_measured:
    with a pre-populated cache for the winner's exact config,
    _stage_validation runs validation_repetitions times,
    and the resulting TTFT values are NOT all identical
    (assert len(set(ttft_ms)) >= 2, or assert cache_hits == 0).

test_cache_off_by_default:
    with LM_OPTIMIZER_BENCHMARK_CACHE_RW unset, a reps=1 run reports cache_hits == 0.
```

And on a fresh run: `check_run_integrity.py` must no longer warn
`benchmark_repetitions=1 -> the benchmark cache was eligible`.

---

## WP R2-2 — The run never finalises in the database (P0, new)

**Evidence.**

```
$ python -c "...select from runs where id like 'e70e5e40%'"
stage=final_validation  status=running  created=2026-11-06T17:15:35  completed_at=None  duration=0
```

while `results/swift-qwen3.8-27b-q2_k-best.md` says:

```
- Run: e70e5e40-3194-488d-8ffa-39f3932a1350 (status: success)
- Elapsed: 4971.6s
```

and lists 23 tested configurations, whereas the DB holds 19 rows. The report was rendered from
in-memory state and **the run row was never committed**. Consequences:

- `check_run_integrity.py` sees a half-written run (elapsed 0, `validation: 1/1`, Pareto empty).
- A `--resume` would consider the run unfinished and redo work.
- `best_config_id`, `pareto_config_ids_json`, `completed_at` are all unset, so every downstream
  consumer (API, `build_scoreboard.py`, `*-best.md` regeneration) reads a different truth than the
  file on disk.

**Change.** In the orchestrator's stage loop / CLI entry point:

1. Persist **before** rendering: `status`, `completed_at`, `duration_seconds`, `stage=COMPLETE`,
   `best_config_id`, `pareto_config_ids_json`, `search_space` (with the speed-floor block), and any
   custom `benchmark_params` — then, and only then, write `*-best.md`.
2. Wrap the run in `try/finally` so an exception still persists `status=failed` + `error` +
   `completed_at`. A killed process must not leave `running` behind.
3. On start-up, reconcile: a run with `status=running` and no live process older than N minutes is
   marked `interrupted` (there is already `services/run_reconcile.py` — extend it, don't duplicate).
4. Make the report header read `status` from the **persisted** row, not from the in-memory object.

**Acceptance.**

```
test_run_is_finalised_before_report:
    after run(), the DB row has completed_at IS NOT NULL, status == "success",
    pareto_config_ids_json != [], duration_seconds > 0,
    and the number of configurations in the DB equals the number of rows in the report table.

test_exception_still_finalises:
    a generate() that raises on the last stage leaves status == "failed" (not "running").
```

Add to `tools/check_run_integrity.py`: **FAIL** when
`run.status == "running" and run.completed_at is None and a *-best.md exists for that model**.

---

## WP R2-3 — Account for the wall time (P0, new; this is where the hours are)

**Evidence.** Per configuration at ctx 8192, from the DB. Measured generation time vs block duration:

| run | block | generation | unattributed |
| --- | --- | --- | --- |
| Q4_K_S config 19 | 3859 s | 616 s | **3243 s (84 %)** |
| Q4_K_S config 22 | 4728 s | 623 s | **4105 s (87 %)** |
| Q2_K config 19 | 1198 s | 383 s | **815 s (68 %)** |

Load is only 30 s (`load_time_ms` = 32 514 / 20 805 ms), preheat 5–7 s, prefill ~5 s per case. So
**12–68 minutes per configuration are spent somewhere nobody records**. Every campaign estimate in
`results/*-best.md` is therefore unexplainable, and there is no way to know whether the fix is
"don't reload", "don't re-verify", or "the disk is thrashing".

**Change.**

1. Introduce a `PhaseTimer` (context manager) in `services/benchmark.py` and time every phase of one
   configuration: `unload`, `load`, `verify`, `preheat`, `per_case_prefill`, `per_case_generation`,
   `score`, `aggregate`, `persist`.
2. Store it as `generation["phase_timings_ms"]` and also as `duration_ms` on the configuration row
   (this also fixes WP 1.2: 17 of 19 rows were `0`).
3. Add an assertion in `check_run_integrity.py`: for each configuration,
   `sum(phase_timings_ms) >= 0.9 * duration_ms`. If not, FAIL with the missing milliseconds.
4. Log the top-3 slowest phases per configuration at INFO level so the campaign log explains itself.

**Acceptance.** On a fresh run, every configuration's phase timings sum to ≥90 % of its
`duration_ms`, and `check_run_integrity.py` shows no `unattributed` FAIL. Report the phase
breakdown in the PR description — it will tell us which of the three hypotheses is true.

---

## WP R2-4 — `parallel = 1` is a policy, not a search dimension (P1, revises brief-1 WP 2.3)

**Evidence.** This run swept `parallel` 4× at ctx 4096 with `eval_batch_size`/`physical_batch_size`/
`context_checkpoints` mixed in — 16 configurations, results `1.4, 2.5, 2.2, 2.5, 2.0, 2.8, 2.1, 2.2,
2.5, 2.2, 1.8, 2.4, 2.4, 2.7, 2.5, 1.5` tok/s. When the measurement was final (ctx 8192), the winner
was `parallel=1`:

```
16 | 4096 | 2048 | 512 | 4 | 2.4   (noise)
14 | 4096 | 2048 | 512 | 1 | 2.7   ← best of the block
16 | 4096 | 2048 | 512 | 8 | 1.5   ← worst
18 | 8192 | 2048 | 512 | 1 | 3.6   ← actual winner
```

LM Studio defaults to `parallel=4`. For a single-user chat this allocates four KV slots that nobody
uses and measurably costs 10–15 %. The optimizer spent 16 configurations to rediscover a constant.

**Change.**

1. `domain/models.py` (or wherever `LoadConfiguration` defaults live): for
   `workload_type == "interactive"`, default `parallel = 1`.
2. `search_space._generate_parallels`: return `[1]` for interactive — **and remove the code path in
   `_stage_micro_refinement` that re-expands the list to `[1,2,4,8]`** (it currently overrides the
   workload policy).
3. Keep the sweep only for `workload_type == "throughput"`, where it is the point of the exercise.
4. Log once per run: `parallel fixed at 1 (interactive workload; pass --parallels to override)`.

**Acceptance.** For an interactive run, the tested-configurations table contains exactly one value
of `parallel`, and it is `1`. `check_run_integrity.py`'s
`N configurations differ only in (...)` WARN disappears.

---

## WP R2-5 — Kill the cold-first-configuration artefact (P1, new)

**Evidence.** Same run, same config, ctx 4096: **config 1 = 1.4 tok/s**, configs 2–16 = 2.1–2.8 tok/s.
Q4 showed the same pattern (1.61 first, 1.7–2.4 after). The first measurement of every campaign is
systematically ~40 % slower, and it is the *baseline* the report compares against
(`Baseline generation: 1.6 tok/s` in `swift-qwen3.8-27b-q4_k_s-best.md`).

**Change.**

1. Before the first measured configuration, run one throwaway **burn-in** `run_benchmark` on the
   default config with `repetitions=1` whose metrics are discarded, so the page cache and CUDA
   context are warm. Record its duration as `generation["burn_in_ms"]`.
2. Increase the preheat so it actually touches all weights and the KV cache:
   `PreheatConfig(max_tokens=128, repetitions=2)` (`preheat.py:49-54` currently does 30 tokens once
   of "Say hi in 5 words").
3. Record `warm_state` (`cold`/`warm`) per configuration — `cold` when it is the first after a fresh
   load with no burn-in.
4. Do **not** use a `cold` measurement as the run baseline; if no `warm` measurement exists, the
   baseline fields stay `None`.

**Acceptance.** In a fresh run, the first configuration's tok/s is within 20 % of the run's median
(a unit test can simulate the warm/cold distinction with a fake client).

---

## WP R2-6 — A winner with n=1 must not claim quality or stability (P1)

**Evidence.** This run's report prints

```
- Quality: 0.997 (30/30 checks)
- Verdict: winner of 23 tested (non-inferiority band, profile balanced)
```

with `benchmark_repetitions: 1` and 5 replayed validation rounds — i.e. **one real sample**. Compare
Q4, which had 5 real rounds and honestly reported a 4/5 pass rate that the report then hid.

**Change.**

1. `reporting.py`: when `n_measured < 2`, print `Quality: 0.997 (single sample — not a stability
   claim)` and omit `stability` from the score breakdown (weight redistributed, not zeroed silently).
2. `optimizer`: set `run.validation_repetitions_effective` = number of rounds that were actually
   measured, and store it. The report reads that number, never the requested one.
3. Add a hard rule: a run whose winner has `n_measured < 2` cannot be `status=success` — it is
   `success_single_sample`, and the CLI prints a one-line warning with the exact re-run command.

**Acceptance.** Unit test: one measured round → report contains `single sample` and no stability
component; two measured rounds → normal output.

---

## WP R2-7 — `long_context` is still 297 tokens at ctx 8192 (P1, carry-over)

**Evidence.** This run, config 19 (`ctx=8192`): `long_context` `prompt_tokens = 297`, i.e. **4 % of
the window**. Confirmed again in `check_run_integrity.py`:

```
FAIL  long_context at ctx=8192 used only 297 prompt tokens (4% of the window)
```

57 of 57 runs in the database are affected. `Context: 8192` in the report is the largest context
*tried*, not a measured ceiling.

**Change.** Exactly brief-1 WP 2.2 (scale the document to ~80 % of the window, assert
`prompt_tokens >= 0.6 * ctx`, add a needle-recall case). Do not defer it again: without it, `Context`
and `maximum stable context` are unmeasured claims in every report the tool has ever produced.

**Acceptance.** At `ctx=8192`, `long_context.prompt_tokens >= 4900`. The report's context section
names the measured prompt size next to the number.

---

## WP R2-8 — The empty `## Contexts (measured, not assumed)` section (P2, new)

**Evidence.** In `results/swift-qwen3.8-27b-q2_k-best.md`:

```
## Contexts (measured, not assumed)

## Recommended generation settings (per chat request, not load)
```

The header is printed with no body. `_context_trio` (`reporting.py:669`) returned all `None`, and the
renderer emits the heading unconditionally.

**Change.** Emit the section only when at least one of the three values is known; otherwise print
`Contexts: not measured (only one context length was tested)`. Add a golden-file test for the report
renderer covering the empty case.

---

## WP R2-9 — `presence_penalty: 1.5` is still being recommended (P2, carry-over)

**Evidence.** Same file:

```
- presence_penalty: 1.5
- Source: Qwen3.5 official (HF discussion #51, instruct-general)
```

for `swift-qwen3.8-27b@q2_k` — a Qwen**3.8** model. `generation_defaults.py:16` matches the Qwen3.5
entry through the architecture token `qwen35` (which LM Studio reports for Qwen3.8 as well) before
the `match: ["qwen3.8"]` entry can apply.

**Change.** Match model id first, architecture as an exact token second (brief-1 WP 3.3).

**Acceptance.** `swift-qwen3.8-27b@q2_k` and `@q4_k_s` both report `presence_penalty: 0.0` with the
Qwen3 source string.

---

## 2. Order, and why

| PR | packages | rationale |
| --- | --- | --- |
| A | R2-1, R2-2 | A run that replays measurements and never persists is not evidence |
| B | R2-3 | You cannot cut hours you cannot account for; this makes the next decision data-driven |
| C | R2-4, R2-5, R2-6 | Removes 16 configs, fixes the baseline, stops n=1 claims |
| D | R2-7 | Makes `Context` a measurement |
| E | R2-8, R2-9 | Reporting correctness |

After PR A, re-run the same model with `--preset standard` and compare against `e70e5e40`. Expected:
**fewer configurations, longer wall time, and a completely different validation block** — that
difference is the bug you removed, so state it in the PR.

---

## 3. Definition of done for this round

```
python -m pytest tests lm_optimizer/tests -q            # green
python tools/check_run_integrity.py --run <new run>     # zero FAIL
```

and on the new run's report:

1. every validation round has a **different** TTFT (or the report says `single measurement`),
2. `Quality` carries either a pass rate over ≥2 measured rounds or an explicit single-sample caveat,
3. `Contexts` prints real numbers or an explicit "not measured" line,
4. exactly one `parallel` value appears, and it is `1`,
5. `duration_ms` is non-zero on every configuration, and phase timings sum to ≥90 % of it,
6. the DB row has `status=success`, `completed_at` set, and `pareto_config_ids_json` non-empty,
7. the report's configuration count equals the DB's row count for that run.

---

## 4. Report back with

- the phase-timing breakdown for one ctx-8192 configuration (this is the most valuable artefact of
  the round — it tells us where the 68–87 % goes),
- before/after for: configurations tested, wall time, validation distinctness, `duration_ms` coverage,
- anything in this brief that turned out to be wrong, stated plainly rather than worked around.
