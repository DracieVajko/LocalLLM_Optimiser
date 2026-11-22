"""Backfill benchmarks and quality_results from configurations JSON.

Run once to populate the previously-empty tables:
    python tools/backfill_benchmarks.py
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "optimizer.db"


def main() -> int:
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, metrics_json, quality_json FROM configurations"
    ).fetchall()
    b_repo = None
    q_repo = None
    try:
        from lm_optimizer.database.result_repositories import (
            BenchmarkRepository,
            QualityResultRepository,
        )

        b_repo = BenchmarkRepository(conn)
        q_repo = QualityResultRepository(conn)
    except Exception as exc:
        print(f"import failed: {exc}")
        return 1

    b_count = 0
    q_count = 0
    for row in rows:
        cfg_id = row["id"]
        metrics = json.loads(row["metrics_json"]) if row["metrics_json"] else []
        quality = json.loads(row["quality_json"]) if row["quality_json"] else None
        if isinstance(metrics, list):
            for m in metrics:
                b_repo.save(
                    config_id=cfg_id,
                    test_name=m.get("test_name", ""),
                    category=m.get("category", ""),
                    success=bool(m.get("success", False)),
                    load_time_ms=m.get("load_time_ms", 0.0),
                    ttft_ms=m.get("estimated_ttft_ms", 0.0),
                    prompt_tokens=m.get("prompt_tokens", 0),
                    completion_tokens=m.get("completion_tokens", 0),
                    total_tokens=m.get("total_tokens", 0),
                    prompt_processing_ms=m.get("prompt_processing_ms", 0.0),
                    generation_ms=m.get("generation_ms", 0.0),
                    prompt_tok_s=m.get("prompt_tok_s", 0.0),
                    generation_tok_s=m.get("generation_tok_s", 0.0),
                    output_text=m.get("output_text", ""),
                    error=m.get("error") or "",
                    estimated_ttft_ms=m.get("estimated_ttft_ms", 0.0),
                )
                b_count += 1
        if isinstance(quality, dict) and quality:
            q_repo.save(
                config_id=cfg_id,
                test_name="aggregate",
                overall=quality.get("overall", 0.0),
                task_completion=quality.get("task_completion", 0.0),
                factual_consistency=quality.get("factual_consistency", 0.0),
                format_compliance=quality.get("format_compliance", 0.0),
                coding_correctness=quality.get("coding_correctness", 0.0),
                no_truncation=quality.get("no_truncation", 0.0),
                no_malformed=quality.get("no_malformed", 0.0),
                confident=bool(quality.get("confident", True)),
                details=quality.get("details", {}),
                checks_passed=quality.get("checks_passed"),
                checks_total=quality.get("checks_total"),
            )
            q_count += 1
    print(f"backfilled {b_count} benchmark rows, {q_count} quality rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())