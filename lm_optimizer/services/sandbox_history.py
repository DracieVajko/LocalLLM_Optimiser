"""JSONL history of single-model sandbox runs.

The CLI writes one record per `lab sandbox` execution. The web UI reads the
same file, so single-model sandbox results are visible without a separate
database table. The file lives under the gitignored ``results/`` directory.

Each record carries a ``run_key``: a fingerprint of the model, task, prompt
and normalized model settings. A measured rerun of the *same* test replaces
the older record (and its artifact dir); a different prompt or different
settings is a different test and both records stay.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_HISTORY = Path("results") / "sandbox_runs.jsonl"

#: Root that workdirs must live under before they may be deleted.
RESULTS_ROOT = Path("results")

#: Rows with these task ids are failure evidence, never deduped or pruned.
SPECIAL_TASKS = ("(load)", "(crash)")

SETTINGS_KEYS = (
    "temperature",
    "max_output_tokens",
    "thinking",
    "reasoning_effort",
    "context_length",
    "kv_ram",
    "safe",
    "kv_quant",
    "threads",
)


def _history_path(path: Path | None) -> Path:
    return path or DEFAULT_HISTORY


def normalize_settings(
    *,
    temperature: float = 0.0,
    max_output_tokens: int = 2048,
    thinking: bool = False,
    reasoning_effort: str | None = None,
    context_length: int | None = None,
    kv_ram: bool = False,
    safe: bool = False,
    kv_quant: str | None = None,
    threads: str | int | None = None,
) -> dict[str, Any]:
    """Normalize the settings that make two runs the same test or not.

    ``kv_quant`` and ``threads`` are load-time settings LM Studio refuses over
    REST (400 unrecognized_keys); they are declared by the caller and recorded
    so a q4/q5/q8 comparison stays distinguishable.
    """
    effort = (reasoning_effort or "").strip().lower()
    if effort in ("", "off", "none", "false", "on", "true", "default"):
        effort = None
    quant = (kv_quant or "").strip().lower()
    if quant in ("", "none", "f16", "fp16"):
        quant = None
    threads_value: str | None = None
    if threads not in (None, ""):
        threads_value = str(threads).strip().lower()
    return {
        "temperature": float(temperature),
        "max_output_tokens": int(max_output_tokens),
        "thinking": bool(thinking),
        "reasoning_effort": effort,
        "context_length": int(context_length) if context_length else None,
        "kv_ram": bool(kv_ram),
        "safe": bool(safe),
        "kv_quant": quant,
        "threads": threads_value,
    }


def settings_from_reasoning(
    reasoning: str,
    *,
    context_length: int | None,
    max_output_tokens: int,
    temperature: float = 0.0,
    kv_quant: str | None = None,
    threads: str | int | None = None,
) -> dict[str, Any]:
    """Map the CLI's ``--reasoning`` value onto normalized settings."""
    level = (reasoning or "").strip().lower()
    thinking = level not in ("", "off", "none", "false")
    return normalize_settings(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        thinking=thinking,
        reasoning_effort=level,
        context_length=context_length,
        kv_quant=kv_quant,
        threads=threads,
    )


