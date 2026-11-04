"""Reconstruct sandbox run history from the all-models sweep log.

The sweep ran `lab sandbox` for 90 model x task pairs. The CLI overwrote
`results/sandbox-<task>.json` on every run, so per-model results were lost;
the workdirs under `results/sandbox/<task>/<timestamp>/` still contain the
model output. This script:

1. parses the sweep log for (timestamp, model, task) run starts,
2. maps each run to the nearest workdir (same task, within 15 minutes),
3. re-scores the files with the task's own checks,
4. appends one record per run to `results/sandbox_runs.jsonl`.

Idempotent: records already present (same model/task/ts) are skipped.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lm_optimizer.services.sandbox_lab import SANDBOX_TASKS, score_attempt  # noqa: E402
from lm_optimizer.services.sandbox_runner import read_workdir_files  # noqa: E402

LOG = Path("logs/sandbox_all_models.log")
OUT = Path("results/sandbox_runs.jsonl")
RUN_RE = re.compile(r"^\[(?P<ts>[^\]]+)\] --- \[\d+/\d+\] (?P<model>.+) x (?P<task>\S+) ---$")


def parse_runs() -> list[dict]:
    if not LOG.exists():
        raise SystemExit(f"missing log: {LOG}")
    runs: list[dict] = []
    for line in LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        match = RUN_RE.match(line)
        if not match:
            continue
        try:
            started = datetime.fromisoformat(match.group("ts"))
        except ValueError:
            continue
        runs.append(
            {
                "started": started,
                "model": match.group("model").strip(),
                "task": match.group("task").strip(),
            }
        )
    return runs


def workdir_index() -> dict[str, list[tuple[datetime, Path]]]:
    index: dict[str, list[tuple[datetime, Path]]] = {}
    base = Path("results") / "sandbox"
    for task_dir in base.iterdir() if base.exists() else []:
        if not task_dir.is_dir():
            continue
        items: list[tuple[datetime, Path]] = []
        for child in task_dir.iterdir():
            if not child.is_dir():
                continue
            try:
                stamp = datetime.strptime(child.name, "%Y%m%d_%H%M%S")
            except ValueError:
                continue
            items.append((stamp, child))
        index[task_dir.name] = items
    return index


def score_workdir(task_id: str, workdir: Path) -> tuple[float, bool, list[str], list[str]]:
    task = SANDBOX_TASKS[task_id]
    files = read_workdir_files(workdir)
    custom = {}
    if task.kind.value == "web":
        try:
            from lm_optimizer.services.web_validator import validate_web_files

            for check in validate_web_files(files):
                custom[check.name] = (check.passed, check.detail)
        except Exception:
            custom = {}
    score, failing, critical = score_attempt(
        task, files, custom_results=custom or None
    )
    passed = not failing and not critical
    return score, passed, failing, critical


def main() -> int:
    runs = parse_runs()
    index = workdir_index()
    used: set[Path] = set()
    records: list[dict] = []
    for run in runs:
        task = run["task"]
        best: tuple[float, Path] | None = None
        for stamp, path in index.get(task, []):
            if path in used:
                continue
            delta = abs((stamp - run["started"]).total_seconds())
            if delta > 900:
                continue
            if best is None or delta < best[0]:
                best = (delta, path)
        if best is None:
            records.append(
                {
                    "ts": run["started"].isoformat(timespec="seconds"),
                    "model": run["model"],
                    "task": task,
                    "first_pass_success": False,
                    "final_success": False,
                    "repair_count": 0,
                    "final_score": 0.0,
                    "penalized_score": 0.0,
                    "artifacts": [],
                    "critical_failures": [],
                    "error": "no workdir (timeout or load failure)",
                    "workdir": "",
                    "duration_s": 0.0,
                    "backfilled": True,
                }
            )
            continue
        used.add(best[1])
        score, passed, failing, critical = score_workdir(task, best[1])
        records.append(
            {
                "ts": run["started"].isoformat(timespec="seconds"),
                "model": run["model"],
                "task": task,
                "first_pass_success": passed,
                "final_success": passed,
                "repair_count": 0,
                "final_score": round(score, 4),
                "penalized_score": round(score, 4),
                "artifacts": sorted(read_workdir_files(best[1]).keys()),
                "critical_failures": critical,
                "error": "; ".join(failing)[:300],
                "workdir": str(best[1]),
                "duration_s": 0.0,
                "backfilled": True,
            }
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    existing: set[tuple[str, str, str]] = set()
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            existing.add((item.get("model", ""), item.get("task", ""), item.get("ts", "")))
    added = 0
    with OUT.open("a", encoding="utf-8") as handle:
        for record in records:
            key = (record["model"], record["task"], record["ts"])
            if key in existing:
                continue
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            added += 1
    passed = sum(1 for r in records if r["final_success"])
    print(f"parsed={len(runs)} scored={len(records)} pass={passed} added={added}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
