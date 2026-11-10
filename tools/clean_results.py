"""Delete regenerable benchmark by-products so ``results/`` stays small.

``results/`` is gitignored; everything in it can be rebuilt except the raw model
answers, which took hours to generate. This tool therefore never touches
``results/bakeoff`` unless you ask for it explicitly.

Usage:
    python tools/clean_results.py --list
    python tools/clean_results.py --yes                 # scratch runs only
    python tools/clean_results.py --yes --include-bakeoff
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"

#: Regenerable by a single command.
SCRATCH = (
    "compare/runs",
    "compare/visuals",
    "explain/runs",
    "retry",
    "sandbox",
)

#: Hours of model time; only with --include-bakeoff.
EXPENSIVE = ("bakeoff",)


def _size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="show what would be deleted")
    parser.add_argument("--yes", action="store_true", help="actually delete")
    parser.add_argument("--include-bakeoff", action="store_true")
    parser.add_argument(
        "--prune-history",
        action="store_true",
        help="drop sandbox history records whose workdir no longer exists",
    )
    args = parser.parse_args()

    targets = [RESULTS / rel for rel in SCRATCH]
    if args.include_bakeoff:
        targets += [RESULTS / rel for rel in EXPENSIVE]

    total = 0
    for path in targets:
        size = _size(path)
        if size == 0 and not path.exists():
            continue
        total += size
        print(f"{size / 1_048_576:8.1f} MB  {path.relative_to(ROOT)}")
    print(f"{total / 1_048_576:8.1f} MB total")

    if args.list or not args.yes:
        print("\n(dry run; pass --yes to delete)")
        return 0

    for path in targets:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    print("deleted")

    if args.prune_history:
        removed = _prune_history()
        print(f"history records removed: {removed}")
    return 0


def _prune_history() -> int:
    """Keep only history records whose artifact directory still exists."""
    import json

    history = RESULTS / "sandbox_runs.jsonl"
    if not history.exists():
        return 0
    kept: list[str] = []
    removed = 0
    for line in history.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            removed += 1
            continue
        workdir = str(record.get("workdir") or "")
        if workdir and not Path(workdir).exists():
            removed += 1
            continue
        kept.append(line)
    history.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return removed


if __name__ == "__main__":
    raise SystemExit(main())
