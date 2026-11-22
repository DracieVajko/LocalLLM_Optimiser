"""Repository helpers for the ``benchmarks`` and ``quality_results`` tables.

These tables exist in the schema but were historically unused: the optimizer
stored benchmark metrics and quality scores inside ``configurations.metrics_json``
and ``configurations.quality_json``. Normalising them into their own tables makes
cross-run analysis and leaderboards possible without parsing JSON blobs.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Any


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class BenchmarkRepository:
    """CRUD for the ``benchmarks`` table."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save(
        self,
        *,
        config_id: str,
        test_name: str,
        category: str = "",
        repetition: int = 0,
        success: bool = False,
        load_time_ms: float = 0.0,
        ttft_ms: float = 0.0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        prompt_processing_ms: float = 0.0,
        generation_ms: float = 0.0,
        prompt_tok_s: float = 0.0,
        generation_tok_s: float = 0.0,
        output_text: str = "",
        error: str = "",
        estimated_ttft_ms: float = 0.0,
    ) -> str:
        row_id = str(uuid.uuid4())
        self.conn.execute(
            """
            INSERT INTO benchmarks (
                id, config_id, test_name, category, repetition, success,
                load_time_ms, ttft_ms, prompt_tokens, completion_tokens,
                total_tokens, prompt_processing_ms, generation_ms,
                prompt_tok_s, generation_tok_s, output_text, error,
                created_at, estimated_ttft_ms
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row_id, config_id, test_name, category, repetition, int(success),
                load_time_ms, ttft_ms, prompt_tokens, completion_tokens,
                total_tokens, prompt_processing_ms, generation_ms,
                prompt_tok_s, generation_tok_s, output_text, error,
                _now(), estimated_ttft_ms,
            ),
        )
        self.conn.commit()
        return row_id

    def get_by_config(self, config_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM benchmarks WHERE config_id = ? ORDER BY created_at",
            (config_id,),
        ).fetchall()
        cols = [d[0] for d in self.conn.execute("SELECT * FROM benchmarks LIMIT 0").description]
        return [dict(zip(cols, r)) for r in rows]


class QualityResultRepository:
    """CRUD for the ``quality_results`` table."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save(
        self,
        *,
        config_id: str,
        test_name: str,
        overall: float = 0.0,
        task_completion: float = 0.0,
        factual_consistency: float = 0.0,
        format_compliance: float = 0.0,
        coding_correctness: float = 0.0,
        no_truncation: float = 0.0,
        no_malformed: float = 0.0,
        confident: bool = True,
        details: dict[str, Any] | None = None,
        checks_passed: int | None = None,
        checks_total: int | None = None,
    ) -> str:
        row_id = str(uuid.uuid4())
        self.conn.execute(
            """
            INSERT INTO quality_results (
                id, config_id, test_name, overall, task_completion,
                factual_consistency, format_compliance, coding_correctness,
                no_truncation, no_malformed, confident, details_json,
                created_at, checks_passed, checks_total
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row_id, config_id, test_name, overall, task_completion,
                factual_consistency, format_compliance, coding_correctness,
                no_truncation, no_malformed, int(confident),
                json.dumps(details or {}), _now(), checks_passed, checks_total,
            ),
        )
        self.conn.commit()
        return row_id

    def get_by_config(self, config_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM quality_results WHERE config_id = ? ORDER BY created_at",
            (config_id,),
        ).fetchall()
        cols = [d[0] for d in self.conn.execute("SELECT * FROM quality_results LIMIT 0").description]
        return [dict(zip(cols, r)) for r in rows]