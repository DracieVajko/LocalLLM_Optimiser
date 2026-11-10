"""A non-run must be reported as 'not measured', never as a 0.00 score."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from lm_optimizer.services.model_gate import ModelGate
from lm_optimizer.services.sandbox_history import record_run
from lm_optimizer.services.sandbox_lab import SANDBOX_TASKS, SandboxPolicy
from lm_optimizer.services.sandbox_runner import SandboxRunner, build_command_for


def _runner(tmp_path: Path, task_id: str = "email_write") -> SandboxRunner:
    task = replace(SANDBOX_TASKS[task_id], max_repair_attempts=0)
    workdir = tmp_path / task_id
    return SandboxRunner(
        task=task,
        policy=SandboxPolicy(workdir=workdir, network_enabled=False, timeout_s=task.timeout_s),
        workdir=workdir,
        command=build_command_for(task),
    )


def test_empty_completion_is_not_measured(tmp_path: Path) -> None:
    runner = _runner(tmp_path)

    result = runner.run(lambda feedback: "")

    assert result.status == "not_measured"
    assert result.final_success is False
    assert result.attempts == []
    assert result.error == "empty model output"


def test_whitespace_completion_is_not_measured(tmp_path: Path) -> None:
    runner = _runner(tmp_path)

    result = runner.run(lambda feedback: "   \n\t ")

    assert result.status == "not_measured"


def test_generation_exception_is_not_measured(tmp_path: Path) -> None:
    runner = _runner(tmp_path)

    def explode(feedback: str) -> str:
        raise RuntimeError("HTTP 500 engine aborted")

    result = runner.run(explode)

    assert result.status == "not_measured"
    assert result.final_score == 0.0
    assert "500" in result.error


def test_real_output_is_measured(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    email = (
        "Subject: Kickoff follow-up\n\nHi Sarah,\n\n"
        "Next step is the roadmap by Friday 14 November.\n\nBest regards,\nAlex\n"
    )

    result = runner.run(lambda feedback: email)

    assert result.status == "measured"
    assert result.final_score == pytest.approx(1.0)


def test_history_stores_null_score_for_unmeasured_run(tmp_path: Path) -> None:
    history = tmp_path / "runs.jsonl"

    record_run(
        "some-model",
        "email_write",
        {"status": "not_measured", "final_score": 0.0, "final_success": False},
        workdir=str(tmp_path / "sandbox" / "run"),
        path=history,
    )

    stored = json.loads(history.read_text(encoding="utf-8").splitlines()[0])
    assert stored["status"] == "not_measured"
    assert stored["final_score"] is None


def test_history_keeps_score_for_measured_run(tmp_path: Path) -> None:
    history = tmp_path / "runs.jsonl"

    record_run(
        "some-model",
        "email_write",
        {"status": "measured", "final_score": 0.75, "final_success": False},
        workdir="",
        path=history,
    )

    stored = json.loads(history.read_text(encoding="utf-8").splitlines()[0])
    assert stored["final_score"] == 0.75


class _LostResponseClient:
    """Load call returns success but the HTTP response was never received."""

    async def load_model(self, model_id: str, load_config: object) -> dict:
        return {"success": True, "response_received": False}

    async def unload_model(self, **kwargs: object) -> None:
        return None


class _NormalClient(_LostResponseClient):
    async def load_model(self, model_id: str, load_config: object) -> dict:
        return {"success": True, "response_received": True}


def _gate_config():
    from lm_optimizer.services.model_gate import ModelGateConfig

    return ModelGateConfig(enabled=False)


async def test_load_measured_false_when_response_was_lost() -> None:
    gate = ModelGate(_LostResponseClient(), _gate_config())

    lease = await gate.acquire("m")

    assert lease.load_measured is False


async def test_load_measured_true_for_a_normal_load() -> None:
    gate = ModelGate(_NormalClient(), _gate_config())

    lease = await gate.acquire("m")

    assert lease.load_measured is True
