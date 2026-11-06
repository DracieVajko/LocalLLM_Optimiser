# Optimizer code review — measurement integrity, scoring, and time waste

Reviewed: `lm_optimizer/services/` (orchestration, benchmark, scoring, search space, suite),
cross-checked against `data/optimizer.db` and the 12 campaigns in `results/`.
Date: 2026-11-06.

Companion docs: `results/DEBUG-REPORT-20261106.md` (sandbox), `docs/plans/SANDBOX-V2-REDESIGN.md`,
`tools/selfcheck_sandbox.py` (deterministic harness self-test).

---

## 0. Read this before starting the new Q2 run

**Your last Q2 run tested nothing.** The database says:

```
swift-qwen3.8-27b@q2_k   run 0d4d749c   started 14:03:22   completed 14:24:25   = 1262 s
  benchmark_repetitions: 1        validation_repetitions: 2
  configurations in DB:  1        (ctx 4096, passed)
  stage: complete, status: success, "winner of 1 tested"
```

Two independent causes, both fixable without touching the code:

1. **The `quick` preset sets `benchmark_repetitions: 1`** (`optimizer.py:146-156`).
2. **`reps == 1` turns on the benchmark cache** (`benchmark.py:701`, `cache_eligible = reps == 1`).
   A cache hit replays an earlier measurement **without generating anything** (`benchmark.py:709-716`).

That is why `nemotron-e4b` "ran" its whole 5-test suite × 2 validation rounds in **21.6 s**
(`data/optimizer.db`, run `78c252af`: `duration_seconds = 21.63`, 2 741 completion tokens at a
claimed 12.2 tok/s ⇒ ≥225 s is the physical minimum). It is a replay, not a measurement.

```
$ ls data/benchmark_cache | wc -l
173
```

The cache key (`benchmark_cache.py:39-56`) contains suite version, model id, case, context,
reasoning and `LoadConfiguration` — **but no timestamp, no host state, no LM Studio/llama.cpp
version, and no TTL**. KV-cache quantisation and thread count are GUI-only settings that are not in
`LoadConfiguration`, so two physically different hosts produce the same key.

**Before the new Q2 run:**

```bash
# 1. A measurement that is not a replay
rm -rf data/benchmark_cache/*          # or: set LM_OPTIMIZER_BENCHMARK_CACHE=data/cache_q2_test

# 2. A preset that actually measures (reps=3, validation 2..5, all stages)
python -m lm_optimizer.cli.main run --model swift-qwen3.8-27b@q2_k --preset standard

# 3. Prove it is fresh: the elapsed time must be at least
#    (completion tokens / measured tok/s) + load time. For a 27B at ~3 tok/s
#    a 5-test suite CANNOT finish in under ~4 minutes.
```

Verify afterwards: `python tools/check_run_integrity.py` (see §7) should print
`reps=3, cache_eligible=False, configs>=3`.

---

## 1. Where the time actually goes (measured, not estimated)

`swift-qwen3.8-27b@q4_k_s`, run `7ae5ffae`: **48 428 s = 13.5 h**, 23 configurations.

| block | configs | time | what it measured |
| --- | --- | --- | --- |
| ctx 4096, batch/physical/parallel/checkpoint sweep | 17 | ~1.1 h | 11 configs that are physically equivalent (see §5.1) |
| ctx 8192 validation | 6 | **~6.3 h** | the same config 6× — **and the "long context" prompt is only 297 tokens** |
| 4 load failures | 4 | ~5 s | invalid combinations that should never be generated (§4.1) |
| dead time / pauses | — | ~5.5 h | gap 04:33→10:07, `duration_ms = 0` on 17 of 23 records |

Two things make this worse than it looks:

**1.1 `long_context` does not test long context.** `benchmark/suite.py` scales the document only
when `context_length > 8192`:

```python
if bp.category == "context" and context_length > 8192:
    repeat_count = min(context_length // 4000, 4)
```

At ctx 8192 the prompt is the base ~350-token paragraph. The reports confirm it:
`long_context` measured **285 prompt tokens at ctx 4096** and **297 prompt tokens at ctx 8192**.
So the 6.3 h of "8192 context validation" was 6.3 h of measuring a 297-token prompt on a config
whose only difference was a larger KV allocation. And `maximum stable context: 8192` is a claim
about a number that was never sent to the model.

