# OpenCode fix round 3 — after the 2026-11-07 campaign

> Paste as the task. Round 3 targets the **blocker that made 5 models produce 0 winners** plus the
> sandbox items that Round 2 did not finish. Read §1 first: the pipeline is now honest enough to
> fail, and it is failing for the wrong reason.

---

## 0. Where we are

Round 2 landed well. Evidence from `data/optimizer.db` and `results/sandbox_runs.jsonl`:

| item | state | proof |
| --- | --- | --- |
| `long_context` document scaling | **LANDED** | `suite.py:178-193`; prompt tokens 297 → 4 118–4 264 |
| real repetitions (no cache replay) | **LANDED** (via `--preset standard`, reps=3) | runs now take 3.7–5.1 h and validation failures are real |
| validation failures persisted | **LANDED** | `check_run_integrity` reports `pass_rate 0/2` instead of `1/1` |
| `duration_ms` recorded | **MOSTLY** | 1/20 missing (was 17/19) |
| sandbox: research sources injected | **LANDED** | `research_synthesis` 0.00–0.13 → **0.87** |
| sandbox: email+calendar duration | **LANDED** | 0.83 → **1.00** |
| sandbox: sweep timeout 3600 s | **LANDED** | commit `b5f91ec` |
| blender artifact name | **LANDED** | `build_scene.py` instead of `scene.blend` |
| quality gate | **NOT DONE** | still `0.98`, unreachable |
| Pareto frontier | **NOT DONE** | empty with 17–19 passed configs |
| stage-4 no-op sweep | **NOT DONE** | 12–15 configs at ctx 4096 |
| phase timing / cost attribution | **NOT DONE** | 4.2 h of 5.1 h unexplained |
| sandbox: artifact contract, wiring, `no_*` critical | **NOT DONE** | `tools/selfcheck_sandbox.py` → **23 findings** |

**Result of the campaign: 5 models, 14.4 h, 0 winners.** Every run ended
`completed_no_validated_winner`. Round 3 exists to make that stop.

---

## 1. The blocker (fix this before anything else)

`benchmark/suite.py:188-191` now asks a **different question** than the grader evaluates:

```python
# suite.py  (NEW, landed in round 2)
needle = "NOTE: the harbour access code is 7-TANGO."
prompt = ... + "\n\nQUESTION: What is the harbour access code mentioned in the document?"
```

```python
# scoring/evaluator.py:338-342  (UNCHANGED)
elif prompt_def.category == "context":
    keywords = ["solar", "wind", "hydro", "geothermal", "biomass"]
    found = sum(1 for kw in keywords if kw in output.lower())
    scores["factual_consistency"] = min(1.0, found / len(keywords) * 1.5)
```

The model answers `7-TANGO`; the grader looks for "solar/wind/hydro" and scores
`factual_consistency = 0`. And `task_completion = min(1.0, tokens / min_tokens)` with
`min_tokens = 150`, so a one-token answer scores 0.007.

```
0.007 (task) + 0 (factual) + 1.0 (format) + 0.5 (no_truncation) + 1.0 + 1.0 = 3.507
3.507 / 6 = 0.584        ← exactly the 0.584 observed for every model
```

So `long_context` is **structurally unpassable**, the 5-test mean lands at 0.83–0.92, and the 0.98
gate rejects every configuration. `check_run_integrity.py` states it plainly:

```
FAIL  every measurement is below the quality gate 0.98 (best 0.9100)
      -> the gate is unreachable for this suite
```

---

## 2. Work packages

### WP R3-1 — `long_context` grades what it asks (P0, blocking)

**Change.** Keep the scaled document. Do **one** of these, and do not mix them:

- **R3-1a (hotfix, preferred):** restore the original question —
  `prompt = doc_text[:doc_start] + repeated + doc_text[doc_end:]`.
  The keyword grader and `min_tokens=150` become valid again immediately.
- **R3-1b (correct, do it right after):** keep the needle question, and give the context category a
  *needle* grader (`pass` iff the normalised answer contains `7TANGO`), while keeping a separate
  summarisation case with the keyword grader.

**Never** leave a case whose prompt and grader disagree. Add a guard so it cannot happen again:

