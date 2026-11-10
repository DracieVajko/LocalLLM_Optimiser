"""Static audit of every sandbox task: are the checks real and aligned?

Flags:
* a custom check the runner never computes (a check that can only fail),
* a task without any critical check,
* a negative-only task (everything passes on an empty file),
* duplicate check names,
* an artifact list that does not include the file the checks read,
* a prompt keyword that no check measures.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lm_optimizer.services.sandbox_lab import SANDBOX_TASKS  # noqa: E402

#: Custom checks the runner / host can actually fill.
COMPUTED = {
    "blend_runs",
    "blend_is_binary",
    "blend_min_size",
    "blend_has_objects",
    "blend_has_camera",
    "blend_has_light",
    "blend_materials",
    "blend_animation",
    "frames_rendered",
    "preview_rendered",
    "is_python_code",
    "html_document",
    "js_parses",
    "renders_content",
}

PROMPT_HINTS = {
    "viewport": r"viewport",
    "media query": r"@media|responsive|mobile",
    "hero": r"hero|headline",
    "contact": r"contact|form",
    "footer": r"footer",
    "testimonial": r"testimonial|quote",
    "services": r"services",
    "about": r"about",
    "three.js": r"three",
    "camera": r"camera",
    "blend": r"scene\.blend|\.blend",
    "frames": r"frames|animation",
    "subject": r"subject",
    "greeting": r"greeting|dear|hello",
    "closing": r"closing|regards",
}


def main() -> int:
    problems = 0
    for task_id, task in SANDBOX_TASKS.items():
        names = [check.name for check in task.checks]
        print(f"\n=== {task_id}  ({task.kind.value}, {len(task.checks)} checks)")
        print(f"    prompt: {task.prompt[:120].replace(chr(10), ' ')}...")
        print(f"    artifacts: {task.artifacts}")
        print(f"    critical: {[c.name for c in task.checks if c.critical] or 'NONE'}")

        if len(names) != len(set(names)):
            print("    !! duplicate check names")
            problems += 1
        if not any(check.critical for check in task.checks):
            print("    !! no critical check")
            problems += 1
        if all(check.negate for check in task.checks):
            print("    !! negative-only checks (empty file passes)")
            problems += 1
        for check in task.checks:
            if check.kind == "custom" and check.name not in COMPUTED:
                print(f"    !! custom check '{check.name}' is never computed by the runner")
                problems += 1
            if check.weight <= 0:
                print(f"    !! check '{check.name}' has weight {check.weight}")
                problems += 1
        if any(name.endswith(".html") for name in names) or any(
            "html" in name for name in names
        ):
            if "index.html" not in task.artifacts and task.artifacts:
                print("    !! HTML checks but index.html is not an artifact")
                problems += 1

        prompt = task.prompt.lower()
        measured = " ".join(names).lower()
        for label, pattern in PROMPT_HINTS.items():
            if re.search(pattern, prompt) and not re.search(
                pattern.split("|")[0], measured
            ):
                print(f"    .. prompt mentions {label!r}, no check name matches")
        for check in task.checks:
            flag = "critical" if check.critical else ""
            value = f"'{check.value}'" if check.value not in (None, "") else ""
            negate = " negate" if check.negate else ""
            print(
                f"      - {check.name:28} {check.kind:8} w={check.weight:<4} {flag}{negate} {value}"
            )

    print(f"\n{problems} structural problem(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
