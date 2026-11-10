"""Tests for the cross-provider comparison helper."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _load() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "tools" / "compare_models.py"
    spec = importlib.util.spec_from_file_location("compare_models_tool", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


compare = _load()


@pytest.mark.parametrize(
    "raw",
    [
        "```html\n<!DOCTYPE html>\n<html></html>\n```",
        "Here you go:\n\n```html\n<!DOCTYPE html>\n<html></html>\n```\nEnjoy!",
        "```\n<!DOCTYPE html>\n<html></html>\n```",
    ],
)
def test_clean_output_strips_fences(raw: str) -> None:
    assert compare.clean_output(raw).strip() == "<!DOCTYPE html>\n<html></html>"


def test_clean_output_keeps_plain_text() -> None:
    assert compare.clean_output("Subject: hi\n\nBody.\n") == "Subject: hi\n\nBody.\n"


def test_import_output_writes_expected_artifact(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(compare, "PROVIDERS_DIR", tmp_path)
    answer = tmp_path / "answer.md"
    answer.write_text("```python\nprint('hi')\n```", encoding="utf-8")

    written = compare.import_output("ChatGPT", "blender_city", answer, False)

    assert written == tmp_path / "ChatGPT" / "blender_city" / "build_scene.py"
    assert written.read_text(encoding="utf-8") == "print('hi')\n"


def test_import_output_requires_input(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(compare, "PROVIDERS_DIR", tmp_path)
    with pytest.raises(SystemExit):
        compare.import_output("x", "email_write", None, False)


def test_discover_bakeoff_picks_newest_artifact(tmp_path: Path) -> None:
    task_dir = tmp_path / "model-a" / "minecraft_world"
    (task_dir / "20260101_000000").mkdir(parents=True)
    (task_dir / "20260102_000000").mkdir(parents=True)
    (task_dir / "20260101_000000" / "index.html").write_text("old", encoding="utf-8")
    (task_dir / "20260102_000000" / "index.html").write_text("new", encoding="utf-8")

    found = list(compare.discover_bakeoff(tmp_path))

    assert len(found) == 1
    provider, task, artifact = found[0]
    assert (provider, task) == ("model-a", "minecraft_world")
    assert artifact.read_text(encoding="utf-8") == "new"


def test_discover_bakeoff_skips_runs_without_artifact(tmp_path: Path) -> None:
    task_dir = tmp_path / "model-a" / "blender_city"
    (task_dir / "20260101_000000").mkdir(parents=True)
    (task_dir / "20260101_000000" / "scene.blend").write_text("x", encoding="utf-8")

    assert list(compare.discover_bakeoff(tmp_path)) == []


def test_discover_ignores_unknown_directories(tmp_path: Path) -> None:
    (tmp_path / "chatgpt" / "minecraft_world").mkdir(parents=True)
    (tmp_path / "chatgpt" / "minecraft_world" / "index.html").write_text("x", encoding="utf-8")
    (tmp_path / "chatgpt" / "notes").mkdir()
    (tmp_path / "chatgpt" / "notes" / "index.html").write_text("x", encoding="utf-8")

    found = list(compare.discover(tmp_path))

    expected = tmp_path / "chatgpt" / "minecraft_world" / "index.html"
    assert found == [("chatgpt", "minecraft_world", expected)]
