"""Generate a scoreboard from bakeoff/sandbox results.

Reads results/bakeoff/runs.jsonl and results/sandbox_runs.jsonl and produces
a markdown scoreboard with per-model metrics, coverage, and failure modes.

Usage:
    python tools/generate_scoreboard.py
    python tools/generate_scoreboard.py --output results/SCOREBOARD.md
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def generate_scoreboard() -> str:
    bakeoff_rows = _load_jsonl(ROOT / "results" / "bakeoff" / "runs.jsonl")
    sandbox_rows = _load_jsonl(ROOT / "results" / "sandbox_runs.jsonl")

    lines: list[str] = []
    lines.append("# Auto-generated scoreboard")
    lines.append("")
    lines.append(f"Generated: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # --- Bakeoff section ---
    if bakeoff_rows:
        lines.append("## Bakeoff (optimization)")
        lines.append("")
        by_model: dict[str, list[dict]] = defaultdict(list)
        for row in bakeoff_rows:
            by_model[row.get("model", "?")].append(row)

        lines.append("| model | best tok/s | best task score | runs |")
        lines.append("|---|---:|---:|---:|")
        for model, rows in sorted(by_model.items()):
            speeds = [r.get("tok_s") or 0 for r in rows if r.get("tok_s")]
            quals = [r.get("final_score") for r in rows if r.get("final_score") is not None]
            best_speed = max(speeds) if speeds else 0
            best_qual = max(quals) if quals else 0
            lines.append(f"| {model} | {best_speed:.1f} | {best_qual:.3f} | {len(rows)} |")
        lines.append("")

    # --- Sandbox section ---
    if sandbox_rows:
        lines.append("## Sandbox (task scores)")
        lines.append("")
        latest: dict[tuple[str, str], dict] = {}
        for row in sorted(sandbox_rows, key=lambda r: str(r.get("ts", ""))):
            latest[(row.get("model"), row.get("task"))] = row

        models = sorted({r.get("model") for r in sandbox_rows})
        tasks = sorted({r.get("task") for r in sandbox_rows})

        lines.append("| model | passed | measured | total | mean score |")
        lines.append("|---|---:|---:|---:|---:|")
        for model in models:
            model_tasks = [t for t in tasks if (model, t) in latest]
            passed = sum(1 for t in model_tasks if latest[(model, t)].get("final_success"))
            measured = sum(1 for t in model_tasks if latest[(model, t)].get("final_score") is not None and latest[(model, t)].get("status") != "not_measured")
            scores = [latest[(model, t)]["final_score"] for t in model_tasks if latest[(model, t)].get("final_score") is not None and latest[(model, t)].get("status") != "not_measured"]
            mean = round(statistics.fmean(scores), 3) if scores else None
            lines.append(f"| {model} | {passed} | {measured} | {len(model_tasks)} | {mean if mean is not None else '-'} |")
        lines.append("")

        # Per-task matrix
        lines.append("### Per-task matrix (latest score)")
        lines.append("")
        short_models = [m.split("/")[-1][:12] for m in models]
        lines.append("| task | " + " | ".join(short_models) + " |")
        lines.append("|" + "---|" * (len(models) + 1))
        for task in tasks:
            cells = [task]
            for m in models:
                r = latest.get((m, task))
                if not r:
                    cells.append("-")
                elif r.get("status") == "not_measured" or r.get("final_score") is None:
                    cells.append("n/m")
                elif r.get("status") == "not_applicable":
                    cells.append("n/a")
                else:
                    mark = "✅" if r.get("final_success") else "❌"
                    cells.append(f"{mark}{r['final_score']:.2f}")
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

    # --- Failure modes ---
    if sandbox_rows:
        lines.append("## Failure modes (from critical_failures)")
        lines.append("")
        failures: dict[str, int] = defaultdict(int)
        for row in sandbox_rows:
            for cf in row.get("critical_failures") or []:
                name = cf.split(" (")[0]
                failures[name] += 1
        if failures:
            lines.append("| failure | count |")
            lines.append("|---|---:|")
            for name, count in sorted(failures.items(), key=lambda x: -x[1]):
                lines.append(f"| {name} | {count} |")
            lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", "-o", type=Path, default=None, help="Output file (default: stdout)")
    args = parser.parse_args()
    text = generate_scoreboard()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"scoreboard written to {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())