# OpenCode task — WP C2: deterministic context recall probe

> Standalone package. Paste as the task. It can ship **before** anything else in
> `docs/plans/CAMPAIGN-DESIGN-V2.md` and it unblocks all of it.

---

## 0. Why this exists (verified, not a hypothesis)

The benchmark suite has a case called `long_context`. It does not test long context.

`lm_optimizer/benchmark/suite.py` scales the document only when `context_length > 8192`, and even
then it inserts `---` separator lines. Measured across every run in `data/optimizer.db`:

```
long_context prompt tokens    ctx 4096 → 285    ctx 8192 → 297    ctx 32768 → 294–305
```

**57 of 57 runs with a context case never sent more than ~305 prompt tokens, at any context length.**
Consequences that are already in the shipped reports:

- `Context: 8192` and `maximum stable context: 8192` in `results/*-best.md` describe a window that was
  never exercised.
- `reporting.py:669` computes "maximum stable context" as `max(tested, key=context_length)` — the
  largest context *configured*, presented under the heading "Contexts (measured, not assumed)".
- There is no measurement anywhere in the tool that answers "how much context can this model
  actually use on this machine".

This package adds that measurement. It is one small, deterministic, cheap case. Everything about
context in the redesign depends on it.

---

## 1. Non-goals (do not do these here)

- Do **not** touch `_generate_context_candidates`, `min_context`/`max_context`, or the context ladder.
  (That is WP C1, a later package.)
- Do **not** delete or rewrite the existing `long_context` case. Leave it; it still measures document
  summarisation, just not context length. Only fix its *name* if trivial.
- Do **not** change stage order, scoring weights, or the winner-selection logic.
- Do **not** add dependencies. Stdlib + the existing client only.
- Do **not** run a GPU campaign to "verify". Everything below is testable with a fake client.

---

## 2. Specification

### 2.1 A first-class case kind

Add a benchmark case kind `recall` alongside the existing prompt cases, so it can be run through the
same load/verify/preheat/measure skeleton as any other case:

```python
@dataclass
class RecallProbeSpec:
    target_tokens: int          # the context size being probed, e.g. 8192
    fill_ratio: float = 0.85    # fraction of target_tokens to actually fill
    depth: float = 0.5          # needle position, 0.0 = start, 1.0 = end
    depth_points: tuple[float, ...] = (0.5,)   # (0.1, 0.5, 0.9) for the deep test
    max_tokens: int = 24
    temperature: float = 0.0
```

### 2.2 Prompt construction

Deterministic, no randomness, no network. Build by character budget first, then verify against the
server's reported `prompt_tokens` (§2.5).

```
CHARS_PER_TOKEN = 3.2        # conservative for English prose + code; re-calibrated in §2.5

# Four distinct paragraphs, rotated deterministically. A single paragraph repeated
# hundreds of times is degenerate text (near-zero entropy) and can make a model
# behave differently than on real prose — do not use one paragraph.
FILLER_PARAGRAPHS = (
    "The harbour master logged every vessel before the fog lifted. Cargo manifests "
    "were checked against the register, and the watch officer noted the tide, the "
    "wind and the number of crew on each deck.",
    "Coastal shipping follows a fixed schedule: outbound at first light, inbound on "
    "the flood tide. Pilots board outside the breakwater and remain aboard until the "
    "vessel is moored alongside the quay.",
    "Maintenance of the navigation lights is carried out quarterly. Each lamp is "
    "tested for range and colour, and any fault is logged and reported to the "
    "regional authority within one working day.",
    "The register of arrivals has been kept in the same form since the station "
    "opened: date, vessel name, flag, tonnage, cargo class, and the signature of the "
    "officer on watch. Older volumes are stored in the basement archive.",
)

DISTRACTORS = [              # 5 decoy codes placed in the filler; a guesser will pick one
    "CODE-1ALPHA-0001", "CODE-2BRAVO-0002", "CODE-3CHARLIE-0003",
    "CODE-4DELTA-0004", "CODE-5ECHO-0005",
]
NEEDLE = "CODE-7TANGO-4423"          # the harbour access code
NEEDLE_KEY = "7TANGO4423"            # normalised form the answer must contain
QUESTION = ("\n\nWhat is the harbour access code mentioned in the document above? "
            "Answer with the code only, nothing else.")
```

Build:

1. `target_chars = int(target_tokens * fill_ratio * CHARS_PER_TOKEN)`.
2. Fill by rotating `FILLER_PARAGRAPHS[i % 4]` until `len >= target_chars`; truncate at a paragraph
   boundary. (Assert that no paragraph is the immediate repeat of the previous one.)
3. Insert a distractor code every ~15 % of the document.
4. Insert `"The harbour access code is CODE-7TANGO-4423."` at position `depth` — on its own line,
   surrounded by blank lines.
