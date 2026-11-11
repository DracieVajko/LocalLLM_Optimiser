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
) -> dict[str, Any]:
    """Normalize the settings that make two runs the same test or not."""
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
    """Map the CLI's ``--reasoning`` value onto normalized settings."""
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
    """Stable id for one identical test (model + task + prompt + settings)."""
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
    """Line/parsed pairs; malformed lines are kept with ``None``."""
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
    """Atomically replace the JSONL file (a crash cannot truncate history)."""
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
) -> dict[str, Any]:
    """Append one sandbox run record; returns the stored record.

    ``prompt`` and ``settings`` identify the test. When both are given a
    measured run replaces every older record with the same fingerprint.
    """
    status = str(result.get("status") or "measured")
    measured = status == "measured"
    run_key = None
    prompt_sha = ""
    clean_settings = None
    if prompt is not None and settings is not None:
        clean_settings = {key: (settings or {}).get(key) for key in SETTINGS_KEYS}
        prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        run_key = fingerprint(model, task, prompt, clean_settings)
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "task": task,
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
        _drop_superseded(
            target, run_key=run_key, model=model, task=task, keep_workdir=workdir
        )
    return record


def _group_key(row: dict[str, Any]) -> tuple:
    task = str(row.get("task"))
    if task in SPECIAL_TASKS:
        return ("special", id(row))
    return (str(row.get("model")), task, row.get("run_key") or "__legacy__")


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
        if key[0] == "special":
            continue
        model, task, run_key = key
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
    removed_dirs = 0
    if apply and drop:
        _write_entries(
            path, [line for index, (line, _) in enumerate(entries) if index not in drop]
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


def list_runs(limit: int = 100, *, path: Path | None = None) -> list[dict[str, Any]]:
    """Return the newest records first; malformed lines are skipped."""
    target = _history_path(path)
    records = [row for _, row in _load_entries(target) if row is not None]
    return records[-limit:][::-1]


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