**1.2 Validation re-measures instead of validating.** `_stage_validation`
(`optimizer.py:1886-1940`) calls `_test_config` `validation_repetitions` times (5), and each call
runs the **full 5-test suite × `benchmark_repetitions` (3)** = 15 generations. 5 × 15 = 75
generations of a 27B model to confirm one config. With `reps > 1` the cache is bypassed
(`benchmark.py:701`), so all 75 are real. At ~80 min per validation round this is the single
largest cost in the campaign.

**Fix:** validation needs *stability of the already-chosen config*, not new speed medians. Run it
with `repetitions=1` and 2–3 rounds, and use the median. Saves ~5 h per 27B campaign.

---

## 2. Measurement integrity

| # | Bug | Evidence | Effect |
| --- | --- | --- | --- |
| 2.1 | `reps == 1` ⇒ cache replay (`benchmark.py:701`) | e4b: 10 generations in 21.6 s | A "successful" run can contain zero new inference |
| 2.2 | Cache has no TTL / no host state (`benchmark_cache.py:39`) | 173 stale entries, oldest 2026-11-03 | After any GUI change (KV quant, threads) the numbers are unchanged and wrong |
| 2.3 | `duration_ms = 0` on 17 of 23 configs | `SELECT duration_ms …` | Every "total N ms" in failure reports is 0 (matches `total 0 ms` in the .md files) |
| 2.4 | `Elapsed:` header disagrees with the per-test table | e4b 21.6 s vs 2 741 tokens @12.2 tok/s | Any hours-per-model estimate is wrong |
| 2.5 | Preheat is 30 tokens of "Say hi in 5 words" (`preheat.py:49-54`) | — | Cannot warm a 17 GB file; first inference after a cold load pays page-fault cost |
| 2.6 | Preheat is not config-aware | `reps=1` runs combine preheat+cache | A cache hit skips inference entirely, so preheat warms nothing that gets used |

### 2.7 The same config measured 4× gave 1 pass and 3 failures

```
00:37:53  ctx=4096 phys=512 par=4 batch=2048 flash=T kv=T  passed            1.61 tok/s
00:43:13  ctx=4096 phys=512 par=4 batch=2048 flash=T kv=T  benchmark_failed  "Some tests failed"
00:46:52  ctx=4096 phys=512 par=4 batch=2048 flash=T kv=T  benchmark_failed  "Some tests failed"
00:47:32  ctx=4096 phys=512 par=4 batch=2048 flash=T kv=T  benchmark_failed  "Some tests failed"
```

Byte-identical `config_json`. **A good configuration is rejected 75 % of the time**, and the reason
is unrecoverable because `benchmark.py:1087` substitutes the literal string `"All runs failed"`
whenever the per-run error is empty. This is the mechanism behind most
`completed_no_validated_winner` runs: it is a flaky harness, not a model that could not run.

The retry logic does not help: `_aggregate_results` fails a config if *all* repetitions of *one*
case fail, and `run_benchmark`'s `except` (`benchmark.py:757-762`) turns any exception into
`status = failed` with no retry at the config level.

---

## 3. Scoring and selection

### 3.1 Score is normalised inside the run, so it cannot rank models

`scoring/normalization.py:177-270`: `compute_bounds()` takes `min`/`max` **of the results in this
run** and `score_result_breakdown` normalises against them. Therefore:

| model | gen tok/s | run-relative score |
| --- | --- | --- |
| qwen3.8-9b-distill | 8.4 | **1.000** |
| swift-qwen3.8-27b@q4_k_s | **2.8** | 0.844 |
| qwen/qwen3-coder-30b | 4.1 | **0.467** |

A 2.8 tok/s config outranks a 4.1 tok/s config. `score` is a *within-run rank* and nothing else.
`compute_bounds` also contains three consecutive copies of the same metric-extraction block
(`normalization.py:204-221`) — dead iteration that signals this was rewritten in place.

### 3.2 Quality is cherry-picked from passing samples

`_stage_validation` (`optimizer.py:1919-1925`):

```python
if result and result.status == ConfigurationStatus.PASSED:
    validation_results.append(result)      # failures silently dropped
...
self.state.best_config = self._median_result(validation_results)
```