5. Append `QUESTION`.

**Assert at build time** (raise `ValueError`, do not silently continue):

- the needle appears exactly once,
- `NEEDLE_KEY` does not appear in the filler or in any distractor,
- `len(prompt) >= 0.9 * target_chars`.

### 2.3 Response and grading (three-way, not binary)

Call the existing client with `temperature=0.0`, `max_tokens=24`, `reasoning=None`.

Normalise the answer: uppercase, remove every character that is not `A-Z0-9`.

| outcome | condition | status |
| --- | --- | --- |
| **recall** | normalised answer contains `NEEDLE_KEY` | `pass` |
| **wrong_code** | answer contains any distractor key (`1ALPHA0001`, …), i.e. confidently wrong | `fail_hallucinated` |
| **unknown** | answer does not contain any code (`unknown`, `not stated`, `cannot find`, empty) | `fail_not_found` |
| **ambiguous** | contains the needle **and** a distractor | `fail_ambiguous` |

The three-way split matters: `fail_hallucinated` and `fail_not_found` mean different things about a
model, and on weak hardware the difference decides whether it is usable at long context at all.

Record the raw answer (first 200 chars) and the normalised answer in the result — never only the
verdict.

### 2.4 Cost model — this probe is expensive, and it must say so

Prefill dominates. Measured on this host: **prompt processing at 19–25 tok/s**, load 20–33 s,
decode 2.6–3.9 tok/s. So a probe is roughly:

```
estimated_cost_s ≈ load_time_ms/1000 + (target_tokens * fill_ratio) / prompt_tok_s
```

with the observed `prompt_tok_s` from the previous probe (bootstrap: 20 tok/s).

| target ctx | filled tokens | prefill @19 tok/s | total probe |
| --- | --- | --- | --- |
| 2 048 | ~1 700 | 90 s | **~2 min** |
| 4 096 | ~3 500 | 184 s | **~3.5 min** |
| 8 192 | ~7 000 | 368 s | **~6.5 min** |
| 16 384 | ~14 000 | 736 s | **~12.5 min** |
| 32 768 | ~28 000 | 1 470 s | **~25 min** |

Requirements:

- `RecallProbeSpec` is rejected when `estimated_cost_s > max_probe_cost_s` (default **900 s**), and
  the caller gets `skipped: cost > cap` — **not** a failure and not a silent skip.
- The measured `prompt_tokens` and `prompt_processing_ms` from the response are persisted, so the cost
  model is re-calibrated from real data on every run.
- One probe = one generation. Do not add repeats here; repeats belong to the campaign stage.

### 2.5 The honesty gate (the most important part)

The server may silently truncate a prompt that exceeds the loaded context, or the character↔token
estimate may be off. Detect both:

```
built_tokens_estimate = len(prompt) / CHARS_PER_TOKEN
measured = prompt_tokens from the response stats

if measured < 0.60 * target_tokens:
    -> re-build once with CHARS_PER_TOKEN *= (target_tokens / measured), retry ONE time
    -> if still short: status = "fail_prompt_truncated", verdict = fail (never pass)

if abs(measured - built_tokens_estimate) > 0.25 * measured:
    -> update a per-model `chars_per_token` calibration and persist it
       (data/capability/token_calibration.json) so the next run is accurate first time
```

A probe that is marked `pass` must carry `prompt_tokens >= 0.60 * target_tokens` **in the record**.
No record, no pass. This is the single assertion that makes "context 8192" a measurement instead of a
claim.

### 2.6 Output record

Persist as `generation["recall"]` on the result and in the report:

```json
{
  "target_tokens": 8192,
  "fill_ratio": 0.85,
  "depth": 0.5,
  "prompt_tokens": 7341,
  "prompt_processing_ms": 386420,
  "completion_tokens": 11,
  "built_tokens_estimate": 7280,
  "chars_per_token": 3.18,
  "estimated_cost_s": 388,
  "actual_cost_s": 402,
  "answer_raw": "CODE-7TANGO-4423",
  "answer_normalised": "CODE7TANGO4423",
  "status": "pass",
  "distractors_present": 5,
  "truncated": false
}
```

The deep test (`depth_points=(0.1, 0.5, 0.9)`) returns a list of these and an aggregate
`recall_all_depths: bool` plus `worst_depth: 0.9`.

---

## 3. Where to wire it

