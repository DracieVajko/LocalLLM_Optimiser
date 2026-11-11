# Run dedupe and per-test sandbox history — Design

**Date:** 2026-11-11
**Status:** Design approved by the user, pending implementation plan
**Scope:** `results/sandbox_runs.jsonl`, `results/bakeoff/runs.jsonl`, `/sandbox` history UI

## 1. Problem

Two separate problems, one shared cause: a run record does not say *what* was run, only *which model and task*.

1. **Duplicate history.** Every attempt appends a row. `results/sandbox_runs.jsonl` holds 86 rows across 45 (model, task) pairs (22 pairs duplicated, 41 extra rows); `results/bakeoff/runs.jsonl` holds 77 rows across 43 pairs (21 duplicated, 34 extra). Re-running the same test leaves the old attempt next to the new one with no way to tell whether it was the same test or a different prompt/settings.
2. **History UI.** Clicking a model opens a panel *below* the whole model table, so the expansion can appear far from the row that was clicked, and the per-run list mixes "which test" with "which attempt".

## 2. Requirements

- A new run of the **same model + task + prompt + settings** replaces the previous record once it has been measured. A crash, timeout or empty answer (`status != "measured"`) never deletes a real result.
- A run with a **different prompt or different model settings** is a different test and both records stay.
- The rule applies to single-model sandbox runs *and* to bakeoff runs, because both write history that the UI reads.
- Removed records take their artifact directories with them.
- Existing duplicates are cleaned up now, with a dry-run first.
- Sandbox history: clicking a model expands its tests **in place**; `View` on a test shows that run's detail (artifacts, failures, score) with a picker when the test has several configs.

Non-goals: `/history` and `SCOREBOARD.md` keep their current "newest per model+task" grouping (they read the same cleaned file, so they benefit without a rule change); no SQLite migration; no change to task prompts or scoring.

## 3. Run identity

`sandbox_history.fingerprint(model, task, prompt, settings) -> "rk1:<16 hex>"`

sha256 over canonical JSON (`sort_keys=True`, compact separators) of:

```json
{"model": "...", "task": "...", "prompt_sha": "<sha256 of prompt bytes>", "settings": {...}}
```

`prompt_sha` covers the prompt sent on the first attempt (task prompt or `--custom-prompt`/`--scene` variant), before any repair feedback.

Settings are normalized so that equivalent invocations collapse. Every writer builds them through one helper:

| key | value |
|---|---|
| `temperature` | `0.0` for CLI/bakeoff, `0.2` for the `/lab/sandbox-run` web job (its current hardcoded value) |
| `max_output_tokens` | task definition value (web job: `2048`, its current hardcoded value) |
| `thinking` | `bool` |
| `reasoning_effort` | `null` for `off`/`on`/`default`/empty, else the level string |
| `context_length` | effective context used for the load (`null` when the job does not choose one) |
| `kv_ram` | `bool` |
| `safe` | `bool` |

The web job's different temperature/output budget is intentional: those runs are not equivalent to a CLI run and must not replace its record.

Consequences:

- `lab sandbox --reasoning off --context 8192` and `lab bakeoff --no-thinking --context 8192` produce the same key.
- `--context 4096`, `--thinking`, `--reasoning high`, `--kv-ram` or `--safe` each change the key.
- A custom prompt or a scene variation changes the key.

Records gain three fields: `run_key`, `settings`, `prompt_sha`. Legacy records keep working without them.

## 4. Dedupe on write

`sandbox_history.record_run(...)` gains `prompt` and `settings` parameters and, after appending, prunes the file:

1. Skip entirely unless `status == "measured"` and `task` is not `(load)` or `(crash)`.
2. Keep every row that is not the same `run_key` for the same model+task. Legacy rows (no `run_key`) are never matched, so they survive until the one-off prune.
3. Delete the workdirs of removed rows, guarded: the resolved path must be a directory inside `results/sandbox/` or `results/bakeoff/` and must not be the new run's workdir.
4. Rewrite atomically (temp file in the same directory + `os.replace`) so an interrupted write cannot truncate history. Malformed lines are preserved verbatim.

`record_run` still returns the stored record; the number of replaced rows is exposed to callers that want to log it.

`bakeoff._run_task` builds the same fingerprint and passes it to `record_run`, then `run_bakeoff` applies the same rule to `results/bakeoff/runs.jsonl` (rows carry `run_key`, `settings`, `prompt_sha`). Both files therefore stay one-row-per-identical-test.

## 5. One-off cleanup: `lab prune-runs`