For `q4_k_s` the six validation runs scored `quality_failed(0.933)`, `pass`, `pass`, `pass`,
`pass`, `quality_failed(0.933)`. The two failures are discarded, and the report shows
`Quality: 0.983`. The honest statement is **4/6 validation rounds passed the 0.97 quality gate**,
i.e. the winner does not reliably pass its own threshold. The report should print
`quality: median of all attempts, pass_rate: 4/6`.

`_median_result` (`optimizer.py:2492`) sorts by speed and takes `speeds[len//2]` — for an even
count that is the upper-middle element, a silent upward bias.

### 3.3 Pareto frontier is empty in 2 of 12 runs

`pareto_config_ids_json` is `[]` for both single-config runs (e4b, q2_k) while a valid passing
config exists, so the report prints `Pareto-optimal: 0 of 1 passed` — which is mathematically
impossible. `_compute_pareto_frontier` (`optimizer.py:2440`) skips any result with
`quality_score is None`, and for single-config runs the only candidate is the median validation
result appended at `optimizer.py:1927`. Add an assertion (≥1 element when ≥1 passed) and a test.

### 3.4 `maximum stable context` = the largest context that was *tried*

`reporting.py:669`: `stable = max(tested, key=context_length)`. Combined with §1.1, the reported
`8192` (and `4096` for most models) is simply the biggest ctx in the search space that passed
nothing but a 300-token prompt. See `docs/plans/SANDBOX-V2-REDESIGN.md` §5.3 for the recall probe
that actually measures it.

### 3.5 The quality gate has no margin — one heuristic check decides pass/fail

`profiles/registry.py:117` sets `minimum_quality = 0.97` for balanced/context/quality.
The quality value is the mean of the per-test `overall` values, each of which is the mean of six
heuristic dimensions (`scoring/evaluator.py:21-25`; a dimension counts as passed at ≥0.9). The
observed values for the **same config** in `q4_k_s` were:

```
0.9333  rejected   (coding_task 0.667)
0.9824  accepted
0.9833  accepted   (coding_task 0.917)
```

So the entire accept/reject decision sits in a **0.049 window**, and the only thing that moves it is
*one* dimension of *one* test: `coding_task` flipping between 0.667 and 0.917 — which is
`has_def = "def find_duplicates" in code` (`evaluator.py:243`), i.e. whether the model wrapped its
function in a fence that `_strip_fences` failed to remove.

Across the whole database the same tests flap on identical configurations:
`coding_task` 0.533 → 1.0, `structured_output` 0.0 → 1.0, `long_context` 0.583 → 1.0,
`short_instruction` 0.917 → 1.0.

**Consequence:** the "quality gate" is close to a coin flip on a substring match, not a capability
measurement. It explains the `completed_no_validated_winner` runs (gemma: 15 passed configs,
4 `quality_failed`) and the 2-of-6 failed validation rounds of your Q4 winner.

**Fix:**

1. Grade on the *continuous* dimension scores, not on the mean of pass/fail booleans.
2. Replace the flat 0.97 with `no_critical_check_failed AND aggregate >= 0.90`.
3. Fix the two causes of the flap: `_strip_fences` must strip **all** fences anywhere in the text
   (it handles one leading pair only, `evaluator.py:46`), and `has_def` must be a regex
   (`\bdef\s+find_duplicates\s*\(`) instead of a literal substring.
4. Report `quality: median, pass_rate 4/6` — never the best passing round.

### 3.6 How often each defect fires (all 119 runs in `data/optimizer.db`)

`python tools/check_run_integrity.py --all`:

| finding | runs affected |
| --- | --- |
| `duration_ms` missing → every "total N ms" is 0 | **104 / 119** |
| Pareto frontier empty while passed configs exist | **84 / 119** |
| `long_context` prompt ≤ 4 % of the context window | **57 / 57 with a context case** |
| validation rounds dropped → cherry-picked quality | **32** |
| quality gate decided by a single heuristic check | **9** (runs with a quality case) |
| `long_context` at ctx 32768 used 294–305 prompt tokens | every such run |

The context finding is universal: **no run in the database ever sent a prompt longer than ~350
tokens**, at any context length including 32768. Every `maximum stable context` figure in
`results/*-best.md` is therefore unmeasured.

---

## 4. Search space and configuration generation

### 4.1 Q2/Q3/Q1 models are estimated as **fp16** — 5.5× too large

