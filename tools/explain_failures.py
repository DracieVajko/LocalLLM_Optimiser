"""Re-score stored artifacts and explain why each one failed.

Uses the *current* sandbox definitions, not the score that was recorded at
generation time, so a scoring fix is visible immediately.

Usage:
    python tools/explain_failures.py                  # newest artifact per model/task
    python tools/explain_failures.py --task email_write
    python tools/explain_failures.py --json out.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from lm_optimizer.services.sandbox_lab import SANDBOX_TASKS, SandboxPolicy  # noqa: E402
from lm_optimizer.services.sandbox_runner import (  # noqa: E402
    SandboxRunner,
    build_command_for,
)

from compare_models import discover_bakeoff  # noqa: E402

BAKEOFF = ROOT / "results" / "bakeoff"
OUT = ROOT / "results" / "explain"


def rescore(model: str, task: str, artifact: Path, index: int, stamp: str) -> dict:
    definition = replace(SANDBOX_TASKS[task], max_repair_attempts=0)
    workdir = OUT / "runs" / f"{index:03d}_{model[:40]}" / task / stamp
    workdir.mkdir(parents=True, exist_ok=True)
    policy = SandboxPolicy(
        workdir=workdir,
        network_enabled=False,
        timeout_s=definition.timeout_s,
        allowed_executables=definition.allowed_executables,
    )
    runner = SandboxRunner(
        task=definition,
        policy=policy,
        workdir=workdir,
        command=build_command_for(definition),
        model=model,
    )
    content = artifact.read_text(encoding="utf-8", errors="replace")
    result = runner.run(lambda feedback: content)
    first = result.attempts[0] if result.attempts else None
    return {
        "model": model,
        "task": task,
        "score": result.final_score,
        "passed": result.final_success,
        "failing": list(first.failing_checks) if first else [],
        "critical": list(result.critical_failures),
        "artifact": str(artifact),
        "workdir": str(workdir),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", default="", help="only this task id")
    parser.add_argument("--model", default="", help="only models containing this text")
    parser.add_argument("--json", default="", help="write the full report here")
    args = parser.parse_args()

    rows: list[dict] = []
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for index, (model, task, artifact) in enumerate(discover_bakeoff(BAKEOFF)):
        if args.task and task != args.task:
            continue
        if args.model and args.model.lower() not in model.lower():
            continue
        print(f"[score] {model} :: {task}", flush=True)
        rows.append(rescore(model, task, artifact, index, stamp))

    for row in rows:
        flag = "PASS" if row["passed"] else "FAIL"
        print(f"\n{flag} {row['model']} :: {row['task']}  score={row['score']}")
        for name in row["failing"]:
            print(f"   - {name}")
        if row["critical"]:
            print(f"   critical: {', '.join(row['critical'])}")

    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
