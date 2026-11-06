# OpenCode task brief — make the optimizer trustworthy, fast, and honest

> Paste this file's contents as the task. Work top-down. Stop after each **work package**,
> run its acceptance commands, and report what changed. Do not batch all packages into one PR.

---

## 0. Your job in one paragraph

This repo is an LM Studio benchmark/optimizer. It finds the best load configuration for a local
model, writes `results/<model>-best.md`, and runs a sandbox of generation tasks. Three independent
audits found that its **numbers are not yet trustworthy**: a benchmark cache can replay instead of
measure, the "long context" test never sends a long prompt, the quality gate is decided by one
substring match, Q2/Q3 quantisations are estimated as fp16, ~1 h per campaign is spent sweeping four
parameters that cannot affect anything, a large part of the sandbox scores prose as if it were code,
and the optimizer refuses to produce a valid `.blend` at all. Your job is to fix the measurement
path first, then the search cost, then the reporting, then the sandbox. Every finding below is
already verified against `data/optimizer.db` (119 runs) and `results/` — you do not need to
re-derive them. Implement, test, verify.

---

## 1. Ground rules (read before touching anything)

**Non-goals — do not do these:**

- Do not rewrite the orchestrator, rename stages, or restructure `optimizer.py`.
- Do not change the public CLI/API surface unless a fix requires it (then keep the old flag working
  and add a deprecation note).
- Do not run GPU campaigns. Every fix in phases 0–3 is verifiable offline with the harness in §2.
  If a fix seems to need a real model run, say so and stop.
- Do not delete anything under `results/` or `data/optimizer.db`. The user's history is the only
  evidence for the audits. If a file must be neutralised, move it to `results/_invalid/`.
- Do not change the database schema destructively. Additive migrations only.
- Do not mix sandbox work (phase 4) with optimizer work in the same PR.

**Style rules for the existing codebase:**

- Keep `logger`/`log_best_effort` usage patterns; no bare `except:`.
- Every new behaviour gets a unit test under `lm_optimizer/tests/` (or `tests/`).
- Keep comments that explain *why*, matching the existing docstring style.
- If a fix changes a reported number's meaning, say so in the report text (`reporting.py`), not only
  in the code.

---

## 2. Verification harness (already in the repo — use it, extend it)

