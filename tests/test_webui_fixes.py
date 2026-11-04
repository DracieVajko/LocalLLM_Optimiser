"""Web UI reliability fixes: legacy run statuses and sandbox run history."""

from pathlib import Path

from lm_optimizer.database.repositories import _safe_enum
from lm_optimizer.domain.enums import OptimizationStage, RunStatus, SUCCESS_STATES
from lm_optimizer.services import sandbox_history


def test_cleaned_status_is_known():
    # Old cleanup tool wrote this; a single row must not break /api/runs.
    assert RunStatus("cleaned") is RunStatus.CLEANED
    assert RunStatus.CLEANED.value == "cleaned"


def test_safe_enum_falls_back_for_unknown_values():
    assert _safe_enum(RunStatus, "totally-new-status", RunStatus.FAILED) is RunStatus.FAILED
    assert _safe_enum(OptimizationStage, "gone", OptimizationStage.COMPLETE) is OptimizationStage.COMPLETE
    assert _safe_enum(RunStatus, "success", RunStatus.FAILED) is RunStatus.SUCCESS


def test_cleaned_is_not_a_success_state():
    # A cleaned record carries no validated winner.
    assert RunStatus.CLEANED not in SUCCESS_STATES


def test_sandbox_history_roundtrip(tmp_path: Path):
    path = tmp_path / "sandbox_runs.jsonl"
    record = sandbox_history.record_run(
        "model-a",
        "email_write",
        {
            "first_pass_success": True,
            "final_success": True,
            "repair_count": 0,
            "final_score": 1.0,
            "penalized_score": 1.0,
            "artifacts": ["email.txt"],
            "critical_failures": [],
            "error": "",
        },
        workdir="results/sandbox/email_write/20260101_000000",
        duration_s=12.5,
        path=path,
    )
    assert record["model"] == "model-a"
    assert record["duration_s"] == 12.5

    listed = sandbox_history.list_runs(10, path=path)
    assert len(listed) == 1
    assert listed[0]["task"] == "email_write"
    assert listed[0]["final_success"] is True


def test_sandbox_history_skips_malformed_lines(tmp_path: Path):
    path = tmp_path / "sandbox_runs.jsonl"
    path.write_text('{"model": "a", "task": "t"}\nnot-json\n', encoding="utf-8")
    listed = sandbox_history.list_runs(10, path=path)
    assert listed == [{"model": "a", "task": "t"}]


def test_sandbox_history_missing_file_is_empty(tmp_path: Path):
    assert sandbox_history.list_runs(10, path=tmp_path / "missing.jsonl") == []
