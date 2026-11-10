"""Scoring reference tests: known-good artifacts must score 1.0, known-bad low.

These tests are the reference point for the sandbox scoring system. They use
the committed frontier artifacts as the "good" side and tiny synthetic files
as the "bad" side, so a regression in weights, critical checks or negations
shows up immediately.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from lm_optimizer.services.sandbox_lab import (
    SANDBOX_TASKS,
    SandboxCheck,
    SandboxPolicy,
    SandboxTask,
    SandboxTaskKind,
    score_attempt,
)
from lm_optimizer.services.sandbox_runner import SandboxRunner, build_command_for

ROOT = Path(__file__).resolve().parents[1]
GOOD = ROOT / "benchmarks" / "deepseek_agent"


def _run(task_id: str, _filename: str, content: str, tmp_path: Path):
    definition = replace(SANDBOX_TASKS[task_id], max_repair_attempts=0)
    workdir = tmp_path / task_id
    policy = SandboxPolicy(
        workdir=workdir,
        network_enabled=False,
        timeout_s=definition.timeout_s,
        allowed_executables=definition.allowed_executables,
    )
    runner = SandboxRunner(
        task=definition,
        policy=policy,
        workdir=workdir,
        command=build_command_for(definition),
    )
    return runner.run(lambda feedback: content)


def _read(*parts: str) -> str:
    return (GOOD.joinpath(*parts)).read_text(encoding="utf-8")


def test_minecraft_good_artifact_scores_exactly_one(tmp_path):
    result = _run(
        "minecraft_world",
        "index.html",
        _read("minecraft_world", "index.html"),
        tmp_path,
    )
    assert result.final_score == 1.0
    assert result.final_success is True
    assert result.critical_failures == []


def test_minecraft_empty_artifact_scores_zero_and_vetoes(tmp_path):
    result = _run("minecraft_world", "index.html", "", tmp_path)
    assert result.final_score == 0.0
    assert result.final_success is False
    assert any("single_file_html" in item for item in result.critical_failures)


def test_minecraft_wrong_artifact_scores_low(tmp_path):
    result = _run(
        "minecraft_world",
        "index.html",
        "<html><body><h1>Hello world</h1>"
        "<p>This page has no Three.js scene, no voxels and no island.</p>"
        "</body></html>",
        tmp_path,
    )
    assert result.final_score < 0.5
    assert result.final_success is False


def test_minecraft_external_asset_fails_negative_check(tmp_path):
    content = _read("minecraft_world", "index.html").replace(
        "</body>", '<img src="tree.png" alt="tree"></body>'
    )
    result = _run("minecraft_world", "index.html", content, tmp_path)
    assert result.final_score < 1.0
    assert result.final_success is False
    assert any("no_external_assets" in item for item in result.attempts[0].error.split("; "))


def test_web_dashboard_good_artifact_scores_exactly_one(tmp_path):
    result = _run(
        "web_dashboard",
        "index.html",
        _read("web_dashboard", "index.html"),
        tmp_path,
    )
    assert result.final_score == 1.0
    assert result.final_success is True


def test_web_dashboard_empty_artifact_scores_zero(tmp_path):
    result = _run("web_dashboard", "index.html", "", tmp_path)
    assert result.final_score == 0.0
    assert result.final_success is False


def test_email_good_artifact_scores_exactly_one(tmp_path):
    result = _run(
        "email_write",
        "email.txt",
        _read("email_write", "email.txt"),
        tmp_path,
    )
    assert result.final_score == 1.0
    assert result.final_success is True


def test_email_without_subject_vetoes_on_critical_check(tmp_path):
    result = _run(
        "email_write",
        "email.txt",
        "Hello team,\n\nNext step by Friday.\n\nBest regards,\nAlex",
        tmp_path,
    )
    assert result.final_score < 1.0
    assert result.final_success is False
    assert any("has_subject" in item for item in result.critical_failures)


def test_blender_scoring_accepts_valid_artifacts():
    task = SANDBOX_TASKS["blender_skyblock"]
    files = {"build_scene.py": _read("blender_skyblock", "build_scene.py")}
    custom = {
        "blend_runs": (True, "exit=0"),
        "blend_is_binary": (True, "size=2530753"),
        "blend_min_size": (True, "size=2530753"),
        "frames_rendered": (True, "120 frame(s) rendered"),
    }
    score, failing, critical = score_attempt(
        task, files, custom_results=custom, exit_code=0
    )
    assert score == 1.0
    assert failing == []
    assert critical == []


def test_blender_scoring_vetoes_when_command_or_artifacts_fail():
    task = SANDBOX_TASKS["blender_skyblock"]
    files = {"build_scene.py": _read("blender_skyblock", "build_scene.py")}
    custom = {
        "blend_runs": (False, "exit=1"),
        "blend_is_binary": (False, "scene.blend not created"),
        "blend_min_size": (False, "no .blend file"),
        "frames_rendered": (False, "no frames directory"),
    }
    score, failing, critical = score_attempt(
        task, files, custom_results=custom, exit_code=1
    )
    assert score < 0.5
    assert critical
    assert any("blend_runs" in item for item in critical)
    assert any("blend_is_binary" in item for item in critical)


def test_critical_failure_zeroes_an_otherwise_high_score():
    task = SandboxTask(
        id="t",
        kind=SandboxTaskKind.TEXT,
        title="t",
        prompt="p",
        checks=[
            SandboxCheck("ok", "regex", r"present", weight=9.0),
            SandboxCheck("veto", "regex", r"missing", weight=1.0, critical=True),
        ],
        artifacts=("a.txt",),
    )
    score, failing, critical = score_attempt(task, {"a.txt": "present"})
    assert score == 0.0
    assert critical
