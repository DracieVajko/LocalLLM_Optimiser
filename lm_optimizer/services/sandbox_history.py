"""JSONL history of single-model sandbox runs.

The CLI writes one record per `lab sandbox` execution. The web UI reads the
same file, so single-model sandbox results are visible without a separate
database table. The file lives under the gitignored ``results/`` directory.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_HISTORY = Path("results") / "sandbox_runs.jsonl"


def _history_path(path: Path | None) -> Path:
    return path or DEFAULT_HISTORY


def record_run(
    model: str,
    task: str,
    result: dict[str, Any],
    *,
    workdir: str = "",
    duration_s: float = 0.0,
    path: Path | None = None,
) -> dict[str, Any]:
    """Append one sandbox run record; returns the stored record."""
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "task": task,
        "first_pass_success": bool(result.get("first_pass_success")),
        "final_success": bool(result.get("final_success")),
        "repair_count": result.get("repair_count", 0),
        "final_score": result.get("final_score"),
        "penalized_score": result.get("penalized_score"),
        "artifacts": list(result.get("artifacts") or []),
        "critical_failures": list(result.get("critical_failures") or []),
        "error": str(result.get("error") or "")[:300],
        "workdir": workdir,
        "duration_s": round(float(duration_s), 1),
        "blend_file": str(result.get("blend_file") or ""),
    }
    target = _history_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def list_runs(limit: int = 100, *, path: Path | None = None) -> list[dict[str, Any]]:
    """Return the newest records first; malformed lines are skipped."""
    target = _history_path(path)
    if not target.exists():
        return []
    records: list[dict[str, Any]] = []
    try:
        with target.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    records.append(item)
    except OSError:
        return []
    return records[-limit:][::-1]


def clear_failed_sandbox_runs() -> dict[str, int]:
    """Delete all failed single-model sandbox runs.

    Removes both the JSONL history records with final_success=False and the
    corresponding directories under results/sandbox/.

    Returns a dict with counts of deleted records and directories.
    """
    import shutil

    target = _history_path()
    if not target.exists():
        return {"records_deleted": 0, "directories_deleted": 0}

    kept: list[str] = []
    deleted_records = 0
    deleted_dirs = 0

    with target.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                kept.append(line)
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                kept.append(line)
                continue
            if isinstance(item, dict) and item.get("final_success") is False:
                deleted_records += 1
                workdir = item.get("workdir") or ""
                if workdir:
                    wd_path = Path(workdir)
                    # Safety: only delete inside results/sandbox/
                    try:
                        wd_resolved = wd_path.resolve()
                        sandbox_root = Path("results/sandbox").resolve()
                        wd_resolved.relative_to(sandbox_root)
                        if wd_resolved.exists() and wd_resolved.is_dir():
                            shutil.rmtree(wd_resolved)
                            deleted_dirs += 1
                    except (ValueError, OSError):
                        pass  # skip unsafe or missing paths
            else:
                kept.append(line)

    # Rewrite the JSONL file without failed records.
    target.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")

    return {"records_deleted": deleted_records, "directories_deleted": deleted_dirs}