```
python -m lm_optimizer.cli.main lab prune-runs            # dry run, prints the plan
python -m lm_optimizer.cli.main lab prune-runs --apply    # rewrites both files
```

Rules per (model, task):

- keyed rows: keep the newest measured row per `run_key`;
- legacy rows (no key): keep the newest measured row for the pair, and drop the rest;
- if a keyed row exists for the pair, legacy rows for that pair are dropped as superseded (a legacy row carries no evidence of a different prompt or settings).

Output: one line per collapsed group (`model`, `task`, kept key/date, removed count) and the artifact directories to delete. `--apply` rewrites both JSONL files and removes those directories with the same path guard as §4.

Expected effect on current data: sandbox 86 → 45 rows, bakeoff 77 → 43 rows.

## 6. Sandbox history UI

Model rows stay a table; the expansion moves inline, directly under the clicked row, in a single `<tr class="sb-expand"><td colspan="N">`.

```
Model                              Tests  Best           Last
▾ nvidia-nemotron-3.5-bolt-e4b      5    0.93 email     2026-11-11 19:50
    task             result    score  date           runs  action
    email_write      PASS      1.00   11-10 21:14    1     [View]
    blender_city     FAIL      0.00   11-11 19:50    2     [View]
    company_website  PASS      1.00   11-10 19:02    1     [View]
```

- State: `expandedModel`, `openTask`, `selectedRun`, `pinnedRun`. Only the expansion container is re-rendered, so the row does not collapse on every click.
- `View` swaps the test list for the run detail: task, status badge, score, duration, artifact links (existing `/api/sandbox/files` opener), critical failures, and `← Back to tests`.
- When a test has more than one surviving config, a `<select>` lists them (`date · score · short run_key`) and switches the detail without leaving the view.
- `Pin` marks a run; other runs then offer `Compare with pinned`, reusing the existing split view.
- States: no history → existing hint; fetch error → inline error with a retry button; a run with no artifacts → "no files" line instead of an empty list.

## 7. Files touched

| File | Change |
|---|---|
| `lm_optimizer/services/sandbox_history.py` | `fingerprint`, settings normalization, dedupe + atomic rewrite, prune helper |
| `lm_optimizer/services/bakeoff.py` | fingerprint + settings on rows, dedupe of `runs.jsonl` |
| `lm_optimizer/cli/lab.py` | pass prompt/settings to `record_run`; `lab prune-runs` command |
| `lm_optimizer/api/routes.py` | pass prompt/settings in the web sandbox job; record its result in history (today the `/lab/sandbox-run` job writes no history at all — a small gap this closes so UI runs are deduped like CLI runs) |
| `lm_optimizer/ui/static/js/sandbox.js` | inline accordion, per-test rows, detail view, run picker |
| `tests/test_sandbox_history_dedupe.py` | new: key equivalence, replacement rules, guards, prune |
| `tests/test_sandbox_lab.py`, `tests/test_bakeoff_service.py`, `lm_optimizer/tests/test_dashboard_api.py` | adjusted expectations |

## 8. Testing

- Key equivalence: CLI defaults vs bakeoff `--no-thinking` at the same context → same key; each of context/thinking/effort/kv/safe/custom-prompt → different key.
- Replacement: second measured run with the same key leaves one row and removes the old workdir; `not_measured` leaves both rows; `(load)`/`(crash)` untouched.
- Guard: a workdir outside `results/` is never deleted; a malformed JSONL line survives a rewrite.
- Prune: dry run writes nothing; `--apply` collapses real-shaped fixtures to one row per pair and deletes only in-scope directories.
- Bakeoff: two rows with the same key collapse; different `--context` rows both stay.
- Web job: a completed `/lab/sandbox-run` writes exactly one history record with `temperature=0.2`, and its key differs from the CLI run of the same task.
- UI: `node --check`, plus a CDP probe — expand a model, see one row per test, `View` shows the detail, `Back` restores the list, and a two-config test exposes the picker.
- End-to-end: `lab prune-runs` dry run on the real files, counts match the expectation in §5, then `--apply` and `pytest` on the sandbox/history suites.

## 9. Risks

- **Rewrite on every run** touches a file the web UI polls. Mitigation: atomic replace, keep the read path unchanged, rewrite only when a matching key exists (no duplicates → no write).
- **Legacy collapse is lossy by definition**: those rows cannot prove a different config. The dry run prints exactly what would go, and `--apply` is explicit.
- **Concurrent writers** (bakeoff + web job) could interleave read-modify-write. Existing `ModelGate` already serialises model loads; the rewrite is milliseconds and the file is small. Accepted for this scope.
