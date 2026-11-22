"""WP-1: repair feedback must never leak the answer.

For every task in ``sandbox_lab`` and the vision manifest, building the
feedback for every check failing must not contain the check name, the check
value, or any digit/word from the task's expected text.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from lm_optimizer.services.sandbox_lab import SANDBOX_TASKS, SandboxCheck, build_repair_feedback

ROOT = Path(__file__).resolve().parents[1]
VISION_ROOT = ROOT / "benchmarks" / "vision"


def _vision_expected() -> dict[str, str]:
    manifest = json.loads((VISION_ROOT / "manifest.json").read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for item in manifest.get("images", []):
        out[f"vision_{item['id']}"] = str(item.get("expected", ""))
    return out


def test_repair_feedback_no_leak():
    expected_by_task = _vision_expected()

    for task_id, task in SANDBOX_TASKS.items():
        for check in task.checks:
            feedback = build_repair_feedback(task, attempt=1, failing_checks=[check])

            # Never the check name.
            assert check.name not in feedback, f"{task_id}/{check.name}: name leaked"

            # Never the raw check value (regex text, expected counts, ...).
            if check.value is not None:
                val_str = str(check.value)
                if val_str:
                    assert val_str not in feedback, (
                        f"{task_id}/{check.name}: value leaked ({val_str!r})"
                    )

            # For vision tasks, no digit or word from the expected text.
            expected = expected_by_task.get(task_id, "")
            if expected:
                # digits
                for digit in set(re.findall(r"\d{2,}", expected)):
                    assert digit not in feedback, (
                        f"{task_id}/{check.name}: digit {digit!r} from expected leaked"
                    )
                # words (length >= 4, to avoid noise from short connectors)
                for word in set(re.findall(r"[A-Za-z]{4,}", expected)):
                    assert word.lower() not in feedback.lower(), (
                        f"{task_id}/{check.name}: word {word!r} from expected leaked"
                    )