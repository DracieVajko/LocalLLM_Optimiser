"""Tests for `clean_tests` CLI command (spec 4.2 cleanup automation).

Removes runs with status='failed' after --failed-count consecutive failures
per model. Only within project folder; never deletes outside directory.
Default is dry run; pass --confirm to delete.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from typer.testing import CliRunner

from lm_optimizer.cli.main import app
from lm_optimizer.database.repositories import run_repo
from lm_optimizer.domain.models import (
    ConfigurationStatus,
    ModelIdentity,
    OptimizationProfile,
    OptimizationRun,
)


def _make_run(model_id: str, status: str = "failed", run_id: str | None = None) -> OptimizationRun:
    """Create an OptimizationRun with given status."""
    run = OptimizationRun(
        model=ModelIdentity(id=model_id, name=model_id),
        profile=OptimizationProfile.BALANCED,
    )
    run.id = run_id or str(uuid4())
    run.status = ConfigurationStatus(status)
    run.created_at = datetime.now(timezone.utc)
    return run


def test_clean_tests_dry_run_lists_candidates(monkeypatch):
    """Dry run should list candidates but delete nothing."""
    runs = [
        _make_run("model-a", "failed", "r1"),
        _make_run("model-a", "failed", "r2"),
        _make_run("model-a", "failed", "r3"),
        _make_run("model-b", "failed", "r4"),
        _make_run("model-c", "passed", "r5"),
    ]

    monkeypatch.setattr(run_repo, "list_all", lambda limit=10000: runs)
    monkeypatch.setattr(
        run_repo, "get", lambda run_id: next((r for r in runs if r.id == run_id), None)
    )

    runner = CliRunner()
    result = runner.invoke(app, ["clean-tests", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "model-a" in result.output
    assert "model-b" not in result.output  # only 1 failure, below threshold
    assert "model-c" not in result.output  # success, not failed


def test_clean_tests_deletes_failed_runs(monkeypatch):
    """--confirm deletes failed runs with >= --failed-count consecutive failures."""
    runs = [
        _make_run("model-a", "failed", "r1"),
        _make_run("model-a", "failed", "r2"),
        _make_run("model-a", "failed", "r3"),
        _make_run("model-b", "failed", "r4"),
        _make_run("model-c", "passed", "r5"),
    ]

    deleted_run_ids = []

    def fake_delete(run_id: str) -> bool:
        deleted_run_ids.append(run_id)
        return True

    monkeypatch.setattr(run_repo, "list_all", lambda limit=10000: runs)
    monkeypatch.setattr(
        run_repo, "get", lambda run_id: next((r for r in runs if r.id == run_id), None)
    )
    monkeypatch.setattr(run_repo, "delete", fake_delete)

    runner = CliRunner()
    result = runner.invoke(app, ["clean-tests", "--confirm", "--failed-count", "2"])
    assert result.exit_code == 0, result.output
    assert "model-a" in result.output
    assert "Removed" in result.output

    # model-a runs deleted (3 failures >= threshold of 2)
    assert set(deleted_run_ids) == {"r1", "r2", "r3"}
    # model-b (1 failure) and model-c (success) NOT deleted
    assert "r4" not in deleted_run_ids
    assert "r5" not in deleted_run_ids


def test_clean_tests_default_dry_run(monkeypatch):
    """Default behavior is dry run (no deletion)."""
    runs = [
        _make_run("model-a", "failed", "r1"),
        _make_run("model-a", "failed", "r2"),
    ]

    deleted = []
    monkeypatch.setattr(run_repo, "list_all", lambda limit=10000: runs)
    monkeypatch.setattr(
        run_repo, "get", lambda run_id: next((r for r in runs if r.id == run_id), None)
    )
    monkeypatch.setattr(run_repo, "delete", lambda run_id: deleted.append(run_id) or True)

    runner = CliRunner()
    result = runner.invoke(app, ["clean-tests"])
    assert result.exit_code == 0, result.output
    assert "Dry run" in result.output
    assert deleted == []  # nothing deleted


def test_clean_tests_default_failed_count_is_2(monkeypatch):
    """Default failed_count is 2: model-b with 1 failure should NOT be cleaned."""
    runs = [
        _make_run("model-a", "failed", "r1"),
        _make_run("model-a", "failed", "r2"),
        _make_run("model-b", "failed", "r3"),
    ]

    deleted = []
    monkeypatch.setattr(run_repo, "list_all", lambda limit=10000: runs)
    monkeypatch.setattr(
        run_repo, "get", lambda run_id: next((r for r in runs if r.id == run_id), None)
    )
    monkeypatch.setattr(run_repo, "delete", lambda run_id: deleted.append(run_id) or True)

    runner = CliRunner()
    result = runner.invoke(app, ["clean-tests", "--confirm"])
    assert result.exit_code == 0, result.output
    # model-a (3 failures >= 2) deleted; model-b (1 failure < 2) kept
    assert set(deleted) == {"r1", "r2"}
    assert "r3" not in deleted


def test_clean_tests_no_failed_runs(monkeypatch):
    """No failed runs -> nothing to delete."""
    runs = [_make_run("model-x", "passed", "r1")]

    monkeypatch.setattr(run_repo, "list_all", lambda limit=10000: runs)

    runner = CliRunner()
    result = runner.invoke(app, ["clean-tests"])
    assert result.exit_code == 0, result.output
    assert "No failed runs found" in result.output
