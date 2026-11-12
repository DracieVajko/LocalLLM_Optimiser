"""Merge desloppify review batch outputs into one import file.

The review runner writes one ``batch-N.raw.txt`` per batch into a run
directory. This utility merges those batches into a single ``merged.json``
that ``desloppify review --import`` can consume.

Usage::

    python tools/merge_desloppify.py                      # newest run directory
    python tools/merge_desloppify.py --run-dir <dir>     # a specific run
    python tools/merge_desloppify.py --run-dir <dir> --out merged.json
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

DEFAULT_RUNS_ROOT = Path(".desloppify") / "subagents" / "runs"


def newest_run_dir(root: Path = DEFAULT_RUNS_ROOT) -> Path | None:
    """The most recent run directory (name is a timestamp, so it sorts)."""
    if not root.is_dir():
        return None
    candidates = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name)
    return candidates[-1] if candidates else None


def merge_run(run_dir: Path, out_path: Path | None = None) -> dict:
    """Merge every batch output of ``run_dir`` and write the import file."""
    results = run_dir / "results"
    out_path = out_path or (run_dir / "merged.json")

    assessments: dict[str, list[float]] = defaultdict(list)
    findings: list[dict] = []
    batches = sorted(results.glob("batch-*.raw.txt"))
    for path in batches:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"skip (bad json): {path.name}")
            continue
        for dimension, score in (data.get("assessments") or {}).items():
            assessments[dimension].append(float(score))
        issues = data.get("issues") or data.get("findings") or []
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            if issue.get("concern_verdict"):
                continue
            if not issue.get("dimension") or not issue.get("summary"):
                continue
            if not issue.get("related_files") or not issue.get("evidence"):
                continue
            findings.append(
                {
                    "dimension": issue["dimension"],
                    "identifier": issue.get("identifier", path.stem),
                    "summary": issue["summary"],
                    "related_files": issue.get("related_files", []),
                    "evidence": issue.get("evidence", []),
                    "suggestion": issue.get("suggestion", ""),
                    "confidence": issue.get("confidence", "medium"),
                }
            )

    merged = {
        "assessments": {
            dimension: round(sum(scores) / len(scores), 1)
            for dimension, scores in sorted(assessments.items())
        },
        "findings": findings,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"batches: {len(batches)}")
    print(f"dimensions: {len(assessments)}")
    print(f"findings: {len(findings)}")
    print(f"merged: {out_path}")
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        default="",
        help="Run directory with the batch outputs (default: the newest one).",
    )
    parser.add_argument("--out", default="", help="Output file (default: <run-dir>/merged.json)")
    args = parser.parse_args()

    run_dir = Path(args.run_dir) if args.run_dir else newest_run_dir()
    if run_dir is None:
        print("no desloppify run directory found")
        return 1
    if not run_dir.is_dir():
        print(f"run directory not found: {run_dir}")
        return 1

    merge_run(run_dir, Path(args.out) if args.out else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
