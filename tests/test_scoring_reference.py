"""Scoring reference tests: known-good artifacts must score 1.0, known-bad low.

These tests are the reference point for the sandbox scoring system. They use
the committed frontier artifacts as the "good" side and tiny synthetic files
as the "bad" side, so a regression in weights, critical checks or negations
shows up immediately.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path


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


def test_minecraft_empty_artifact_is_not_measured(tmp_path):
    """An empty completion must never be reported as a 0.00 quality result."""
    result = _run("minecraft_world", "index.html", "", tmp_path)
    assert result.status == "not_measured"
    assert result.final_success is False
    assert result.attempts == []


def test_minecraft_prose_artifact_is_vetoed(tmp_path):
    result = _run(
        "minecraft_world",
        "index.html",
        "Here is how I would build the scene: create a box, add a camera, done.",
        tmp_path,
    )
    assert result.final_score == 0.0
    assert result.final_success is False
    assert any("html_document" in item for item in result.critical_failures)


def test_minecraft_wrong_artifact_scores_low(tmp_path):
    result = _run(
        "minecraft_world",
        "index.html",
        "<html><body><h1>Hello world</h1>"
        "<p>This page has no Three.js scene, no voxels and no island.</p>"
        "</body></html>",
        tmp_path,
    )
    assert result.final_score < 0.6
    assert result.final_success is False


def test_minecraft_external_asset_fails_negative_check(tmp_path):
    content = _read("minecraft_world", "index.html").replace(
        "</body>", '<img src="tree.png" alt="tree"></body>'
    )
    result = _run("minecraft_world", "index.html", content, tmp_path)
    assert result.final_score < 1.0
    assert result.final_success is False
    assert any("no_external_assets" in item for item in result.attempts[0].error.split("; "))


def test_company_website_good_artifact_scores_exactly_one(tmp_path):
    result = _run(
        "company_website",
        "index.html",
        _read("company_website", "index.html"),
        tmp_path,
    )
    assert result.final_score == 1.0
    assert result.final_success is True


def test_company_website_empty_artifact_scores_zero(tmp_path):
    result = _run("company_website", "index.html", "", tmp_path)
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
        "## Summary\n\n"
        "Alice asked for a faster dashboard and a fix for the broken export "
        "feature. Bob agreed to prioritize both and schedule a demo for next "
        "Friday. Alice also requested an updated timeline, which Bob will send "
        "by Wednesday.\n\n"
        "## Email\n\n"
        "Hello Alice,\n\n"
        "Thank you for the productive kickoff. The next step is to confirm the "
        "dashboard scope and the export fix, and I will send the updated "
        "timeline by Wednesday, 12 November 2026.\n\n"
        "Best regards,\nBob\n",
        tmp_path,
    )
    assert result.final_score < 1.0
    assert result.final_success is False
    assert any("has_subject" in item for item in result.critical_failures)


def test_email_without_summary_vetoes_on_critical_check(tmp_path):
    result = _run(
        "email_write",
        "email.txt",
        "## Email\n\n"
        "Subject: Dashboard priorities and next steps\n\n"
        "Hello Alice,\n\n"
        "The next step is to send the updated timeline by Wednesday.\n\n"
        "Best regards,\nBob\n",
        tmp_path,
    )
    assert result.final_score < 1.0
    assert result.final_success is False
    assert any("has_summary" in item for item in result.critical_failures)


def test_email_without_email_section_vetoes_on_critical_check(tmp_path):
    result = _run(
        "email_write",
        "email.txt",
        "## Summary\n\n"
        "Alice asked for a faster dashboard and a fix for the broken export "
        "feature. Bob agreed to prioritize both and schedule a demo for next "
        "Friday. Alice also requested an updated timeline, which Bob will send "
        "by Wednesday.\n",
        tmp_path,
    )
    assert result.final_score < 1.0
    assert result.final_success is False
    assert any("has_email" in item for item in result.critical_failures)


def test_email_short_output_fails_word_checks(tmp_path):
    result = _run(
        "email_write",
        "email.txt",
        "## Summary\n\n"
        "Too short to meet the word count.\n\n"
        "## Email\n\n"
        "Subject: Hello\n\n"
        "Hi Alice,\n\n"
        "Best regards,\nBob\n",
        tmp_path,
    )
    assert result.final_score < 1.0
    assert result.final_success is False
    failing = result.attempts[-1].failing_checks
    assert any("summary_min_words" in item for item in failing)
    assert any("email_min_words" in item for item in failing)


def test_blender_scoring_accepts_valid_artifacts():
    task = SANDBOX_TASKS["blender_city"]
    files = {"build_scene.py": _read("blender_city", "build_scene.py")}
    custom = {
        "blend_runs": (True, "exit=0"),
        "blend_is_binary": (True, "size=900000"),
        "blend_min_size": (True, "size=900000"),
        "blend_has_camera": (True, "cameras=1"),
        "blend_has_light": (True, "lights=1"),
        "city_mesh_count": (True, "meshes=80 (min 60), vertices=900"),
        "city_height_variety": (True, "tall(>=15m)=6, max=31.2m"),
        "city_footprint": (True, "size=[48.0, 48.0, 32.0]"),
    }
    score, failing, critical = score_attempt(
        task, files, custom_results=custom, exit_code=0
    )
    assert score == 1.0
    assert failing == []
    assert critical == []


def test_blender_scoring_vetoes_when_command_or_artifacts_fail():
    task = SANDBOX_TASKS["blender_city"]
    files = {"build_scene.py": _read("blender_city", "build_scene.py")}
    custom = {
        "blend_runs": (False, "exit=1"),
        "blend_is_binary": (False, "scene.blend not created"),
        "blend_min_size": (False, "no .blend file"),
        "city_mesh_count": (False, "meshes=0"),
    }
    score, failing, critical = score_attempt(
        task, files, custom_results=custom, exit_code=1
    )
    assert score < 0.5
    assert critical
    critical_names = [check.name for check in critical]
    assert "blend_runs" in critical_names
    assert "blend_is_binary" in critical_names


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
