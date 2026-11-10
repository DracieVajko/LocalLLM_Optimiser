"""Delete models that are no longer downloaded in LM Studio, plus their data.

The optimiser database keeps a row per model it has ever seen, with runs and
per-run configurations hanging off it. After deleting a model in LM Studio the
rows stay behind and clutter the model list, the way `lms ls` and the API no
longer show them.

This tool compares the database against the live LM Studio model list and
removes the orphans, after writing a timestamped backup of the database.

Usage:
    python tools/prune_models.py --dry-run
    python tools/prune_models.py --yes
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "optimizer.db"
BACKUPS = ROOT / "data" / "backup"


def downloaded_models(url: str = "http://127.0.0.1:1234") -> set[str]:
    response = httpx.get(f"{url}/api/v0/models", timeout=15)
    response.raise_for_status()
    ids = set()
    for model in response.json().get("data", []):
        model_id = str(model.get("id") or "").strip()
        if model_id:
            ids.add(model_id.lower())
    return ids


def base_id(model_id: str) -> str:
    """``qwen/x@q4_k_m`` -> ``qwen/x`` so quant variants still match."""
    return model_id.split("@", 1)[0].strip().lower()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="apply the deletion")
    parser.add_argument("--dry-run", action="store_true", help="print the plan only (default)")
    parser.add_argument("--db", default=str(DB))
    parser.add_argument("--url", default="http://127.0.0.1:1234")
    args = parser.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"database not found: {db}")
        return 2

    present = downloaded_models(args.url)
    print(f"LM Studio reports {len(present)} model(s):")
    for model_id in sorted(present):
        print(f"  + {model_id}")

    connection = sqlite3.connect(db)
    connection.row_factory = sqlite3.Row
    models = list(connection.execute("select id, name from models order by id"))

    keep: list[str] = []
    stale: list[dict] = []
    for row in models:
        if base_id(row["id"]) in present or base_id(row["name"]) in present:
            keep.append(row["id"])
        else:
            stale.append({"id": row["id"], "name": row["name"]})

    print(f"\n{len(keep)} kept, {len(stale)} stale:")
    for row in stale:
        print(f"  - {row['id']}  ({row['name']})")

    if not stale:
        connection.close()
        return 0

    stale_ids = [row["id"] for row in stale]
    marks = ",".join("?" for _ in stale_ids)
    run_ids = [
        row["id"]
        for row in connection.execute(
            f"select id from runs where model_id in ({marks})", stale_ids
        )
    ]
    config_count = 0
    if run_ids:
        run_marks = ",".join("?" for _ in run_ids)
        config_count = connection.execute(
            f"select count(*) from configurations where run_id in ({run_marks})", run_ids
        ).fetchone()[0]

    print(f"\nrelated rows: {len(run_ids)} run(s), {config_count} configuration(s)")

    if not args.yes:
        connection.close()
        print("\ndry run; pass --yes to delete")
        return 0

    BACKUPS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BACKUPS / f"optimizer_before_prune_{stamp}.db"
    shutil.copyfile(db, backup)
    print(f"backup: {backup}")

    try:
        with connection:
            if run_ids:
                run_marks = ",".join("?" for _ in run_ids)
                connection.execute(
                    f"delete from configurations where run_id in ({run_marks})", run_ids
                )
                connection.execute(f"delete from runs where id in ({run_marks})", run_ids)
            connection.execute(f"delete from models where id in ({marks})", stale_ids)
        connection.execute("vacuum")
    finally:
        connection.close()

    print(f"deleted {len(stale_ids)} model(s), {len(run_ids)} run(s), {config_count} configuration(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