| command | what it must show |
| --- | --- |
| `python tools/selfcheck_sandbox.py` | currently **26 findings**; must reach **0** by end of phase 4 |
| `python tools/check_run_integrity.py --run <id>` | must print **no FAIL** for any run produced after your fixes |
| `python -m pytest tests lm_optimizer/tests -q` | must stay green (report pre-existing failures separately, don't "fix" them by deleting the test) |

`tools/check_run_integrity.py` encodes the audits as assertions (cache replay, dropped validation
rounds, duplicate configs, no-op sweeps, short "long context", missing durations, empty Pareto,
marginless quality gate). **Any new bug you find of the same kind should be added to it as a check** —
that is how this stays fixed.

Evidence documents (read the relevant section before starting a package, don't read all of them):

- `docs/plans/OPTIMIZER-CODE-REVIEW-20261106.md` — optimizer/benchmark/scoring findings, with
  `file:line` and measured impact. **Primary reference for phases 1–3.**
- `results/DEBUG-REPORT-20261106.md` — sandbox findings. **Primary reference for phase 4.**
- `docs/plans/SANDBOX-V2-REDESIGN.md` — the sandbox target design (artifact contract, layered
  scoring, output files).
- `results/SCOREBOARD.md` — the reporting format the results should converge to.

---

# PHASE 1 — measurement integrity (P0, do this first)

Nothing else matters until a "successful" run provably contains real inference.

## WP 1.1 — Stop the benchmark cache from faking measurements

**Problem.** `benchmark.py:701` sets `cache_eligible = reps == 1`, and the `quick` preset sets
`reps=1` (`optimizer.py:146-156`). A cache hit replays an old `BenchmarkMetrics` without any
inference (`benchmark.py:709-716`). Measured proof: `nemotron-e4b` run `78c252af` reports 2 741
completion tokens at 12.2 tok/s in **21.6 s** — the physical minimum is 225 s.

**Change.**

1. `services/benchmark_cache.py`
   - Add to the key: `created_at`-independent `host_fingerprint` = hash of
     `{gpu name, driver/backend build, lmstudio cli build, kv_quant setting, n_threads,
     keep_model_in_memory}`. Read it from where `host/lm_studio.py` already exposes capabilities;
     do not add a new probe if the data exists.
   - Add `ttl_days` (default 14) and refuse entries older than that.
   - Expose `cache_reads_enabled` honouring a new env `LM_OPTIMIZER_BENCHMARK_CACHE_RW`
     (`off` = never read, still write; default `off`).
2. `services/benchmark.py`
   - `cache_eligible = reps == 1 and cache_reads_enabled()`.
   - Record `generation["cache_hits"]` and `generation["cache_misses"]` on the result; persist them.
   - A case served from cache must be flagged in the metrics (`from_cache=True`) so nothing
     downstream can present it as freshly measured.
3. `services/orchestration/optimizer.py`
   - Store `benchmark_params["cache_reads_enabled"]` on the run.

**Acceptance.**
- New unit test: a `reps=1` run with a pre-populated cache produces `from_cache=True` metrics and a
  non-zero `cache_hits`, **and** `check_run_integrity.py` reports `FAIL … cache replay` unless the
  run's elapsed time is consistent with its tokens.
- A `standard` preset run never reads the cache.

## WP 1.2 — Record durations, so every report stops saying "total 0 ms"

**Problem.** `duration_ms` is `0` on **104 of 119 runs**. `failure_states.py:152` sums it →
`total 0 ms`; `reporting.py:291` shows a wrong `Elapsed`.

**Change.** In the persistence path (`database/repositories.py`, wherever a `ConfigurationResult`
is saved), write `duration_ms` from the measured wall time of that configuration (load + preheat +
measured runs). If it is genuinely unknown, persist `NULL`, never `0`, and make the readers render
`n/a` instead of `0 ms` (`failure_states.py`, `reporting.py`).

**Acceptance.** `check_run_integrity.py` stops emitting the `duration_ms missing` FAIL for a new
run; `failure_signatures` renders real ms; a unit test covers the NULL path.

## WP 1.3 — Never lose the reason a configuration failed

**Problem.** `benchmark.py:1087` falls back to the literal `"All runs failed"` whenever the per-run
error is empty, so a flaky config is rejected with no diagnosis. Observed: the *same* config tested
4× gave 1 pass and 3 `benchmark_failed`.

**Change.**
- Propagate the real exception text from `_run_single_case` through `BenchmarkMetrics.error`
  (never drop it), and include the failing case names in `ConfigurationResult.error`.
- Retry a `benchmark_failed` configuration **once** (config-level, not case-level) before giving it a
  terminal status. Record `retried=True` and both attempts' errors.
- Add a hard distinction in the status/error text between `transient` (timeout, connection, single
  all-runs-failed) and `structural` (load failure, incompatible, quality).

**Acceptance.** Unit test: a case that raises on the first attempt and succeeds on the retry yields
`passed` with `retried=True`. No code path can produce an error string identical to the fallback
while a real exception exists.

## WP 1.4 — Validation reports a pass rate instead of the best round

**Problem.** `optimizer.py:1919-1925` appends only `PASSED` validation rounds and takes their median,
so `quality 0.983` hides `4/5` (Q4 run) or `2/6` failures. Files: `optimizer.py:1886-1940`,
`_median_result` at `:2492` (biased for even counts).

**Change.**
- Run validation with `repetitions=1` (validation is about stability of the chosen config, not new
  speed medians) — expected saving ~5 h per 27B campaign. Expose this via
  `advanced_settings["validation_benchmark_repetitions"]`, default 1.
- Keep **all** rounds in `state.tested_configs` (with their status), and compute:
  `validation_pass_rate`, `quality_median`, `quality_min`, `speed_median`, `speed_iqr`.
- Fix `_median_result` to a true median for even counts.
- Persist these on the run and print them in `reporting.py` next to `Quality:`.

**Acceptance.** Report shows `Quality: 0.983 (median) · validation pass rate 4/5`. Integrity check
no longer emits the `validation … dropped` FAIL.

## WP 1.5 — Pareto frontier can never be empty when something passed

**Problem.** `pareto_config_ids_json = []` in **84 of 119 runs**, including runs with 15–24 passed
configs, while `reporting.py:710` prints `Pareto-optimal: 0 of N passed` (impossible).

**Change.** In `_stage_validation`, recompute the frontier *after* quality validation, assert
`len(frontier) >= 1` when any config passed (raise/log a warning with the inputs if not), and make
`reporting.py` print `not computed` instead of `0 of N` when the run is incomplete.

**Acceptance.** Unit test with a single passed, quality-bearing config → frontier has 1 element.
Integrity check's `Pareto frontier empty` FAIL disappears.

---

# PHASE 2 — stop wasting campaign time (P0 for wall-clock, P1 for risk)

## WP 2.1 — Correct the VRAM estimate (this currently breaks every Q1/Q2/Q3 model)

**Problem.** `search_space.py:318-340` (duplicated verbatim in `discovery/inspector.py:125-150`)
maps only q4/q5/q6/q8/fp16/fp32 and defaults everything else to **fp16**. Measured with the repo's
own function:

| quant | estimated | actual | error |
| --- | --- | --- | --- |
| Q2_K | 65.4 GB | 12.0 GB | **5.5×** |
| Q1_0 | 65.4 GB | 9.0 GB | 7.3× |
| Q3_K_M | 65.4 GB | 13.9 GB | 4.7× |
| Q4_K_S | 16.3 GB | 17.5 GB | 0.9× |

`ModelIdentity.size_bytes` already exists (`domain/model.py:17`) and holds the real file size
(it is what `Variant/size` prints in the reports).

**Change.** Create one shared helper (e.g. `services/model_size.py`) and use it from both call sites,
deleting the duplicates:

```python
# Values are measured bytes-per-parameter *including GGUF overhead*, derived from
# the files in this repo: Q2_K 27B = 11.96e9 B -> 0.443, Q4_K_S 27B = 17.50e9 B
# -> 0.648. Order matters: iq2/iqq contain "q2", and bf16 must come before f16.
_BYTES_PER_PARAM = (
    ("iq1", 0.26), ("q1", 0.28), ("iq2", 0.31), ("q2", 0.44), ("iq3", 0.42),
    ("q3", 0.52), ("iq4", 0.55), ("q4", 0.65), ("q5", 0.77), ("q6", 0.90),
    ("q8", 1.10), ("bf16", 2.05), ("fp16", 2.05), ("f16", 2.05), ("f32", 4.10),
)

def estimate_weights_gb(model) -> float | None:
    if getattr(model, "size_bytes", None):
        return model.size_bytes / 1024**3          # exact, always preferred
    if not getattr(model, "parameter_count", None):
        return None                                # unknown, never guess fp16
    q = (model.quantization or "").lower()
    bpp = next((b for token, b in _BYTES_PER_PARAM if token in q), None)
    return None if bpp is None else model.parameter_count * bpp / 1024**3

def estimate_vram_gb(model) -> float | None:
    w = estimate_weights_gb(model)
    return None if w is None else w * 1.15         # KV cache + compute buffers
```

Then make `_generate_gpu_ratio_candidates` and the eligibility/fit code treat `None` as
"unknown → do not place the model in the 'larger than VRAM' bucket; use the neutral bucket"
(i.e. the middle branch, not the pessimistic one).

**Acceptance.** Table test with three cases per quant: (a) `size_bytes` present → exact; (b) only
`parameter_count` → within ±20 % of the measured file size (Q2_K 27B ≈ 12.0 GB, Q4_K_S 27B ≈ 17.5 GB);
(c) neither → `None`, and no code path may fall back to fp16. A Q2_K model must no longer land in the
`[0.6, 0.5, 0.4, 0.3, 0.25, 0.0]` offload bucket for a 6 GB GPU.

## WP 2.2 — `long_context` must actually be long

**Problem.** `benchmark/suite.py` scales the document only for `context_length > 8192`, and even then
only inserts `---` lines. Measured: **every run in the DB sent 285–305 prompt tokens**, including at
ctx 32768 (1 % of the window). Simultaneously `reporting.py:669` reports the largest *tested* context
as "maximum stable context". So the context dimension is entirely unmeasured.

**Change.**

1. In `create_benchmark_cases`, build the context case from repeated real document text up to a
   target of `int(0.8 * context_length)` tokens (≈3.6 chars/token), keeping the original question at
   the end and inserting a unique needle sentence in the middle
   (e.g. `"NOTE: the harbour access code is 7-TANGO."`).
2. Assert before scoring: `prompt_tokens >= 0.6 * context_length`, else mark the case
   `insufficient_context=True` and make it a **hard** failure for that config (never a silent pass).
3. Add a second question variant that asks for the needle, so a real recall measurement exists:
   `needle_recall` case, `max_tokens=32`, validator = exact match of the needle string.
4. Fix `reporting.py:669` naming: `maximum stable context` → `largest context tested`, and only use
   the words "stable" when a recall probe passed at that size.
5. `check_run_integrity.py` already checks this — keep it.

**Acceptance.** At ctx 4096 the `long_context` prompt must be ≥2 400 tokens; at ctx 32768 ≥19 000.
Unit test with a fake tokenizer/char heuristic. A `needle_recall` failure is visible in the report.

## WP 2.3 — Stop sweeping parameters that cannot change the result

**Problem.** `_generate_stage4_configs` (`optimizer.py:1772-1820`) produces ~12 configs varying
`eval_batch_size`, `physical_batch_size`, `parallel`, `context_checkpoints` around the winner. For a
single interactive request with a ~300-token prompt, **none of these can affect decode speed**
(`eval_batch`/`physical_batch` are prefill-only; `parallel` only multiplies KV slots;
`context_checkpoints` only helps repeated identical prefixes). Observed: 12 such configs per run,
1.6→2.4 tok/s spread of pure noise, and that noise picks the winner.

**Change.**

- Skip stage 4 entirely when `workload_type == "interactive"` **and**
  `max_prompt_tokens_of_suite < min(batch_sizes)`.
- Otherwise test at most `physical_batch_size ∈ {256, 1024}` and only when a long-prompt case exists.
- Move `eval_batch_size` testing to a **prefill/TTFT** objective (the speed stage already exists) and
  drop it from the decode-stage sweep.
- Test `context_checkpoints` with a two-turn repeated-prefix probe, not a single-shot benchmark.
- Never sweep `parallel` when `workload_type == interactive` (`workload.apply_to_space` already
  returns `[1]`; the micro-refinement/BALANCED branch re-expands it — remove that).

**Acceptance.** For `workload_type=interactive` with a short suite, stage 4 creates **0** configs and
logs why. `check_run_integrity.py`'s "N configurations differ only in …" WARN disappears for new runs.

## WP 2.4 — One dedupe key for every stage

**Problem.** Coarse search includes flash/kv in its key (`optimizer.py:1405-1420`); refinement omits
them (`:1593-1603`). Result: `flash=False` variants are silently skipped in refinement, and identical
configs get re-tested. A correct implementation already exists: `_candidate_key` (`:2735`).

**Change.** Use `_candidate_key(cfg)` for `completed_keys`, `tested_keys` and every `seen` set.
Add a debug log when a candidate is skipped as a duplicate.

**Acceptance.** A run that would previously test the same config twice now tests it once; unit test
covering "a config differing only in flash_attention is NOT considered already tested".

## WP 2.5 — Never generate an impossible load

**Problem.** `search_space.py:260-272` adds `flash_attention=False` while
`_generate_kv_cache_options` adds `offload_kv_cache_to_gpu=True`. That pair is rejected by LM Studio
(`V Cache Quantization requires flash attention`). 4 wasted loads in the Q4 campaign. The learner
`_note_flash_requirement` (`optimizer.py:1815`) only fires *after* the failure.

**Change.** Filter the pair at generation time (both in `SearchSpaceGenerator` and the coarse
cross-product), and default `test_flash_off` to `False` once `settings flash_required == 1`
(the learner already persists it).

**Acceptance.** Unit test: no generated config ever combines `flash=False` with KV-on-GPU or
non-f16 KV quant.

---

# PHASE 3 — quality measurement and reporting honesty

## WP 3.1 — The quality gate must not be decided by one substring

**Problem.** `profiles/registry.py:117` uses `minimum_quality = 0.97`, compared against a mean of
heuristic dimension scores. Identical configs produced `0.9333` (rejected) and `0.9833` (accepted) —
a **0.049 window**, moved by one dimension of `coding_task`, which is
`has_def = "def find_duplicates" in code` (`scoring/evaluator.py:243`). Across the DB:
`coding_task` 0.533→1.0, `structured_output` 0.0→1.0, `long_context` 0.583→1.0 on *identical* configs.

**Change.**

1. Replace the flat threshold with: `no critical check failed AND aggregate >= 0.90`, where
   "critical" is a per-test flag (start with: `structured_output` schema validity,
   `coding_task` compiles+runs, `output_not_empty`).
2. Grade on continuous dimension scores, not on a mean of pass/fail booleans
   (`scoring/evaluator.py:21-25`).
3. Fix the flap sources:
   - `_strip_fences` (`evaluator.py:46`) must strip **all** fences anywhere in the text, not one
     leading pair.
   - `has_def` → `re.search(r"\bdef\s+find_duplicates\s*\(", code)`.
4. Keep the old numeric threshold available via `advanced_settings["quality_threshold_override"]` so
   existing reports remain reproducible.

**Acceptance.** Unit tests: a fenced answer and an unfenced answer score identically; a prose-only
answer scores 0 on `coding_task`; a single non-critical miss (e.g. missing docstring) does **not**
flip the verdict, while a compile failure does.

## WP 3.2 — Make `coding_task` mean something

**Problem.** The code is never compiled or executed. `task_completion` is a substring test and the
"O(n)/O(1)" requirement is satisfied by *writing the words* in a docstring.

**Change.** `compile()` the extracted function and run 5 assertions in a subprocess with a 5 s
timeout (duplicates, negatives, empty list, all-unique, ascending order). Score
`coding_correctness` from the pass count; keep the existing heuristics as secondary signals.

**Acceptance.** An empty `def find_duplicates(items): pass` scores 0 on correctness. A correct
implementation scores 1.0. Total added runtime < 1 s per case.

## WP 3.3 — Stop recommending `presence_penalty: 1.5` to Qwen3.8

**Problem.** `generation_defaults.py:16-30` matches the Qwen3.5 entry on the `arch` token `qwen35`,
which is exactly the architecture LM Studio reports for `swift-qwen3.8-27b`. The model therefore
inherits Qwen3.5's `presence_penalty: 1.5` and the Qwen3.5 source citation. (It is not applied during
benchmarks, so this is bad advice, not bad data.)

**Change.** Match on the model id (`match`) **first**; only fall back to `arch` when no `match` entry
hits, and treat `arch` as an exact token match rather than a substring. Add a unit test for
`swift-qwen3.8-27b@q2_k` → qwen3.8 settings, `presence_penalty 0.0`.

**Acceptance.** Both q2_k and q4_k_s report `presence_penalty: 0.0` with the Qwen3 source.

## WP 3.4 — Report what is comparable

**Problem.** `score` is normalised inside one run (`scoring/normalization.py:177-270`), so a 2.8 tok/s
config scores 0.844 while a 4.1 tok/s config scores 0.467.

**Change.**

- In `reporting.py` and the API schema, print `score` with the explicit note
  *"within-run rank; not comparable across models"*, plus an absolute column
  `gen tok/s` / `TTFT` / `quality` / `context`.
- Add `hardware_index = gen_tok_s / reference_tok_s_for_this_gpu` (reference from a shipped table,
  documented) so cross-run comparison has *some* anchor.
- Fix the failure-signature display: group by the masked key but **print the raw error**
  (`failure_states.py:80`) — currently `qwen3.8-27b` prints as `qwen3.#27b` and `12 gb` as `# gb`.
- Delete the empty `results/campaign/`, `results/deep/` writers or implement them.

**Acceptance.** `results/SCOREBOARD.md` regenerates from real runs via
`python tools/build_scoreboard.py`; signatures show real model ids and numbers.

## WP 3.5 — Duels must measure something

**Problem.** `cli/lab.py:706-707` hardcodes `"tokens_per_second": 0.0, "tokens": 0`, so all 5 duel
reports read `TTFT 0 · Gen 0.0 · Quality 1.000 · Pass no` and `undetermined (insufficient data)`.

**Change.** Populate both fields from the real `BenchmarkMetrics`; set `quality` to `None` when the
attempt did not pass; make the verdict say `no measurement` only when there genuinely is none.

**Acceptance.** A duel between two loaded models prints non-zero tok/s and a real winner.

---

# PHASE 4 — sandbox (separate PR series)

Target design: `docs/plans/SANDBOX-V2-REDESIGN.md`. Findings: `results/DEBUG-REPORT-20261106.md`.
**Definition of done for this phase: `python tools/selfcheck_sandbox.py` exits 0.**

## WP 4.1 — The artifact contract (this is the Blender bug)

**Problem.** `sandbox_runner.py:294` writes the model's text into `artifacts[0]`, which for the
Blender task is `scene.blend` (`sandbox_lab.py:198`). The prompt asks for a *script*, so a text file
is stored as `scene.blend`; `blender` is never executed (`cli/lab.py:789` builds `SandboxRunner`
without `command=`); output is capped at 2 048 tokens (`lab.py:814`). All 10 stored `.blend` files are
Python text or reasoning, 1.3–8.4 KB, none starting with the `BLENDER` magic bytes.

**Change.**

1. Add `ArtifactSpec(path, kind, produced_by ∈ {model, runner}, validator, min_bytes, critical)` and
   `SandboxTask.outputs`; keep `artifacts` as a deprecated alias for one release.
2. `_materialise` writes only `produced_by == "model"` artifacts; `produced_by == "runner"` artifacts
   are asserted to exist after the command runs.
3. Raise `MissingCommand` when a task declares a runner artifact and `command == ""`
   (this alone turns the silent false pass into a loud config error).
4. Per-task `max_output_tokens` (Blender needs ≥6144); record `finish_reason`/`truncated`; a truncated
   `code`/`blender` artifact fails validity.
5. Wire `command=build_command_for(task)` in `cli/lab.py` and fix `build_command_for` to
   `blender --background --python build_scene.py`.

**Acceptance.** `selfcheck_sandbox` fixtures: `perfect_script` and `prose_dump` for
`blender_skyblock` both score ≤0.2; a valid run produces a `scene.blend` that begins with `BLENDER`.

## WP 4.2 — Execution-based grading

- `blender_opens` validator: run `blender --background scene.blend --python-expr <introspect>` and
  grade the returned JSON (object counts, materials, camera, animated objects, frame range, rendered
  frames, black-frame ratio). If `blender` is absent → status `not_measured`, **never** a pass.
- `python_exec` validator: run the artifact, compare stdout to golden output.
- `html_dom` validator: assert `#theme-toggle`, `@media` inside `<style>`, required elements via
  `html.parser`; add a hard gate `is_really_html` (strip fences, require `<!DOCTYPE html` or `<html`).
- JSON checks: extract the object (`re.search(r"\{.*\}", text, re.S)`) and strip fences before
  `json.loads` — a fenced-but-correct answer must score 1.0, a prose answer 0.0.

**Acceptance.** All `fixtures` findings in `selfcheck_sandbox.py` green.

## WP 4.3 — Fix the four structurally broken tasks

| task | bug | fix |
| --- | --- | --- |
| `research_synthesis` | `RESEARCH_PACKAGE` is never interpolated into the prompt; `no_irrelevant_source` misses `negate=True` | include the source documents, delimited and labelled; add `negate=True` |
| `email_and_calendar` | check demands `10:45`, the notes never state a duration | state "for 45 minutes" in the notes |
| `web_dashboard` | validator emits `has_viewport`, task expects `has_viewport_meta`; regex fallback greps prose | one canonical name per check + a warning when a custom result has no matching check |
| `blender_skyblock` | see WP 4.1 | — |

**Acceptance.** `selfcheck_sandbox` `reachable` / `material` / `wiring` / `contract` lints green.

## WP 4.4 — Layered scoring and output files

- Score = `(L2 conformance + L3 quality + L4 behaviour) × Π(L1 validity gates)`; a failed gate zeroes
  the attempt (see design doc §3). No check may pass without evidence.
- Emit the append-only layout from the design doc §6.1: `results/runs/<run_id>/models/<model>/<task>/
  attempt-N/{manifest.json,checks.json,exec.json,files/}`. Stop overwriting
  `results/sandbox-<task>.json`.
- Retention per `(model, task)`, never global per task (`apply_retention`, `sandbox_runner.py:118`).
- Mark harness timeouts `not_measured`, never `0.0` (`tools/backfill_sandbox_runs.py:125`).
- Raise the sweep timeout in `tools/sandbox_all_models.py:78` (900 → 3600 s) and record
  `timeout` vs `load_failed` distinctly.

**Acceptance.** A single task run produces the directory tree above; `build_scoreboard.py` consumes it.

---

# Execution order and PR batching

| PR | packages | why in this order |
| --- | --- | --- |
| 1 | 1.1, 1.2 | Without these, every later number is suspect |
| 2 | 1.3, 1.4, 1.5 | Makes verdicts explainable and stable |
| 3 | 2.1 | Unblocks every Q1/Q2/Q3 model (including the user's Q2 run) |
| 4 | 2.2 | Turns "context" from a guess into a measurement |
| 5 | 2.3, 2.4, 2.5 | Cuts ~1 h + several failed loads per campaign |
| 6 | 3.1, 3.2 | Quality stops being a coin flip |
| 7 | 3.3, 3.4, 3.5 | Reporting honesty |
| 8–10 | 4.1 → 4.4 | Sandbox, in its own series |

After each PR: `pytest`, then `python tools/check_run_integrity.py --run <a fresh run id>` and report
the diff in findings. **Do not start phase 4 until phase 1 is merged** — the sandbox campaign numbers
would otherwise be uninterpretable for the same reason the optimizer's are.

---

# Definition of done

1. `python tools/selfcheck_sandbox.py` → exit 0, `all checks green`.
2. `python tools/check_run_integrity.py --run <new run>` → zero `FAIL`.
3. A `standard` preset run on any model shows, in the report:
   - `reps ≥ 3` and `cache_reads_enabled: false`,
   - a real `long_context` prompt token count ≥60 % of the context,
   - `Quality` with a `validation pass rate`,
   - a non-empty Pareto line,
   - non-zero `duration_ms` on every configuration,
   - no more than 2 stage-4 configurations for an interactive workload.
4. Total campaign time for a 27B on ctx 8192 is **at most half** the previous 13.5 h, with no loss of
   meaningful measurement (call this out explicitly in the PR description).
5. Every fix has a test that fails on the old code.

---

# Reporting back

For each work package, state:

- what changed (`file:line`),
- the test that proves it (name + command),
- the measured before/after where it exists (elapsed, configs tested, quality spread),
- anything you deliberately did **not** change and why.

If a package turns out to be based on a wrong assumption, say so and stop that package — do not
implement a workaround to make the acceptance command pass.
