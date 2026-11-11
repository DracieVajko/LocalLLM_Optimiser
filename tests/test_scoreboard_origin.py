"""The local ranking must never include an API-provider (frontier) run."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("scoreboard", ROOT / "tools" / "scoreboard.py")
scoreboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scoreboard)


def _row(model, task, score, origin=None):
    row = {
        "model": model,
        "task": task,
        "status": "measured",
        "final_score": score,
        "gen_s": 10.0,
    }
    if origin:
        row["origin"] = origin
    return row


def test_frontier_rows_do_not_enter_the_local_text_table():
    local = _row("local-model", "email_write", 0.6)
    frontier = _row("deepseek-v4.1-flash (agent)", "email_write", 1.0, origin="frontier")
    rows = [row for row in (local, frontier) if scoreboard.origin_of(row) != "frontier"]
    table = "\n".join(scoreboard.text_table(rows))
    assert "local-model" in table
    assert "deepseek" not in table


def test_origin_of_reads_legacy_rows_as_local():
    assert scoreboard.origin_of({"model": "m"}) == "local"
    assert scoreboard.origin_of({"model": "m", "origin": "frontier"}) == "frontier"
