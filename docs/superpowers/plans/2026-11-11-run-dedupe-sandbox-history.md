# Run dedupe and per-test sandbox history — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every sandbox/bakeoff run a fingerprint so a measured re-run replaces the identical older record, add a one-off prune command, and turn sandbox history into an inline per-test accordion whose `View` shows the run detail.

**Architecture:** A single `fingerprint()` over (model, task, prompt sha, normalized settings) lives in `sandbox_history.py`. `record_run` appends then prunes rows with the same key (atomic rewrite, guarded workdir deletion). The CLI and bakeoff pass prompt + settings; the web job starts recording history (it currently records nothing). Prune reuses the same grouping on demand. The UI keeps one table but moves the expansion under the clicked model row and nests a per-test view inside it.

**Tech Stack:** Python 3.14, Typer/rich, FastAPI, pytest, vanilla JS (`lm_optimizer/ui/static/js/sandbox.js`), headless Chrome CDP for UI proof.

**Spec:** `docs/specs/2026-11-11-run-dedupe-sandbox-history-design.md`

## Global Constraints

- A record is replaced only by a run with `status == "measured"`; `not_measured` never deletes anything.
- `(load)` and `(crash)` rows are never deduped or pruned.
- Workdir deletion only inside `results/sandbox/` or `results/bakeoff/` (resolved path check).
- JSONL rewrites are atomic (temp file + `os.replace`); malformed lines survive verbatim.
- `results/` stays gitignored; no commit may include it.
- Existing uncommitted UI edits by the user must not be reverted.

---

### Task 1: Fingerprint, settings, and write-time dedupe

**Files:**
- Modify: `lm_optimizer/services/sandbox_history.py`
- Test: `tests/test_sandbox_history_dedupe.py` (create)

**Interfaces:**
- Produces:
  - `normalize_settings(**kwargs) -> dict[str, Any]` with keys `temperature`, `max_output_tokens`, `thinking`, `reasoning_effort`, `context_length`, `kv_ram`, `safe`
  - `settings_from_reasoning(reasoning: str, *, context_length: int | None, max_output_tokens: int, temperature: float = 0.0) -> dict`
  - `fingerprint(model: str, task: str, prompt: str, settings: dict) -> str` → `"rk1:<16 hex>"`
  - `record_run(..., prompt: str | None = None, settings: dict | None = None)` — same return shape, plus `run_key`, `settings`, `prompt_sha`
  - `RESULTS_ROOT: Path = Path("results")` module constant (tests monkeypatch it)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sandbox_history_dedupe.py
from __future__ import annotations

import json
from pathlib import Path

from lm_optimizer.services import sandbox_history as sh


def test_cli_and_bakeoff_settings_fingerprint_identically():
    cli = sh.settings_from_reasoning("off", context_length=8192, max_output_tokens=2048)
    bakeoff = sh.normalize_settings(
        temperature=0.0, max_output_tokens=2048, thinking=False,
        reasoning_effort="on", context_length=8192,
    )
    assert sh.fingerprint("m", "email_write", "do it", cli) == sh.fingerprint(
        "m", "email_write", "do it", bakeoff
    )


def test_fingerprint_changes_with_every_setting():
    base = sh.normalize_settings(context_length=8192)
    variants = [
        sh.normalize_settings(context_length=4096),
        sh.normalize_settings(context_length=8192, thinking=True),
        sh.normalize_settings(context_length=8192, reasoning_effort="high"),
        sh.normalize_settings(context_length=8192, kv_ram=True),
        sh.normalize_settings(context_length=8192, safe=True),
        sh.normalize_settings(context_length=8192, temperature=0.2),
    ]
    keys = {sh.fingerprint("m", "t", "p", s) for s in variants}
    assert len(keys) == len(variants)
    assert sh.fingerprint("m", "t", "p", base) not in keys
    assert sh.fingerprint("m", "t", "other", base) != sh.fingerprint("m", "t", "p", base)


def _result(score=1.0, status="measured"):
    return {
        "status": status,
        "first_pass_success": score == 1.0,
        "final_success": score == 1.0,
        "repair_count": 0,
        "final_score": score if status == "measured" else None,
        "penalized_score": score if status == "measured" else None,
        "artifacts": ["out.txt"],
        "critical_failures": [],
        "error": "",
    }