`search_space.py:318-340` (duplicated verbatim in `discovery/inspector.py:125-150`):

```python
if   "q4" in quantization: bytes_per_param = 0.5
elif "q5" in quantization: bytes_per_param = 0.625
elif "q6" in quantization: bytes_per_param = 0.75
elif "q8" in quantization: bytes_per_param = 1.0
elif "fp16" in quantization: bytes_per_param = 2.0
elif "fp32" in quantization: bytes_per_param = 4.0
# anything else: 2.0 (default)
```

Measured with the repo's own function:

| quant | estimated | actual file | error |
| --- | --- | --- | --- |
| **Q2_K** | **65.4 GB** | 12.0 GB | **5.5×** |
| Q3_K_M | 65.4 GB | 13.9 GB | 4.7× |
| Q1_0 | 65.4 GB | 9.0 GB | 7.3× |
| IQ2_XXS | 65.4 GB | 7.5 GB | 8.7× |
| Q4_K_S | 16.3 GB | 17.5 GB | 0.9× ✓ |
| Q8_0 | 32.7 GB | 29.0 GB | 1.1× ✓ |

`_generate_gpu_ratio_candidates` (`search_space.py:196`) then places every Q1/Q2/Q3 quant in the
"model larger than VRAM" bucket (`[0.6, 0.5, 0.4, 0.3, 0.25, 0.0]`) and the eligibility/fit
advice follows. **This is live in your Q2 test right now.**

**Fix:** `ModelIdentity.size_bytes` already exists (`domain/model.py:17`) and matches the
`Variant/size` field the reports print. Use it first:

```python
if model.size_bytes:
    return model.size_bytes / (1024**3) * 1.15      # +15 % KV/overhead
```

and add `q1`, `q2`, `q3`, `iq1`..`iq4`, `bf16` to the fallback map. Also collapse the duplicate
implementation — two copies will drift.

### 4.2 `parallel` is swept even for the interactive workload

`workload.apply_to_space` correctly returns `[1]` for interactive, and the stored search space
says `"parallels": [1]`. But `_stage_batch_optimization` → `_generate_stage4_configs`
(`optimizer.py:1772-1820`) reads `space.parallels`, and the observed run contains `par=1, 2, 4, 8`
— coming from `_stage_micro_refinement` / the BALANCED branch, which re-expands the list. For a
single-user chat workload `parallel>1` only multiplies KV allocation: it cannot improve latency.
**Never sweep it when `workload_type == interactive`.**

### 4.3 Stage 4 sweeps four dimensions that cannot affect the measured quantity

`_generate_stage4_configs` produces one config per value of `eval_batch_size` (6),
`physical_batch_size` (3), `parallel` (up to 4) and `context_checkpoints` (3) ≈ 12 configs.

What they actually change:

| parameter | affects | measured objective here |
| --- | --- | --- |
| `eval_batch_size` | batched **prefill** only, and only when `prompt_tokens > batch` | generation tok/s + TTFT of a ~300-token prompt |
| `physical_batch_size` | prefill chunking | same |
| `parallel` | max concurrent predictions (KV slots) | same |
| `context_checkpoints` | prompt-cache reuse for **repeated identical prefixes** | same |

With a 297-token prompt and one request per measurement, all four are no-ops. The observed spread
across the 11 stage-4 configs was **1.6 → 2.4 tok/s (50 %)** — pure noise, and that noise then
*drives winner selection*.

**Fix:** gate stage 4 on evidence:

- skip entirely when `workload_type == interactive` **and** `prompt_tokens < min(batch_sizes)`;
- keep at most `physical_batch_size` ∈ {256, 1024} and only when a long-prompt case exists;
- test `eval_batch_size` with a *prefill/TTFT* objective in the prefill stage, not the decode stage;
- test `context_checkpoints` with a two-turn repeated-prefix probe, not a single-shot benchmark.

Expected saving: **~1 h per 27B model, and it removes the noise that picks the wrong winner.**

### 4.4 The same config can be re-tested across stages

Coarse search dedupes on a key that **includes** flash/kv (`optimizer.py:1405-1420`); refinement
dedupes on `(ctx, gpu, batch, phys, par, ck)` — **flash and kv missing** (`optimizer.py:1593-1603`).
Consequently:

