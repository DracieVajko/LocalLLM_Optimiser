"""The web sandbox job must record history with its own run fingerprint."""

from __future__ import annotations

import asyncio

import pytest

from lm_optimizer.api import routes
from lm_optimizer.services import sandbox_history as sh
from lm_optimizer.services import sandbox_runner


class _FakeRunner:
    def __init__(self, **kwargs):
        self.workdir = kwargs.get("workdir")

    async def run(self, generate):  # pragma: no cover - result shape only
        return _FakeResult()


class _FakeResult:
    status = "measured"

    def as_dict(self):
        return {
            "task_id": "email_write",
            "status": "measured",
            "final_score": 1.0,
            "penalized_score": 1.0,
            "final_success": True,
            "first_pass_success": True,
        }


class _FakeClient:
    async def chat_completion(self, **kwargs):
        return {"choices": [{"message": {"content": "hello"}}]}

    async def close(self):
        return None


@pytest.fixture
def captured(monkeypatch, tmp_path):
    seen: dict = {}

    def fake_record(*args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return {}

    monkeypatch.setattr(sh, "record_run", fake_record)
    monkeypatch.setattr(sh, "RESULTS_ROOT", tmp_path / "results")
    monkeypatch.setattr(sandbox_runner, "SandboxRunner", _FakeRunner)
    monkeypatch.setattr(sandbox_runner, "apply_retention", lambda *a, **k: [])

    async def fake_client(*args, **kwargs):
        return _FakeClient()

    monkeypatch.setattr(routes, "get_lm_client", fake_client)
    monkeypatch.chdir(tmp_path)
    return seen


def _run_job(job_id: str) -> None:
    # The POST /lab/sandbox-run endpoint seeds the job before scheduling it.
    routes._sandbox_jobs[job_id] = {"status": "pending", "result": None, "error": None}
    asyncio.run(routes._run_sandbox_job(job_id, "email_write", "model-x"))


def test_web_sandbox_job_records_history(captured):
    _run_job("job-1")
    kwargs = captured["kwargs"]
    assert captured["args"][:2] == ("model-x", "email_write")
    assert kwargs["settings"]["temperature"] == pytest.approx(0.2)
    assert kwargs["settings"]["max_output_tokens"] == 2048
    assert kwargs["prompt"]


def test_web_sandbox_job_settings_never_match_a_cli_run(captured):
    _run_job("job-2")
    job = captured["kwargs"]["settings"]
    prompt = captured["kwargs"]["prompt"]
    cli = sh.normalize_settings(temperature=0.0, max_output_tokens=2048)
    assert sh.fingerprint("model-x", "email_write", prompt, job) != sh.fingerprint(
        "model-x", "email_write", prompt, cli
    )