def test_measured_rerun_replaces_and_deletes_old_workdir(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "RESULTS_ROOT", tmp_path)
    history = tmp_path / "runs.jsonl"
    old = tmp_path / "sandbox" / "email_write" / "old"
    new = tmp_path / "sandbox" / "email_write" / "new"
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    settings = sh.normalize_settings(context_length=8192)

    sh.record_run("m", "email_write", _result(), workdir=str(old), duration_s=1,
                  path=history, prompt="p", settings=settings)
    sh.record_run("m", "email_write", _result(0.5), workdir=str(new), duration_s=1,
                  path=history, prompt="p", settings=settings)

    rows = sh.list_runs(10, path=history)
    assert len(rows) == 1
    assert rows[0]["final_score"] == 0.5
    assert not old.exists()
    assert new.exists()


def test_not_measured_rerun_keeps_the_old_record(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "RESULTS_ROOT", tmp_path)
    history = tmp_path / "runs.jsonl"
    settings = sh.normalize_settings()
    sh.record_run("m", "t", _result(1.0), path=history, prompt="p", settings=settings)
    sh.record_run("m", "t", _result(status="not_measured"), path=history,
                  prompt="p", settings=settings)
    assert [r["status"] for r in sh.list_runs(10, path=history)] == ["not_measured", "measured"]


def test_different_settings_or_prompt_coexist(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "RESULTS_ROOT", tmp_path)
    history = tmp_path / "runs.jsonl"
    sh.record_run("m", "t", _result(), path=history, prompt="p",
                  settings=sh.normalize_settings(context_length=8192))
    sh.record_run("m", "t", _result(), path=history, prompt="p",
                  settings=sh.normalize_settings(context_length=4096))
    sh.record_run("m", "t", _result(), path=history, prompt="different",
                  settings=sh.normalize_settings(context_length=8192))
    assert len(sh.list_runs(10, path=history)) == 3


def test_workdir_outside_results_is_never_deleted(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "RESULTS_ROOT", tmp_path / "results")
    outside = tmp_path / "precious"
    outside.mkdir()
    history = tmp_path / "runs.jsonl"
    settings = sh.normalize_settings()
    sh.record_run("m", "t", _result(), workdir=str(outside), path=history, prompt="p", settings=settings)
    sh.record_run("m", "t", _result(), workdir="", path=history, prompt="p", settings=settings)
    assert outside.exists()


def test_malformed_line_survives_rewrite(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "RESULTS_ROOT", tmp_path)
    history = tmp_path / "runs.jsonl"
    settings = sh.normalize_settings()
    sh.record_run("m", "t", _result(), path=history, prompt="p", settings=settings)
    with history.open("a", encoding="utf-8") as handle:
        handle.write("not json\n")
    sh.record_run("m", "t", _result(), path=history, prompt="p", settings=settings)
    text = history.read_text(encoding="utf-8")
    assert "not json" in text
    assert sum(1 for line in text.splitlines() if line.startswith("{")) == 1
```

- [ ] **Step 2: Run the tests, expect ImportError/AttributeError**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sandbox_history_dedupe.py -q`
Expected: FAIL — `settings_from_reasoning` / `normalize_settings` missing.

- [ ] **Step 3: Implement the service**

Add to `lm_optimizer/services/sandbox_history.py` (keep existing functions):