- a refinement config that differs only in `flash_attention` / `offload_kv_cache_to_gpu` is
  considered "already tested" and skipped (this is why the reports say *"flash=False was offered
  but never tried"*);
- and a config identical to an earlier one can be re-tested, which is what the 4× identical rows in
  §2.7 show.

There is already a correct implementation in the same file: `_candidate_key` (`optimizer.py:2735`)
uses `tuple(sorted(cfg.to_dict().items()))`. Use it everywhere.

### 4.5 Invalid combinations are generated and cost a load attempt

`_generate_flash_attention_options` adds `False` by default (`test_flash_off: True`,
`search_space.py:260-272`) while `_generate_kv_cache_options` adds `True`. The pair
`flash_attention=False, offload_kv_cache_to_gpu=True` is rejected by LM Studio
(`V Cache Quantization requires flash attention to be enabled`) — 4 such rows in the q4 run,
1 in `qwen-qwen3-coder-30b-failed-20261025`. There *is* a learner
(`optimizer.py:1815 _note_flash_requirement`) but it only fires **after** the failure. Filter the
pair at generation time.

---

## 5. Does the benchmark suite measure anything?

### 5.1 `coding_task` is graded by substring, and never executed

`scoring/evaluator.py:236-260`:

```python
has_def = "def find_duplicates" in code                              # task_completion
has_complexity = any(kw in code.lower() for kw in ["o(n)", "o(1)", "linear", "constant"])
no_extra = not any(kw in code for kw in ["class ", "if __name__"])
```

A function with an empty body passes; the "O(n) time, O(1) space" requirement is satisfied by
*writing the words* `O(n)` in the docstring. The prompt asks for O(n)/O(1)/negatives/ascending
order; none of that is checked, and the code is never compiled or run.

**Fix:** `compile()` is free; running it against 5 assertions costs ~0.2 s and would make this the
most informative test in the suite.

### 5.2 `long_context` is not long (see §1.1)

Also note `max_tokens = min(bp.max_tokens, context_length // 4)` (`suite.py`), so at ctx 2048 the
reasoning case is silently capped at 512 tokens — a per-context change in the *workload*, which
makes cross-context speed comparisons invalid.

### 5.3 `stop_sequences` are dead code

All five cases define `stop_sequences` (`benchmark/suite.py`), `BenchmarkCase` carries them
(`benchmark.py:532`), and `chat_completion` (`host/lm_studio.py:812-823`) has **no `stop`
parameter** — the field is never sent. `_strip_fences` in the evaluator even documents this:
*"the server rejects `stop`"*.

Two consequences:
1. If it ever gets wired up, `coding_task`'s stops are `["```", "def ", "class "]` — the prompt is
   *"Provide only the function definition"*, so the model would be cut off at its first token.
   The `structured_output` stop is `["}"]`, which would truncate the nested `address` object.
2. Today it is a silent no-op that makes the suite look stricter than it is.

### 5.4 The generated `presence_penalty: 1.5` is wrong for your models

`generation_defaults.py:16-30`:

```python
{"match": ["qwen3.5"], "arch": ["qwen35"], "settings": {..., "presence_penalty": 1.5},
 "source": "Qwen3.5 official (HF discussion #51, instruct-general)"},
{"match": ["qwen3.8", "qwen3", ...], "arch": ["qwen3", "qwen3moe"], "settings": {..., "presence_penalty": 0.0}},
```

LM Studio reports the architecture of `swift-qwen3.8-27b` as **`qwen35`**, which matches the
`arch` list of the *Qwen3.5* entry (listed first) — so a Qwen3.8 model inherits
`presence_penalty: 1.5`. That is what both q2_k and q4_k_s reports print, with the Qwen3.5 source
citation. `presence_penalty=1.5` is an extremely aggressive value; applied in chat it degrades
long answers noticeably. It is **not** applied during benchmarks (only per-case temperature is
sent), so it is bad *advice*, not bad data — but it will mislead you.

**Fix:** match on `match` (model id) before `arch`, and treat an `arch` token as a *prefix* match
only when the model id does not match a later, more specific entry.

### 5.5 Two parallel quality systems

`services/quality_lab.py:498 default_tasks()` defines 6 tasks (`instruction_list_three`,
`structured_json_person`, `coding_find_duplicates`, `reasoning_arithmetic`,
`slovak_translation`, `hallucination_resistance`), while the campaigns use
`benchmark/suite.py BENCHMARK_SUITE` (5 different tasks). The naming collides with the sandbox
preset ids too (`web_search`, `deep_research` exist in both). Pick one registry.

---

## 6. Priority fix list

### P0 — correctness of the numbers

| # | file:line | change | acceptance |
| --- | --- | --- | --- |
| 1 | `benchmark.py:701` | Make the cache opt-in (`LM_OPTIMIZER_BENCHMARK_CACHE_RW=off` by default) and **never** serve a config that has not been measured in this run | a `quick` run's elapsed ≥ `tokens / tok_s` |
| 2 | `benchmark_cache.py:39` | Add `host_fingerprint` (GPU, driver, LM Studio build, llama.cpp build, KV-quant setting, thread count) + a TTL/`created_at` to the key; expose a `--no-cache` flag | changing a GUI setting invalidates the entry |
| 3 | `benchmark/suite.py` (context case) | Build the long-context prompt from repeated real text to actually reach the target: `target_tokens ≈ 0.8 × context_length`, and assert `prompt_tokens ≥ 0.6 × context_length` before scoring | `long_context` prompt tokens ≈ 3 300 at ctx 4 096, ≈ 6 600 at ctx 8 192 |
| 4 | `optimizer.py:1886-1940` | Validation: `repetitions=1`, record **all** attempts (keep failures), report `quality_median` + `pass_rate` | report shows `4/6 validation rounds passed`, not `0.983` |
| 5 | `benchmark.py:1087` | Propagate the real per-case exception; never print `"All runs failed"` when an error exists | a flaky config's report names the failing case and reason |
| 6 | `benchmark.py` (run loop) | Retry a failed config **once** before `benchmark_failed`; distinguish `transient` from `structural` | the 4×-identical-config case yields 4 passes, not 1 |

### P1 — stop wasting time

| # | file:line | change | saves |
| --- | --- | --- | --- |
| 7 | `search_space.py:318` | Use `model.size_bytes`; add q1/q2/q3/iq*/bf16 | fixes eligibility for Q2 (your run) |
| 8 | `optimizer.py:1772` | Gate stage 4: skip when `interactive` and `prompt_tokens < min(batch)`; drop `parallel` and `context_checkpoints` from the sweep | ~1 h / 27B |
| 9 | `optimizer.py:1593` | Use `_candidate_key(cfg)` (full `to_dict`) for every dedupe set | removes duplicate measurements |
| 10 | `optimizer.py:1815` | Filter `flash=False ∧ kv=True` at generation, not after a failed load | 4 failed loads |
| 11 | `search_space.py:260` | Default `test_flash_off: False` on hosts that learned `flash_required=1` | 1 load per model |
| 12 | `optimizer.py:2492` | `_median_result`: proper median for even counts | removes speed bias |
| 13 | `benchmark.py:211` | `warmup_repetitions: 1 → 2` and a longer preheat (`128` tokens) **before** the first config, then keep the model loaded between configs where the config allows (`keep_loaded`/`assume_loaded` already exist) | removes first-config penalty |

### P2 — reporting honesty

| # | file:line | change |
| --- | --- | --- |
| 14 | `reporting.py` | Print `score` with the explicit note *"within-run rank; not comparable across models"*, plus an absolute index (tok/s ÷ a hardware reference) |
| 15 | `reporting.py:669` | Rename `maximum stable context` → `largest context tested`; only claim stability after a recall probe |
| 16 | `optimizer.py:2440` + `reporting.py:710` | Assert/raise when the Pareto set is empty while a passed config exists; never print `0 of N` |
| 17 | `config_json` writer | Set `duration_ms` for every configuration (17 of 23 were 0) |
| 18 | `failure_states.py:67-82` | Group by the masked key but **print the raw error** (currently `qwen3.8-27b` → `qwen3.#27b`, `12 gb` → `# gb`) |
| 19 | `generation_defaults.py:16` | Match `match` before `arch`; Qwen3.8 must not inherit Qwen3.5's `presence_penalty: 1.5` |
| 20 | `benchmark/suite.py` | Wire `stop_sequences` or delete the field; fix `coding_task` stops (`"def "` would truncate it) |
| 21 | `scoring/evaluator.py:236` | Compile and execute the coding answer against 5 assertions; `has_def` as a regex; `_strip_fences` strips **all** fences |
| 22 | `profiles/registry.py:117` | Replace the flat `minimum_quality=0.97` with `no critical check failed AND aggregate >= 0.90`; the current gate is decided by one substring match (§3.5) |
| 23 | `benchmark/suite.py` | Scale `long_context` to ~80 % of the window and assert `prompt_tokens >= 0.6 * ctx` before scoring (§1.1, §5.2) — 57/57 runs never exceeded 305 tokens |

---

## 7. The run integrity check (implemented)

`tools/check_run_integrity.py` reads `data/optimizer.db` and fails loudly on the exact patterns
found in this review. Real output for your Q4 campaign:

```
$ python tools/check_run_integrity.py --run 7ae5ffae
run 7ae5ffae  swift-qwen3.8-27b@q4_k_s  profile=balanced  status=success
  INFO  23 configurations: 15 passed, 8 not
  PASS  elapsed 48428s is consistent with the measured tokens
  FAIL  validation: 5 measurements of the winning config, 1 failed and were dropped
        (optimizer.py:1919) -> quality is cherry-picked, pass_rate=4/5
  WARN  identical config tested 5x ['passed','passed','passed','passed','quality_failed']
  WARN  12 configurations differ only in (eval_batch_size, physical_batch_size, parallel,
        context_checkpoints) (ctx=4096) -> cannot change single-request decode speed
  FAIL  long_context at ctx=8192 used only 297 prompt tokens (4% of the window)
  FAIL  duration_ms missing on 18/23 configurations
  WARN  recorded durations sum to 6.3 h of 13.5 h (7.2 h unexplained)
  FAIL  quality gate 0.98: identical configs scored [0.9333] (rejected) vs
        [0.9824, 0.9833] (accepted); the decision rests in a 0.0491 window
  WARN  coding_task scored [0.667, 0.917] across identical configurations
  WARN  long_context scored [0.996, 1.0] across identical configurations
```

Usage:

```bash
python tools/check_run_integrity.py                    # newest 5 runs
python tools/check_run_integrity.py --run 7ae5ffae     # one run (id prefix ok)
python tools/check_run_integrity.py --all              # every run in the DB
```

Exit code 0 = trustworthy, 1 = at least one FAIL. **Run it immediately after the new Q2 campaign**
and gate the report on it. It is the optimizer-side counterpart of `tools/selfcheck_sandbox.py`
(which reproduces the four sandbox bugs deterministically, with no model).

Related artefacts already in the repo:

| file | purpose |
| --- | --- |
| `tools/check_run_integrity.py` | this tool |
| `tools/selfcheck_sandbox.py` | sandbox task/validator self-test, 26 findings, ~1 s |
| `tools/build_scoreboard.py` | `results/SCOREBOARD.md` + `.csv` from comparable metrics only |
| `results/DEBUG-REPORT-20261106.md` | the sandbox side |
| `docs/plans/SANDBOX-V2-REDESIGN.md` | sandbox redesign + output contract |

---

## 8. Answers to the direct questions

**"Will there be more than 1 probe this time?"** Only if you change the command. The `quick` preset
(`reps=1`, validation 2, stages `speed/quality/validation`) plus a warm `data/benchmark_cache/`
produced exactly one stored configuration in 21 minutes. Use `--preset standard`, clear the cache,
and expect ~40–90 min per configuration at ctx 4096 and ~60–85 min at ctx 8192 on a 27B — budget
the run accordingly rather than assuming it will finish quickly.

**"Is it reliable?"** The measurement path is not yet: it can replay instead of measure (§2.1),
it rejects good configs nondeterministically (§2.7), it drops failed validation rounds (§3.2), and
it cannot tell you why (§2.7, #5). None of these are model problems.

**"Does it waste time on useless combinations?"** Yes, and the two biggest items are measured, not
guessed: 6.3 h validating a 297-token prompt at "8192 context", and ~1 h sweeping four parameters
(`eval_batch_size`, `physical_batch_size`, `parallel`, `context_checkpoints`) that cannot change a
single-request decode rate. Fixing #8, #9 and #3 removes roughly **7 of the 13.5 h** on a 27B
campaign without losing a single meaningful measurement.
