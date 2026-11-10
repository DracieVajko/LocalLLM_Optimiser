"""The exported prompt files must match the sandbox task prompts exactly."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]


def _load() -> ModuleType:
    path = ROOT / "tools" / "export_prompts.py"
    spec = importlib.util.spec_from_file_location("export_prompts_tool", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


export = _load()

from lm_optimizer.services.sandbox_lab import SANDBOX_TASKS  # noqa: E402


def test_exported_prompts_match_task_definitions(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(export, "PROMPTS", tmp_path)

    written = export.export_prompts()

    assert written
    for task_id in written:
        text = (tmp_path / f"{task_id}.txt").read_text(encoding="utf-8")
        assert text.strip() == SANDBOX_TASKS[task_id].prompt.strip()


def test_committed_prompts_are_in_sync(monkeypatch) -> None:
    committed = ROOT / "benchmarks" / "compare" / "prompts"
    if not committed.exists():
        return
    for task_id in export.TASKS:
        path = committed / f"{task_id}.txt"
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").strip()
        assert text == SANDBOX_TASKS[task_id].prompt.strip(), (
            f"{task_id} prompt drifted; run python tools/export_prompts.py"
        )