def fingerprint(
    model: str,
    task: str,
    prompt: str,
    settings: dict[str, Any],
    origin: str = "local",
) -> str:
    """Stable id for one identical test (model + task + prompt + settings)."""
    payload = {
        "model": model,
        "task": task,
        "origin": "frontier" if str(origin).lower() == "frontier" else "local",
        "prompt_sha": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "settings": {key: (settings or {}).get(key) for key in SETTINGS_KEYS},
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "rk1:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _allowed_roots() -> tuple[Path, Path]:
    return (RESULTS_ROOT / "sandbox", RESULTS_ROOT / "bakeoff")


def delete_workdir(workdir: str | None, *, keep: str = "") -> bool:
    """Remove one artifact dir, only strictly inside this project's results trees."""
    if not workdir:
        return False
    try:
        resolved = Path(workdir).resolve()
    except OSError:
        return False
    if keep:
        try:
            if resolved == Path(keep).resolve():
                return False
        except OSError:
            pass
    inside = False
    for root in _allowed_roots():
        try:
            resolved_root = root.resolve()
        except OSError:
            continue
        # The root itself and anything above it must never be deletable.
        if resolved == resolved_root:
            return False
        try:
            parts = resolved.relative_to(resolved_root).parts
        except ValueError:
            continue
        if parts:
            inside = True
            break
    if not inside:
        return False
    if not resolved.is_dir():
        return False
    try:
        shutil.rmtree(resolved)
    except OSError:
        return False
    return True


def _load_entries(path: Path) -> list[tuple[str, dict[str, Any] | None]]:
    """Line/parsed pairs; malformed and blank lines are kept with ``None``."""
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    entries: list[tuple[str, dict[str, Any] | None]] = []
    for line in lines:
        if not line.strip():
            entries.append(("", None))
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            entries.append((line, None))
            continue
        entries.append((line, item if isinstance(item, dict) else None))
    return entries


def _count_rows(entries: list[tuple[str, dict[str, Any] | None]]) -> int:
    return sum(1 for _, row in entries if row is not None)


def _write_entries(path: Path, lines: list[str]) -> None:
    """Atomically replace the JSONL file (a crash cannot truncate history).

    On Windows the replace fails while another process holds the file open;
    the history is polled by the web UI, so retry briefly instead of failing
    the run that just succeeded.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("".join(line + "\n" for line in lines))
        last: OSError | None = None
        for attempt in range(5):
            try:
                os.replace(tmp, path)
                return
            except PermissionError as exc:  # another handle has the file open
                last = exc
                time.sleep(0.05 * (attempt + 1))
        raise last or OSError("replace failed")
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _drop_superseded(
    path: Path, *, run_key: str, model: str, task: str, keep_workdir: str
) -> int:
    """Keep only the newest record of this exact test; return how many went."""
    entries = _load_entries(path)
    matches = [
        index
        for index, (_, row) in enumerate(entries)
        if row
        and row.get("run_key") == run_key
        and row.get("model") == model
        and row.get("task") == task
    ]
    if len(matches) <= 1:
        return 0
    drop = set(matches[:-1])
    _write_entries(
        path, [line for index, (line, _) in enumerate(entries) if index not in drop]
    )
    for index in sorted(drop):
        row = entries[index][1] or {}
        delete_workdir(row.get("workdir"), keep=keep_workdir)
    return len(drop)


def record_run(
    model: str,
    task: str,
    result: dict[str, Any],
    *,
    workdir: str = "",
    duration_s: float = 0.0,
    path: Path | None = None,
    prompt: str | None = None,
    settings: dict[str, Any] | None = None,
    origin: str = "local",
) -> dict[str, Any]:
    """Append one sandbox run record; returns the stored record.

    ``prompt`` and ``settings`` identify the test. When both are given a
    measured run replaces every older record with the same fingerprint.
    ``origin`` is ``local`` (this hardware) or ``frontier`` (an API provider).
    """
    status = str(result.get("status") or "measured")
    measured = status == "measured"
    clean_origin = "frontier" if str(origin).lower() == "frontier" else "local"
    run_key = None
    prompt_sha = ""
    clean_settings = None
    if prompt is not None and settings is not None:
        clean_settings = {key: (settings or {}).get(key) for key in SETTINGS_KEYS}
        prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        run_key = fingerprint(model, task, prompt, clean_settings, clean_origin)
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "task": task,
        "origin": clean_origin,
        "status": status,
        "first_pass_success": bool(result.get("first_pass_success")),
        "final_success": bool(result.get("final_success")),
        "repair_count": result.get("repair_count", 0),
        "final_score": result.get("final_score") if measured else None,
        "penalized_score": result.get("penalized_score") if measured else None,
        "artifacts": list(result.get("artifacts") or []),
        "critical_failures": list(result.get("critical_failures") or []),
        "error": str(result.get("error") or "")[:300],
        "workdir": workdir,
        "duration_s": round(float(duration_s), 1),
        "blend_file": str(result.get("blend_file") or ""),
        "run_key": run_key,
        "settings": clean_settings,
        "prompt_sha": prompt_sha,
    }
    target = _history_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    if run_key and measured and task not in SPECIAL_TASKS:
        try:
            record["superseded"] = _drop_superseded(
                target, run_key=run_key, model=model, task=task, keep_workdir=workdir
            )
        except OSError:
            # History maintenance must never fail a run that succeeded.
            record["superseded"] = 0
    return record


def _group_key(row: dict[str, Any]) -> tuple:
    task = str(row.get("task"))
    if task in SPECIAL_TASKS:
        return (1, id(row))
    return (0, str(row.get("model")), task, row.get("run_key") or "__legacy__")


def plan_prune(
    entries: list[tuple[str, dict[str, Any] | None]],
) -> tuple[set[int], list[dict[str, Any]]]:
    """Decide which entry indices to drop; returns (indices, per-group summary)."""
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
    summary: list[dict[str, Any]] = []
    for key, indices in groups.items():
        if key[0] == 1:
            continue
        _, model, task, run_key = key
        measured = [
            index
            for index in indices
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
        summary.append(
            {
                "model": model,
                "task": task,
                "run_key": None if run_key == "__legacy__" else run_key,
                "kept_ts": kept_ts,
                "dropped": len(dropped),
            }
        )
    return drop, summary


def prune_history(path: Path, *, apply: bool = False) -> dict[str, Any]:
    """Collapse duplicate runs; dry run unless ``apply`` is true."""
    entries = _load_entries(path)
    drop, summary = plan_prune(entries)
    directories = [
        str((entries[index][1] or {}).get("workdir") or "")
        for index in sorted(drop)
        if (entries[index][1] or {}).get("workdir")
    ]
    removed_dirs = 0
    if apply and drop:
        _write_entries(
            path, [line for index, (line, _) in enumerate(entries) if index not in drop]
        )
        for index in sorted(drop):
            row = entries[index][1] or {}
            if delete_workdir(row.get("workdir")):
                removed_dirs += 1
    before = _count_rows(entries)
    return {
        "path": str(path),
        "before": before,
        "after": before - len(drop),
        "removed": len(drop),
        "directories": directories,
        "directories_removed": removed_dirs,
        "groups": summary,
    }


def dedupe_written_rows(
    path: Path, rows: list[dict[str, Any]]
) -> int:
    """On-write rule for a JSONL a caller appended to: only a measured row
    replaces rows with its own run_key. Never collapses legacy or unmeasured
    rows — that is `prune_history`'s explicit migration."""
    removed = 0
    for row in rows:
        run_key = row.get("run_key")
        if (
            not run_key
            or str(row.get("status") or "measured") != "measured"
            or str(row.get("task")) in SPECIAL_TASKS
        ):
            continue
        removed += _drop_superseded(
            path,
            run_key=str(run_key),
            model=str(row.get("model")),
            task=str(row.get("task")),
            keep_workdir=str(row.get("workdir") or ""),
        )
    return removed


def origin_of(row: dict[str, Any]) -> str:
    """Where a run executed: ``local`` hardware or a ``frontier`` API provider.

    Records written before the field existed are local, because every writer of
    that era ran against LM Studio on this machine.
    """
    return "frontier" if str(row.get("origin") or "").lower() == "frontier" else "local"


def mark_origin(
    path: Path, *, model_match: str, origin: str, apply: bool = False
) -> dict[str, Any]:
    """Re-label existing rows as local/frontier (backfill for legacy records)."""
    wanted = "frontier" if str(origin).lower() == "frontier" else "local"
    entries = _load_entries(path)
    needle = (model_match or "").strip().lower()
    matched = [
        index
        for index, (_, row) in enumerate(entries)
        if row and needle and needle in str(row.get("model") or "").lower()
    ]
    models = sorted({str(entries[i][1].get("model")) for i in matched})
    changed = [
        index
        for index in matched
        if origin_of(entries[index][1]) != wanted
    ]
    if apply and changed:
        drop = set(changed)
        lines = []
        for index, (line, row) in enumerate(entries):
            if index in drop and row is not None:
                row = dict(row, origin=wanted)
                line = json.dumps(row, ensure_ascii=False)
            lines.append(line)
        _write_entries(path, lines)
    return {
        "path": str(path),
        "origin": wanted,
        "models": models,
        "matched": len(matched),
        "changed": len(changed),
        "applied": bool(apply and changed),
    }


def run_id(row: dict[str, Any]) -> str:
    """Stable address for one history row (indexes shift after a prune)."""
    blob = "|".join(
        str(row.get(key) or "")
        for key in ("model", "task", "ts", "run_key", "final_score", "status")
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def list_runs(limit: int = 100, *, path: Path | None = None) -> list[dict[str, Any]]:
    """Return the newest records first; each row carries a stable ``run_id``."""
    target = _history_path(path)
    records = [row for _, row in _load_entries(target) if row is not None]
    newest = records[-limit:][::-1]
    for row in newest:
        row.setdefault("run_id", run_id(row))
    return newest


def find_run(identifier: str, *, path: Path | None = None) -> dict[str, Any] | None:
    """Find one record by its stable ``run_id`` (falls back to a numeric index)."""
    runs = list_runs(1000, path=path)
    for row in runs:
        if row.get("run_id") == identifier:
            return row
    if identifier.isdigit():
        index = int(identifier)
        if 0 <= index < len(runs):
            return runs[index]
    return None


def clear_failed_sandbox_runs() -> dict[str, int]:
    """Delete all failed single-model sandbox runs.

    Removes both the JSONL history records with final_success=False and the
    corresponding directories under results/sandbox/.

    Returns a dict with counts of deleted records and directories.
    """
    target = _history_path()
    if not target.exists():
        return {"records_deleted": 0, "directories_deleted": 0}

    kept: list[str] = []
    deleted_records = 0
    deleted_dirs = 0

    for line, item in _load_entries(target):
        if item is None:
            kept.append(line)
            continue
        if item.get("final_success") is False:
            deleted_records += 1
            if delete_workdir(item.get("workdir")):
                deleted_dirs += 1
        else:
            kept.append(line)

    # Rewrite the JSONL file without failed records.
    target.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")

    return {"records_deleted": deleted_records, "directories_deleted": deleted_dirs}