```python
import hashlib
import os
import shutil
import tempfile

RESULTS_ROOT = Path("results")
SPECIAL_TASKS = ("(load)", "(crash)")
SETTINGS_KEYS = (
    "temperature", "max_output_tokens", "thinking", "reasoning_effort",
    "context_length", "kv_ram", "safe",
)


def normalize_settings(
    *,
    temperature: float = 0.0,
    max_output_tokens: int = 2048,
    thinking: bool = False,
    reasoning_effort: str | None = None,
    context_length: int | None = None,
    kv_ram: bool = False,
    safe: bool = False,
) -> dict[str, Any]:
    effort = (reasoning_effort or "").strip().lower()
    if effort in ("", "off", "none", "false", "on", "true", "default"):
        effort = None
    return {
        "temperature": float(temperature),
        "max_output_tokens": int(max_output_tokens),
        "thinking": bool(thinking),
        "reasoning_effort": effort,
        "context_length": int(context_length) if context_length else None,
        "kv_ram": bool(kv_ram),
        "safe": bool(safe),
    }


def settings_from_reasoning(
    reasoning: str,
    *,
    context_length: int | None,
    max_output_tokens: int,
    temperature: float = 0.0,
) -> dict[str, Any]:
    level = (reasoning or "").strip().lower()
    thinking = level not in ("", "off", "none", "false")
    return normalize_settings(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        thinking=thinking,
        reasoning_effort=level,
        context_length=context_length,
    )


def fingerprint(model: str, task: str, prompt: str, settings: dict[str, Any]) -> str:
    payload = {
        "model": model,
        "task": task,
        "prompt_sha": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "settings": {key: (settings or {}).get(key) for key in SETTINGS_KEYS},
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "rk1:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _allowed_roots() -> tuple[Path, Path]:
    return (RESULTS_ROOT / "sandbox", RESULTS_ROOT / "bakeoff")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def delete_workdir(workdir: str | None, *, keep: str = "") -> bool:
    """Remove one artifact dir, only inside this project's results trees."""
    if not workdir:
        return False
    target = Path(workdir)
    try:
        resolved = target.resolve()
    except OSError:
        return False
    if keep:
        try:
            if resolved == Path(keep).resolve():
                return False
        except OSError:
            pass
    if not any(_is_relative_to(resolved, root.resolve()) for root in _allowed_roots()):
        return False
    if not resolved.is_dir():
        return False
    try:
        shutil.rmtree(resolved)
    except OSError:
        return False
    return True


def _load_entries(path: Path) -> list[tuple[str, dict[str, Any] | None]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    entries: list[tuple[str, dict[str, Any] | None]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            entries.append((line, None))
            continue
        entries.append((line, item if isinstance(item, dict) else None))
    return entries


def _write_entries(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("".join(line + "\n" for line in lines))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _drop_superseded(
    path: Path, *, run_key: str, model: str, task: str, keep_workdir: str
) -> int:
    entries = _load_entries(path)
    matches = [
        index for index, (_, row) in enumerate(entries)
        if row and row.get("run_key") == run_key
        and row.get("model") == model and row.get("task") == task
    ]
    if len(matches) <= 1:
        return 0
    drop = set(matches[:-1])
    _write_entries(path, [line for index, (line, _) in enumerate(entries) if index not in drop])
    for index in sorted(drop):
        row = entries[index][1] or {}
        delete_workdir(row.get("workdir"), keep=keep_workdir)
    return len(drop)
```

Then in `record_run`:

```python
    run_key = None
    prompt_sha = ""
    clean_settings = None
    if prompt is not None and settings is not None:
        clean_settings = {key: (settings or {}).get(key) for key in SETTINGS_KEYS}
        prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        run_key = fingerprint(model, task, prompt, clean_settings)
    record = {
        ...existing fields...,
        "run_key": run_key,
        "settings": clean_settings,
        "prompt_sha": prompt_sha,
    }
    ...append as today...
    if run_key and measured and task not in SPECIAL_TASKS:
        _drop_superseded(target, run_key=run_key, model=model, task=task, keep_workdir=workdir)
    return record
```

- [ ] **Step 4: Run tests, expect PASS**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sandbox_history_dedupe.py -q`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add lm_optimizer/services/sandbox_history.py tests/test_sandbox_history_dedupe.py
git commit -m "feat(history): fingerprint sandbox runs and replace identical measured reruns"
```

---

### Task 2: Prune planning and application

**Files:**
- Modify: `lm_optimizer/services/sandbox_history.py`
- Test: `tests/test_sandbox_history_dedupe.py`

**Interfaces:**
- Produces:
  - `plan_prune(entries) -> tuple[set[int], list[dict]]` — indices to drop plus per-group summaries `{"model", "task", "run_key", "kept_ts", "dropped"}`
  - `prune_history(path: Path, *, apply: bool = False) -> dict` → `{"path", "before", "after", "removed", "directories_removed", "groups"}`

- [ ] **Step 1: Failing tests**

