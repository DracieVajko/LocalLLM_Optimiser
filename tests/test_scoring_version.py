"""Scoring version stamp (WP-0).

Rows written before the version stamp existed carry no ``scoring_version``
field and are legacy (scoring_version = 0). Legacy and versioned rows must
never be averaged together.
"""

from __future__ import annotations

import json

from lm_optimizer.services import sandbox_history as sh
from lm_optimizer.scoring.version import SCORING_VERSION


def _result(score=1.0, status="measured", first_pass=None):
    return {
        "status": status,
        "first_pass_success": score == 1.0,
        "final_success": score == 1.0,
        "repair_count": 0,
        "final_score": score if status == "measured" else None,
        "penalized_score": score if status == "measured" else None,
        "first_pass_score": first_pass if first_pass is not None else score,
        "artifacts": ["out.txt"],
        "critical_failures": [],
        "error": "",
        "attempts": [{"attempt": 0, "score": first_pass if first_pass is not None else score}],
    }


def test_record_run_stamps_scoring_version_and_first_pass_score(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "RESULTS_ROOT", tmp_path)
    history = tmp_path / "runs.jsonl"
    settings = sh.normalize_settings(context_length=4096)

    # First pass scores 1.0, repaired to 1.0 on attempt 1 (penalized 0.9).
    result = _result(score=1.0, first_pass=0.6)
    result["repair_count"] = 1
    result["penalized_score"] = 0.9

    sh.record_run(
        "m", "task", result, workdir=str(tmp_path / "w"), duration_s=1,
        path=history, prompt="p", settings=settings,
    )

    row = json.loads(history.read_text().splitlines()[0])
    assert row["scoring_version"] == SCORING_VERSION == 7
    assert row["first_pass_score"] == 0.6
    assert row["final_score"] == 1.0
    assert row["penalized_score"] == 0.9


def test_legacy_row_without_field_is_version_zero():
    assert sh.scoring_version_of({"model": "m", "task": "t"}) == 0
    assert sh.scoring_version_of({"scoring_version": None}) == 0
    assert sh.scoring_version_of({"scoring_version": 4}) == 4
    assert sh.scoring_version_of({"scoring_version": 5}) == 5


def test_versions_4_and_5_are_distinct_never_one_mean():
    # Simulate a scoreboard grouping: version 4 rows and version 5 rows must
    # form separate groups; mixing them into a single mean must not happen.
    rows = [
        {"scoring_version": 4, "final_score": 1.0},
        {"scoring_version": 4, "final_score": 0.0},
        {"scoring_version": 5, "final_score": 1.0},
        {"scoring_version": 5, "final_score": 1.0},
        # legacy row, no field -> version 0
        {"model": "m", "task": "t", "final_score": 0.5},
    ]
    groups: dict[int, list[float]] = {}
    for row in rows:
        groups.setdefault(sh.scoring_version_of(row), []).append(
            row.get("final_score", 0.0)
        )
    assert set(groups) == {0, 4, 5}
    # Each version group is computed separately; never one mean across {4, 5}.
    mean_v4 = sum(groups[4]) / len(groups[4])
    mean_v5 = sum(groups[5]) / len(groups[5])
    assert mean_v4 == 0.5
    assert mean_v5 == 1.0
    # legacy group stands alone
    assert groups[0] == [0.5]
