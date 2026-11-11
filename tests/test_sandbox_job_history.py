"""The web sandbox job must record history with its own run fingerprint.

These tests run the real SandboxRunner (a text task needs no command), so a
sync/async mistake in the job fails them instead of being hidden by a fake.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from lm_optimizer.api import routes
from lm_optimizer.services import sandbox_history as sh


class _FakeClient:
    async def chat_completion(self, **kwargs):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            "Subject: Launch update\n\n"
                            "Hi team, the new build is ready for review today."
                        )
                    }
                }
            ]
        }

    async def close(self):
        return None


@pytest.fixture
def web_job(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sh, "RESULTS_ROOT", tmp_path / "results")

    async def fake_client(*args, **kwargs):
        return _FakeClient()

    monkeypatch.setattr(routes, "get_lm_client", fake_client)

    def run(job_id: str) -> dict:
        routes._sandbox_jobs[job_id] = {
            "status": "pending",
            "result": None,
            "error": None,
        }
        asyncio.run(routes._run_sandbox_job(job_id, "email_write", "model-x"))
        return routes._sandbox_jobs[job_id]

    return run


def _history_rows(tmp_path) -> list[dict]:
    path = tmp_path / "results" / "sandbox_runs.jsonl"
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_web_sandbox_job_completes_and_records_one_row(web_job, tmp_path):
    job = web_job("job-real")
    assert job["status"] == "completed", job.get("error")
    rows = _history_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["model"] == "model-x"
    assert rows[0]["task"] == "email_write"
    assert rows[0]["settings"]["temperature"] == pytest.approx(0.2)
    assert rows[0]["settings"]["max_output_tokens"] == 2048
    assert rows[0]["run_key"]


def test_web_sandbox_job_settings_never_match_a_cli_run(web_job, tmp_path):
    web_job("job-real")
    row = _history_rows(tmp_path)[0]
    cli = sh.normalize_settings(temperature=0.0, max_output_tokens=2048)
    assert sh.fingerprint("model-x", "email_write", "prompt", row["settings"]) != (
        sh.fingerprint("model-x", "email_write", "prompt", cli)
    )