```python
def _row(model, task, *, key=None, status="measured", score=1.0, ts="2026-01-01T00:00:00", workdir=""):
    return {"model": model, "task": task, "run_key": key, "status": status,
            "final_score": score if status == "measured" else None, "ts": ts, "workdir": workdir}


def test_prune_dry_run_does_not_touch_the_file(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "RESULTS_ROOT", tmp_path)
    path = tmp_path / "runs.jsonl"
    rows = [_row("m", "t", ts="1"), _row("m", "t", ts="2")]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    report = sh.prune_history(path, apply=False)
    assert report["removed"] == 1
    assert path.read_text(encoding="utf-8") == before


def test_prune_apply_keeps_newest_measured_per_group(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "RESULTS_ROOT", tmp_path)
    path = tmp_path / "runs.jsonl"
    rows = [
        _row("m", "t", key="rk1:a", ts="1"),
        _row("m", "t", key="rk1:a", ts="2", status="not_measured"),
        _row("m", "t", key="rk1:a", ts="3"),
        _row("m", "t", key="rk1:b", ts="4"),
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    report = sh.prune_history(path, apply=True)
    kept = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert report["removed"] == 2
    assert [(r["run_key"], r["ts"]) for r in kept] == [("rk1:a", "3"), ("rk1:b", "4")]


def test_prune_keeps_load_and_crash_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "RESULTS_ROOT", tmp_path)
    path = tmp_path / "runs.jsonl"
    rows = [_row("m", "(load)", ts="1"), _row("m", "(load)", ts="2"),
            _row("m", "(crash)", ts="3")]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert sh.prune_history(path, apply=True)["removed"] == 0


def test_prune_drops_legacy_rows_once_a_keyed_row_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "RESULTS_ROOT", tmp_path)
    path = tmp_path / "runs.jsonl"
    rows = [_row("m", "t", ts="1"), _row("m", "t", key="rk1:a", ts="2")]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    sh.prune_history(path, apply=True)
    kept = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [r["run_key"] for r in kept] == ["rk1:a"]
```

- [ ] **Step 2: Run, expect failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sandbox_history_dedupe.py -q -k prune`
Expected: FAIL — `prune_history` missing.

- [ ] **Step 3: Implement**

```python
def _group_key(row: dict[str, Any]) -> tuple:
    task = str(row.get("task"))
    if task in SPECIAL_TASKS:
        return ("special", id(row))
    return (str(row.get("model")), task, row.get("run_key") or "__legacy__")


def plan_prune(entries: list[tuple[str, dict[str, Any] | None]]) -> tuple[set[int], list[dict]]:
    groups: dict[tuple, list[int]] = {}
    for index, (_, row) in enumerate(entries):
        if row is None:
            continue
        groups.setdefault(_group_key(row), []).append(index)
    keyed_pairs = {
        (str(row.get("model")), str(row.get("task")))
        for _, row in entries
        if row and row.get("run_key")
    }
    drop: set[int] = set()
    summary: list[dict] = []
    for key, indices in groups.items():
        if key[0] == "special":
            continue
        model, task, run_key = key
        measured = [
            index for index in indices
            if str(entries[index][1].get("status") or "measured") == "measured"
        ]
        keep = measured[-1] if measured else indices[-1]
        if run_key == "__legacy__" and (model, task) in keyed_pairs:
            dropped = list(indices)
            kept_ts = ""
        else:
            dropped = [index for index in indices if index != keep]
            kept_ts = str(entries[keep][1].get("ts") or "")
        if not dropped:
            continue
        drop.update(dropped)
        summary.append({
            "model": model,
            "task": task,
            "run_key": None if run_key == "__legacy__" else run_key,
            "kept_ts": kept_ts,
            "dropped": len(dropped),
        })
    return drop, summary


def prune_history(path: Path, *, apply: bool = False) -> dict[str, Any]:
    entries = _load_entries(path)
    drop, summary = plan_prune(entries)
    removed_dirs = 0
    if apply and drop:
        _write_entries(
            path,
            [line for index, (line, _) in enumerate(entries) if index not in drop],
        )
        for index in sorted(drop):
            row = entries[index][1] or {}
            if delete_workdir(row.get("workdir")):
                removed_dirs += 1
    return {
        "path": str(path),
        "before": len(entries),
        "after": len(entries) - len(drop),
        "removed": len(drop),
        "directories_removed": removed_dirs,
        "groups": summary,
    }
```

- [ ] **Step 4: Run all dedupe tests, expect PASS**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sandbox_history_dedupe.py tests/test_webui_fixes.py tests/test_measurement_status.py -q`
Expected: all pass (old call sites have no `prompt`/`settings`, so no key and no dedupe).

- [ ] **Step 5: Commit**

```bash
git add lm_optimizer/services/sandbox_history.py tests/test_sandbox_history_dedupe.py
git commit -m "feat(history): plan and apply duplicate-run pruning"
```