```python
# tests/test_suite_grader_consistency.py
def test_context_case_is_graded_by_what_it_asks():
    case = next(c for c in create_benchmark_cases(8192) if c.category == "context")
    text = case.prompt.lower()
    assert ("access code" in text) == ("7-tango" in text)   # question and needle agree
    # and the grader's vocabulary must appear in the question it grades:
    grader_words = ["solar", "wind", "hydro", "geothermal", "biomass"]
    if "summarize" in text:
        assert sum(w in text for w in grader_words) >= 3
```

**Acceptance.** A perfect answer (`"7-TANGO"` for the needle variant, or a 5-source summary for the
keyword variant) scores ≥ 0.95 on that case. A wrong answer scores < 0.5. The two cases are
distinct test names in `quality_by_test`.

### WP R3-2 — Recalibrate the quality gate (P0, blocking)

**Evidence.** Even with R3-1 fixed, `long_context` is now genuinely hard (4 200 tokens, not 297).
A single test at 5/6 gives aggregate `0.967 < 0.98` → the winner is rejected forever. The gate was
calibrated against a test that measured nothing.

**Change.** In `services/quality.py` (`passes_threshold`) and wherever `minimum_score` is applied:

```python
def passes_threshold(self, quality) -> bool:
    if quality.critical_failed:          # e.g. invalid JSON, code does not compile
        return False
    return quality.overall >= self.config.minimum_score      # default 0.90, not 0.98
```

- New `QualityScore.critical_failed: bool`, set by the evaluator for: empty output, invalid JSON in
  `structured_output`, code that does not compile in `coding_task`, missing required keys.
- `profiles/registry.py`: balanced `minimum_quality = 0.90`, speed `0.88`, context `0.90`,
  quality-profile `0.93`. Keep the old value readable via `--quality-threshold` for reproducibility.
- Fix the contradictory message: it prints "below threshold 0.9" while the run stores `0.98`
  (`optimizer.py:4690` prints `self.quality.config.minimum_score` but the comparison happened
  against a different value). One threshold, one source of truth, printed from the value actually
  compared.

**Acceptance.** Unit test: aggregate 0.916 with no critical failure → passes; 0.916 with
`critical_failed=True` → fails. Report prints the number it enforced.

### WP R3-3 — Pareto and validation persistence (P0)

**Evidence.** `check_run_integrity` on the new runs:

```
FAIL  Pareto frontier empty with 17 passed configuration(s) -> impossible
FAIL  validation: 1 measurements of the winning config, 1 failed and were dropped
      -> quality is cherry-picked, pass_rate=0/1
```

**Change.** (Same as brief-1 WP 1.5 and round-2 R2-1/R2-6, still open.)

1. Recompute the frontier after quality validation; assert `len(frontier) >= 1` when any config
   passed; log the inputs on failure.
2. Keep **every** validation round in `tested_configs` with its status; compute
   `validation_pass_rate`, `quality_median`, `speed_median`, `speed_iqr`.
3. Report `Quality: 0.83 (median) · validation pass rate 0/2`, never a bare number.
4. A run whose winner has `n_measured < 2` is `success_single_sample`, not `success`.

**Acceptance.** Both FAIL lines disappear from `check_run_integrity.py` on a new run.

### WP R3-4 — Make the filled prompt actually reach the window (P1)

**Evidence.** `long_context` at ctx 8192 now sends **4 118–4 264** tokens = **50–52 %** of the
window, below the 60 % threshold. The builder assumes 3.6 chars/token; the real ratio is ~3.9.

**Change.** Implement the calibration loop from `docs/plans/OPENCODE-WP-C2-RECALL-PROBE.md` §2.5:
build, read the server's `prompt_tokens`, and if it is below `0.6 * ctx`, rebuild **once** with
`chars_per_token *= target / measured`; persist the calibration per model in
`data/capability/token_calibration.json`. Assert `prompt_tokens >= 0.6 * context_length` before
scoring, else mark the case `insufficient_context` (a hard failure for that config, never a silent
pass).

**Acceptance.** At ctx 8192 `prompt_tokens >= 4900`; at ctx 16384 `>= 9800`. The measured value is
printed next to the context in the report.

### WP R3-5 — Blender end-to-end (P1)

