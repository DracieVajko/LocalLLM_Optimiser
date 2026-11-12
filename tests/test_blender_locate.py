"""Blender executable discovery for sandbox execution.

The blender task commands were hardcoded to ``blender``, which is not on PATH
on most Windows machines - every blender_city attempt died with exit 1
"'blender' is not recognized". Discovery lives in a service module so the
sandbox and ``tools/preview_blender.py`` agree on what is runnable.
"""

from __future__ import annotations

from pathlib import Path

from lm_optimizer.services import blender_locate
from lm_optimizer.services.sandbox_lab import SandboxPolicy, SANDBOX_TASKS
from lm_optimizer.services.sandbox_runner import build_command_for


def test_env_var_wins(tmp_path, monkeypatch):
    exe = tmp_path / "blender.exe"
    exe.write_bytes(b"")
    monkeypatch.setenv("BLENDER_PATH", str(exe))
    assert blender_locate.find_blender() == str(exe)


def test_command_quotes_a_path_with_spaces(tmp_path, monkeypatch):
    monkeypatch.setattr(
        blender_locate, "find_blender", lambda: "C:/Program Files/Blender/blender.exe"
    )
    command = build_command_for(SANDBOX_TASKS["blender_city"])
    assert command.startswith('"C:/Program Files/Blender/blender.exe"')
    assert command.endswith("--background --python build_scene.py")


def test_no_blender_means_no_command(tmp_path, monkeypatch):
    monkeypatch.setattr(blender_locate, "find_blender", lambda: None)
    assert build_command_for(SANDBOX_TASKS["blender_city"]) == ""


def test_quoted_executable_passes_the_allowlist(tmp_path):
    policy = SandboxPolicy(workdir=tmp_path, allowed_executables=("blender",))
    command = (
        '"C:/Program Files/Blender/blender.exe" --background --python build_scene.py'
    )
    assert policy.is_command_allowed(command)


def test_web_tasks_stay_command_free():
    assert build_command_for(SANDBOX_TASKS["company_website"]) == ""