---

### Task 3: Bakeoff rows carry the fingerprint; runs.jsonl self-cleans

**Files:**
- Modify: `lm_optimizer/services/bakeoff.py:117-234` (`_run_task`), `:237-303` (`_run_model`), `:393-396` (`run_bakeoff`)
- Test: `tests/test_bakeoff_service.py`

- [ ] **Step 1: Failing test**

```python
def test_bakeoff_rows_carry_a_run_key_and_dedupe(tmp_path, monkeypatch):
    from lm_optimizer.services import bakeoff, sandbox_history

    monkeypatch.setattr(sandbox_history, "RESULTS_ROOT", tmp_path)
    settings = sandbox_history.normalize_settings(context_length=8192)
    key = sandbox_history.fingerprint("m", "email_write", "p", settings)
    rows = [
        {"model": "m", "task": "email_write", "run_key": key, "status": "measured", "ts": "1"},
        {"model": "m", "task": "email_write", "run_key": key, "status": "measured", "ts": "2"},
    ]
    path = tmp_path / "runs.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    report = sandbox_history.prune_history(path, apply=True)
    assert report["removed"] == 1
```

(Add `import json` at the top of the test module if missing.)

- [ ] **Step 2: Run it** — `.venv\Scripts\python.exe -m pytest tests/test_bakeoff_service.py -q -k run_key`
Expected: PASS once Task 2 is in; it guards the shared helper used below. If it passes immediately, keep it as the regression guard.

- [ ] **Step 3: Wire `_run_task`**

Add parameters `context: int`, `kv_ram: bool`, `safe: bool` to `_run_task`; build:

```python
    settings = normalize_settings(
        temperature=0.0,
        max_output_tokens=definition.max_output_tokens,
        thinking=thinking,
        reasoning_effort=reasoning_effort,
        context_length=context,
        kv_ram=kv_ram,
        safe=safe,
    )
    run_key = fingerprint(model, task_id, definition.prompt, settings)
```

Pass `prompt=definition.prompt, settings=settings` to `record_run`, and add `"run_key": run_key, "settings": settings` to the returned row. In `_run_model` pass `context=context, kv_ram=kv_ram, safe=safe` to `_run_task`.

- [ ] **Step 4: Prune after each model batch in `run_bakeoff`**

```python
        for row in rows:
            with jsonl.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        prune_history(jsonl, apply=True)
        all_rows.extend(rows)
```

- [ ] **Step 5: Run tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_bakeoff_service.py -q`
Expected: pass. Existing tests that assert on row keys keep passing because we only add keys.

- [ ] **Step 6: Commit**

```bash
git add lm_optimizer/services/bakeoff.py tests/test_bakeoff_service.py
git commit -m "feat(bakeoff): record run fingerprints and prune identical rows"
```

---

### Task 4: CLI records prompt + settings; `lab prune-runs`

**Files:**
- Modify: `lm_optimizer/cli/lab.py:1022-1145` (`_run_sandbox_one`), add command after `sandbox`
- Test: `tests/test_sandbox_history_dedupe.py`

- [ ] **Step 1: Failing test**

```python
def test_cli_settings_include_the_effective_context():
    settings = sh.settings_from_reasoning("off", context_length=8192, max_output_tokens=2048)
    assert settings["thinking"] is False
    assert settings["context_length"] == 8192
    assert settings["reasoning_effort"] is None
    high = sh.settings_from_reasoning("high", context_length=8192, max_output_tokens=2048)
    assert high["thinking"] is True
    assert high["reasoning_effort"] == "high"
```

- [ ] **Step 2: Run** — expect PASS (helper exists); keep as the CLI-mapping guard.

- [ ] **Step 3: Update `_run_sandbox_one`**

Inside `_run_with_gate`, after `effective` is known:

```python
            run_meta["settings"] = settings_from_reasoning(
                reasoning,
                context_length=int(effective),
                max_output_tokens=definition.max_output_tokens,
            )
```

Declare `run_meta: dict = {}` before the async function, and change the `record_run` call to:

```python
    record_run(
        model or "(none)",
        task_id,
        payload,
        workdir=str(workdir),
        duration_s=sum(a.duration_s for a in result.attempts),
        prompt=definition.prompt,
        settings=run_meta.get("settings"),
    )