| file | change |
| --- | --- |
| `lm_optimizer/benchmark/suite.py` | add `RecallProbeSpec`, `build_recall_prompt()`, the constants above; do not modify the existing `BENCHMARK_SUITE` entries |
| new `lm_optimizer/services/recall_probe.py` | `build_prompt()`, `grade_answer()`, `estimate_cost_s()`, `run_recall_probe(client, model_id, ctx, spec)` — pure functions where possible so they are unit-testable without a server |
| `lm_optimizer/services/benchmark.py` | route a `recall` case through the existing load/verify/preheat/measure path; store the record from §2.6 |
| `lm_optimizer/cli/lab.py` | new command `lab recall --model <id> --ctx 8192 [--depth 0.5] [--depth-set 0.1,0.5,0.9]` so it can be run alone, without a campaign |
| `lm_optimizer/services/reporting.py` | when a run contains recall records, print the context-capacity sub-table (see §5); when it does not, print `context recall: not measured` instead of the empty `## Contexts` section |
| `tools/check_run_integrity.py` | new check: every `long_context`-style claim must be backed by a recall record, or be labelled `not measured` |

---

## 4. Acceptance

### Unit tests (no server, fake client)

1. `test_prompt_contains_needle_once` — needle exactly once, 5 distractors present, filler does not
   contain `NEEDLE_KEY`.
2. `test_filler_not_degenerate` — no paragraph appears twice in a row; at ctx 8192 at least 3 of the
   4 `FILLER_PARAGRAPHS` are used.
3. `test_prompt_length_target` — for `target_tokens` in `{2048, 8192, 16384}`, the character build is
   within ±10 % of `target_chars`.
4. `test_grade_pass` — `"CODE-7TANGO-4423"`, `"**CODE-7TANGO-4423**"`, `"7tango4423"` all → `pass`.
5. `test_grade_hallucinated` — `"CODE-4DELTA-0004"` → `fail_hallucinated` (must not be `pass`).
6. `test_grade_not_found` — `"I cannot find that in the document."` and `""` → `fail_not_found`.
7. `test_grade_ambiguous` — needle + distractor in one answer → `fail_ambiguous`.
8. `test_truncation_gate` — fake stats reporting `prompt_tokens = 1200` for `target_tokens = 8192` →
   `fail_prompt_truncated`, never `pass`.
9. `test_recalibrate_once` — first response short → exactly one rebuild, second attempt succeeds, and
   `chars_per_token` is persisted.
10. `test_cost_cap` — `target_tokens = 65536` with `max_probe_cost_s = 900` → `skipped (cost > cap)`,
    and the reason is recorded.
11. `test_estimate_matches_measurement` — after a run, `|estimated_cost_s − actual_cost_s| ≤ 30 %`.

### One real probe (manual, ~7 min)

```bash
python -m lm_optimizer.cli.main lab recall --model swift-qwen3.8-27b@q2_k --ctx 8192
```

Expected: `status: pass`, `prompt_tokens >= 4900`, `truncated: false`, runtime ≤ 10 min on this host.

```bash
python -m lm_optimizer.cli.main lab recall --model swift-qwen3.8-27b@q2_k --ctx 32768 --depth-set 0.1,0.5,0.9
```

Expected on a 6 GB laptop with a 12 GB model: either a genuine `pass`/`fail_*` verdict, or
`skipped (cost > cap)` if the cost model says so — **never** a `pass` without
`prompt_tokens >= 0.6 × 32768`.

### Definition of done

- `pytest` green, all 11 unit tests present.
- One real probe at ctx 8192 recorded with `prompt_tokens >= 4900`.
- `python tools/check_run_integrity.py --run <id>` still exits with no new FAIL.
- The report prints a context row with `prompt_tokens` next to the context size, or explicitly says
  `not measured`.

---

## 5. What this unblocks

Once this exists, three things that are currently fiction become measurements:

1. **The capacity curve** (WP C1): probe each rung of a geometric ladder and stop on
   `recall` failures / speed floor. No `min_context`/`max_context` guessing.
2. **`maximum stable context`**: it can finally mean "largest context where the needle was found
   with ≥ 0.6 × ctx prompt tokens", instead of "largest context we happened to configure".
3. **A usable recommendation for weak hardware**, which is the actual goal:

```
ctx    prompt_tokens  tok/s   TTFT     recall        verdict
4096   3 512          3.9     2.1 s    3/3           fastest
8192   7 341          3.6     3.6 s    3/3           ← recommended
16384  14 020         2.6     6.1 s    2/3 (deep fails)  long documents only
32768  —              —       —        not tested    cost > cap
```

---

## 6. Report back with

- the real `prompt_tokens` / `prompt_processing_ms` from the 8192 probe (this calibrates every later
  cost estimate in the redesign),
- the measured `chars_per_token` for both `swift-qwen3.8-27b@q2_k` and `@q4_k_s`,
- whether ctx 32768 produced a recall verdict or a cost-cap skip, and why,
- anything in this spec that turned out to be wrong — say it plainly, do not work around it.