**Evidence.** Round 2 got the *filename* right (`build_scene.py`) but not the pipeline:

```
run 20261107_165436   build_scene.py  3 766 B   valid Python, 8/8 scene markers  ← the good one
run 20261107_162941   build_scene.py 21 930 B   SyntaxError line 7              ← scored 0.70
run 20261107_171336   build_scene.py 29 718 B   reasoning loop, 74x "import bpy" ← scored 0.12
```

- the good script is wrapped in a ` ```python ` fence → Blender cannot parse it;
- Blender is **not installed**, so `scene.blend` is never produced, yet the task still scores
  0.70–0.76 from text markers;
- `tools/selfcheck_sandbox.py` still reports `blender perfect_script 0.76` and
  `prose_dump 0.70` (both must be ≤ 0.20).

**Change.**

1. `_materialise` (or the sandbox writer) must **strip markdown fences** from `code`/`python` kinds
   before writing. Persist `fences_stripped: true`.
2. Validate the artifact by **executing it**: `blender --background --python build_scene.py`, then
   introspect `scene.blend` (object counts by type, materials, camera, animated objects, frame range,
   rendered frames). If `blender` is absent → status `not_measured`, reason `blender_missing`, and
   the task **cannot score above 0.2**. Never award text-marker points for a file that was never run.

   **Verified on this machine on 2026-11-07:** Blender 5.2 (Microsoft Store build) saves `.blend`
   **zstd-compressed**, so the file starts with `28 B5 2F FD`, *not* `BLENDER`. Only the decompressed
   header reads `BLENDER17-01` (format 17). A validator that requires a literal `BLENDER` prefix will
   reject every modern .blend. Accept either form:

   ```python
   def blend_is_valid(path: Path) -> bool:
       head = path.read_bytes()[:4096]
       if head[:7] == b"BLENDER":                     # uncompressed (<= 3.x, or save with compress=off)
           return True
       if head[:4] == bytes.fromhex("28b52ffd"):      # zstd (4.x+, the default)
           try:
               from compression import zstd           # Python 3.14+
               return zstd.ZstdDecompressor().decompress(path.read_bytes())[:7] == b"BLENDER"
           except Exception:
               return True   # magic matches; do not fail a file you cannot decompress
       return False
   ```

   The same finding applies to the *Store* install layout: there is no `C:\Program Files\Blender
   Foundation` and no uninstall registry entry — the only runnable path is the app execution alias
   `%LOCALAPPDATA%\Microsoft\WindowsApps\blender-launcher.exe`, which **does** honour
   `--background --python <file>` (verified by running a real script). `find_blender()` must scan
   `WindowsApps` and accept `blender-launcher.exe`, not just `blender.exe`.
3. Reject an artifact that fails `ast.parse` as `invalid_python` (the 21.9 KB and 29.7 KB runs).
4. Add `blender_path` to the manifest so the report says which interpreter ran it.

**Acceptance.** `tools/selfcheck_sandbox.py`: `blender perfect_script` ≤ 0.2 and `prose_dump` ≤ 0.2.
A run with Blender installed produces a `scene.blend` that `blend_is_valid()` accepts (uncompressed
`BLENDER` **or** zstd magic with a `BLENDER` payload) and ≥1 PNG in `frames/`. A run without Blender
reports `not_measured (blender_missing)`.

Reference implementation that already works: `python tools/preview_blender.py --run <dir> --launch`
(strips fences, drives the script, renders one frame, validates the .blend both ways).

### WP R3-6 — Sandbox wiring and strict-instruction gates (P1)

**Evidence.** `tools/selfcheck_sandbox.py` → 23 findings. The top ones:

```
[wiring]    web_dashboard: validator emits 'html_parses' but no task check consumes it
[wiring]    web_dashboard: task check 'has_table_or_grid' has no custom validator result
[critical]  email_write: 'no_placeholders' is not critical — [Your Name] only costs 27 %
[critical]  web_dashboard: 'no_external_scripts'/'no_external_styles' not critical
[fixtures]  research_synthesis: perfect_answer scored 0.73 (expected ≥0.90)
[fixtures]  web_fetch_brief: fenced_json scored 0.87 (expected ≥0.95)
[fixtures]  calendar_event: prose_json scored 0.67 (expected ≥0.95)
```

**Change.**

1. One canonical name per check; `score_attempt` logs a warning when a custom result has no matching
   task check (so a mismatch can never silently discard a measurement).
2. Every check enforcing an explicit "only" / "no X" instruction gets `critical=True`.
3. JSON checks: strip fences and extract the outermost `{...}` before `json.loads`, so a
   fenced-but-correct answer scores 1.0 and a prose answer scores 0.0.
4. Fix the regression that made `research_synthesis perfect_answer` drop to 0.73 — find which check
   changed and either revert or update the fixture with a written justification.

**Acceptance.** `python tools/selfcheck_sandbox.py` exits **0**.

### WP R3-7 — Stop the no-op sweep (P1, third request)

**Evidence.** Every new run still spends 12–15 configurations on `eval_batch_size`,
`physical_batch_size`, `parallel`, `context_checkpoints` at ctx 4096. Two campaigns measured these as
no-ops. Simultaneously the winner is decided by a `parallel=1` policy that should be a constant.

**Change.** (round-2 R2-4, still open.)

- `interactive` ⇒ `parallel = 1` by default; never sweep it.
- Freeze `eval_batch_size=2048`, `physical_batch_size=512`, `context_checkpoints=32` with a comment
  citing `docs/plans/CAMPAIGN-DESIGN-V2.md`.
- Replace the sweep with the `gpu_ratio ∈ {auto, 0.7, 0.5}` sweep through the CLI channel
  (`lms load --gpu`), 3 speed probes each, early stop when two values agree within 6 %.

**Acceptance.** An interactive run shows exactly one `parallel` value and at most 9 speed probes in
that stage; `check_run_integrity.py` stops warning about no-op configurations.

### WP R3-8 — Phase timing (P1, third request)

**Evidence.** `check_run_integrity`: "recorded durations sum to 0.9 h of 5.1 h (4.2 h unexplained)".
We still cannot say what the campaign spent its time on.

**Change.** `PhaseTimer` around `unload/load/verify/preheat/per_case/prefill/generation/score/persist`,
stored as `generation["phase_timings_ms"]`, asserted to sum to ≥90 % of `duration_ms`.

**Acceptance.** No `unattributed` WARN for a new run; the PR description contains one real breakdown
for a ctx-8192 configuration.

---

## 3. Order, and one hard rule

| PR | packages |
| --- | --- |
| 1 | R3-1, R3-2 |
| 2 | R3-3 |
| 3 | R3-7, R3-8 |
| 4 | R3-4 |
| 5 | R3-5, R3-6 |

**Do not start another model campaign until PR 1 is merged.** The last one cost 14.4 h and produced
zero winners because of a one-line question/grader mismatch. Verify with a *single* model first:

```bash
python -m lm_optimizer.cli.main run --model nvidia-nemotron-3.5-bolt-e4b --preset standard
python tools/check_run_integrity.py --run <id>
```

That run must end `success` with a non-empty Pareto frontier and a stated validation pass rate
before any other model is touched.

---

## 4. Definition of done for round 3

1. `python tools/selfcheck_sandbox.py` → exit 0.
2. `python tools/check_run_integrity.py --run <new>` → zero FAIL.
3. In the new report:
   - `long_context` scores what its own question asks (perfect answer ≥ 0.95),
   - `Quality` carries a validation pass rate and states the threshold actually enforced,
   - Pareto is non-empty,
   - exactly one `parallel` value appears (1),
   - phase timings sum to ≥90 % of each configuration's duration,
   - `long_context` prompt ≥ 60 % of the context, printed next to the context size.
4. `nemotron-3.5-bolt-e4b` reaches `status=success` with a real winner.
5. Blender: either `not_measured (blender_missing)` or a `scene.blend` that passes
   `blend_is_valid()` (zstd-compressed is expected on Blender 4+).

---

## 5. Report back with

- the one-line diff of R3-1 and the test that proves prompt and grader agree,
- the `long_context` scores before/after for the same model (expect ~0.58 → 0.85–1.00),
- whether `nemotron-e4b` finally produced a winner, and at what quality,
- the phase-timing breakdown for one ctx-8192 configuration,
- what is still in the 23 selfcheck findings and why each is deferred (if any).