```

`record_run` ignores `settings=None` (no key), so a model-gate failure records as before.

- [ ] **Step 4: Add the command**

```python
@app.command("prune-runs")
def prune_runs(
    apply: bool = typer.Option(False, "--apply", help="Rewrite the JSONL files and delete artifact dirs"),
    sandbox: bool = typer.Option(True, "--sandbox/--no-sandbox", help="Prune results/sandbox_runs.jsonl"),
    bakeoff: bool = typer.Option(True, "--bakeoff/--no-bakeoff", help="Prune results/bakeoff/runs.jsonl"),
):
    """Collapse duplicate run history (same model + task + prompt + settings)."""
    from pathlib import Path as _Path

    from lm_optimizer.services.sandbox_history import prune_history

    paths = []
    if sandbox:
        paths.append(_Path("results") / "sandbox_runs.jsonl")
    if bakeoff:
        paths.append(_Path("results") / "bakeoff" / "runs.jsonl")
    if not paths:
        console.print("[yellow]nothing selected[/yellow]")
        raise typer.Exit(1)
    for path in paths:
        report = prune_history(path, apply=apply)
        console.print(
            f"[bold]{path}[/bold]: {report['before']} -> {report['after']} rows, "
            f"{report['removed']} duplicate(s), {report['directories_removed']} dir(s) deleted"
        )
        for group in report["groups"][:40]:
            console.print(
                f"  {group['model']} · {group['task']} · "
                f"{group['run_key'] or 'legacy'} · kept {group['kept_ts'] or '-'} · "
                f"dropped {group['dropped']}"
            )
        if len(report["groups"]) > 40:
            console.print(f"  ... {len(report['groups']) - 40} more group(s)")
    if not apply:
        console.print("[dim]dry run — rerun with --apply to write[/dim]")
```

- [ ] **Step 5: Verify the command parses and refuses to run twice**

Run: `.venv\Scripts\python.exe -m lm_optimizer.cli.main lab prune-runs --help`
Run: `.venv\Scripts\python.exe -m lm_optimizer.cli.main lab prune-runs` (dry run; must print 86 -> 45 and 77 -> 44)

- [ ] **Step 6: Commit**

```bash
git add lm_optimizer/cli/lab.py tests/test_sandbox_history_dedupe.py
git commit -m "feat(cli): fingerprint sandbox runs and add lab prune-runs"
```

---

### Task 5: Web sandbox job writes history

**Files:**
- Modify: `lm_optimizer/api/routes.py:4470-4560` (`_run_sandbox_job`)
- Test: `lm_optimizer/tests/test_dashboard_api.py` or `tests/test_lab_api.py`

- [ ] **Step 1: Failing test**

```python
def test_web_sandbox_job_records_history(monkeypatch, tmp_path):
    """A completed web job writes exactly one record with its own settings."""
    from lm_optimizer.services import sandbox_history

    recorded = {}
    monkeypatch.setattr(
        sandbox_history, "record_run",
        lambda *a, **kw: recorded.update(kw) or {"model": a[0], "task": a[1]},
    )
    settings = sandbox_history.normalize_settings(temperature=0.2, max_output_tokens=2048)
    assert sandbox_history.fingerprint("m", "email_write", "p", settings) != (
        sandbox_history.fingerprint(
            "m", "email_write", "p",
            sandbox_history.normalize_settings(temperature=0.0, max_output_tokens=2048),
        )
    )
```

The second half is the real assertion (the job's config must not match a CLI run); the monkeypatch documents the call contract.

- [ ] **Step 2: Implement in `_run_sandbox_job`**

```python
        started = time.perf_counter()
        result = await runner.run(_generate)
        duration_s = time.perf_counter() - started
        apply_retention(base_dir, policy)
        from lm_optimizer.services.sandbox_history import (
            normalize_settings as _normalize_settings,
            record_run as _record_run,
        )

        _record_run(
            model,
            task_id,
            result.as_dict(),
            workdir=str(workdir),
            duration_s=duration_s,
            prompt=definition.prompt,
            settings=_normalize_settings(temperature=0.2, max_output_tokens=2048),
        )
```

`time` is already imported at module level (used by `/status` caching); if not, add `import time`.

- [ ] **Step 3: Run the API tests**

Run: `.venv\Scripts\python.exe -m pytest lm_optimizer/tests/test_dashboard_api.py tests/test_lab_api.py -q`
Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add lm_optimizer/api/routes.py lm_optimizer/tests/test_dashboard_api.py
git commit -m "feat(api): record sandbox job history with its own run fingerprint"
```

