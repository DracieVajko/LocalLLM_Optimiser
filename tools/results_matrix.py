"""Final results matrix after the retry queue: core tasks per model."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

CORE = ["email_write", "company_website", "minecraft_world", "blender_city", "deep_research_report"]


def load(path: str) -> list[dict]:
    rows: list[dict] = []
    p = Path(path)
    if not p.exists():
        return rows
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def cell(row: dict | None) -> str:
    if row is None:
        return "—"
    status = row.get("status") or "measured"
    if status != "measured":
        return "n/m"
    score = row.get("final_score")
    if score is None:
        return "—"
    mark = "✓" if row.get("final_success") else "✗"
    return f"{score:.2f}{mark}"


def main() -> None:
    rows = load("results/sandbox_runs.jsonl")
    newest: dict[tuple, dict] = {}
    for row in rows:
        key = (row.get("origin") or "local", row.get("model"), row.get("task"))
        newest[key] = row

    by_model: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)
    for (origin, model, task), row in newest.items():
        by_model[(origin, model)][task] = row

    print("| model | " + " | ".join(CORE) + " |")
    print("|---|" + "---|" * len(CORE))
    for (origin, model), tasks in sorted(by_model.items()):
        if origin != "local":
            continue
        label = model.split("/")[-1][:34]
        print("| " + label + " | " + " | ".join(cell(tasks.get(t)) for t in CORE) + " |")

    print("\nfrontier:")
    for (origin, model), tasks in sorted(by_model.items()):
        if origin != "frontier":
            continue
        print("| " + model + " | " + " | ".join(cell(tasks.get(t)) for t in CORE) + " |")

    print("\nrows:", len(rows), " local:",
          sum(1 for r in rows if (r.get("origin") or "local") == "local"))


if __name__ == "__main__":
    main()
