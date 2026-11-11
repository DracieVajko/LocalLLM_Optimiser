"""Merge the 20 desloppify batch outputs into one import file."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

RUN_DIR = Path(".desloppify/subagents/runs/20261111_143620")
RESULTS = RUN_DIR / "results"
MERGED = RUN_DIR / "merged.json"


def main() -> int:
    assessments: dict[str, list[float]] = defaultdict(list)
    findings: list[dict] = []
    for path in sorted(RESULTS.glob("batch-*.raw.txt")):
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
            finding = {
                "dimension": issue["dimension"],
                "identifier": issue.get("identifier", path.stem),
                "summary": issue["summary"],
                "related_files": issue.get("related_files", []),
                "evidence": issue.get("evidence", []),
                "suggestion": issue.get("suggestion", ""),
                "confidence": issue.get("confidence", "medium"),
            }
            findings.append(finding)

    merged = {
        "assessments": {
            dimension: round(sum(scores) / len(scores), 1)
            for dimension, scores in sorted(assessments.items())
        },
        "findings": findings,
    }
    MERGED.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"batches: {len(list(RESULTS.glob('batch-*.raw.txt')))}")
    print(f"dimensions: {len(assessments)}")
    print(f"findings: {len(findings)}")
    print(f"merged: {MERGED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