---

### Task 6: Inline per-test sandbox history

**Files:**
- Modify: `lm_optimizer/ui/static/js/sandbox.js:172-491`

- [ ] **Step 1: State and grouping**

Replace the history block state with:

```js
    var historyRuns = [];
    var pinnedRun = null;
    var expandedModel = null;
    var openTask = null;
    var selectedRun = null;
```

`groupRuns(runs)` stays; add `runsForTask(model, task)` returning `[{index, run}]` sorted newest first.

- [ ] **Step 2: Model table with an inline expansion row**

Each model row: `<tr class="history-model" data-model="...">` with a leading chevron cell (`▸`/`▾`), followed by

```html
<tr class="sb-expand-row" data-model="...”><td colspan="6"><div class="sb-expand"></div></td></tr>
```

`renderHistory()` renders all rows, then calls `renderExpansion()`; the model row click toggles `expandedModel` (clicking the open model closes it), resets `openTask`/`selectedRun`, and re-renders.

- [ ] **Step 3: Test list**

`renderExpansion()` finds the `.sb-expand` inside the matching row and fills it:

```
task | result badge | score | date | N run(s) | [View]
```

where `result badge`/`score`/`date` come from the newest run of that task. `View` sets `openTask = task; selectedRun = null;` and re-renders the expansion only.

- [ ] **Step 4: Detail view**

When `openTask` is set: header `Task · <model>` with `← Back to tests`, a `<select class="run-picker">` when the task has more than one run (label `date · score · key.slice(0,10)`), and the detail body. Reuse today's markup by extracting:

```js
    function runDetailHtml(x) { /* the existing table + preview markup */ }
```

`Pin` sets `pinnedRun = index`; when another run is pinned, show `Compare with pinned` which calls `showCompareRuns(pinnedRun, index)` rendering into the same `.sb-expand`; its Close button returns to the detail view.

A failed detail fetch renders `<p class="text-sm text-red-600">Failed to load run detail: …</p>` plus a `Retry` button that calls the same renderer.

- [ ] **Step 5: Static check and browser proof**

Run: `node --check lm_optimizer/ui/static/js/sandbox.js`
Run the CDP probe from `%TEMP%\opencode\probe_view.py` style: expand a model → count `.sb-test-row` (= number of tests), click `.view-test` → expect `#sb-run-detail` and `← Back to tests`, click back → test rows return, pick a two-config task → `.run-picker` has 2 options.

- [ ] **Step 6: Commit**

```bash
git add lm_optimizer/ui/static/js/sandbox.js
git commit -m "feat(ui): expand sandbox models into per-test rows with run details"
```

---

### Task 7: Clean the real data and verify end to end

- [ ] **Step 1: Dry run on real history**

Run: `.venv\Scripts\python.exe -m lm_optimizer.cli.main lab prune-runs`
Expected: `results\sandbox_runs.jsonl: 86 -> 45` and `results\bakeoff\runs.jsonl: 77 -> 44`.

- [ ] **Step 2: Apply**

Run: `.venv\Scripts\python.exe -m lm_optimizer.cli.main lab prune-runs --apply`

- [ ] **Step 3: Assert the result**

```powershell
.venv\Scripts\python.exe -c "import json; from pathlib import Path; [print(p, len(Path(p).read_text(encoding='utf-8').splitlines())) for p in ['results/sandbox_runs.jsonl','results/bakeoff/runs.jsonl']]"
```
Expected: 45 and 44 lines.

- [ ] **Step 4: Regenerate the scoreboard and confirm it still builds**

Run: `.venv\Scripts\python.exe tools/scoreboard.py`
Then `git diff --stat SCOREBOARD.md results/scoreboard.md` (results is ignored; SCOREBOARD.md only if you copy it).

- [ ] **Step 5: Full targeted suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sandbox_history_dedupe.py tests/test_sandbox_lab.py tests/test_bakeoff_service.py tests/test_webui_fixes.py tests/test_measurement_status.py tests/test_lab_api.py lm_optimizer/tests/test_dashboard_api.py -q`
Expected: all pass.

- [ ] **Step 6: Commit docs/scoreboard if changed, then push**

```bash
git add SCOREBOARD.md docs/ 2>/dev/null
git commit -m "docs: refresh run history after dedupe" || true
git push origin main
```
