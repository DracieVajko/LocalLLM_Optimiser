"""Deterministic self-test for the sandbox task definitions.

Runs in ~1 s, needs no LM Studio, no GPU and no model. It answers one
question: *can the harness tell a correct answer from a wrong one?*

Four checks, each one catches a class of bug found in
`results/DEBUG-REPORT-20261106.md`:

1. ``fixtures``   - score golden fixtures through the real ``score_attempt``
                    path and compare against the expected score. A prose dump
                    scoring > 0.1 or a perfect answer scoring < 0.9 is a bug.
2. ``reachable``  - every regex check that demands a literal must be derivable
                    from the prompt + provided material. Catches "the check
                    wants 10:45 but the prompt never says 45 minutes"
                    and "cite primary_official but the sources were never sent".
3. ``wiring``     - custom validator result names must match task check names.
                    Catches `has_viewport` vs `has_viewport_meta`.
4. ``contract``   - a text-producing task must not declare a binary artifact,
                    and a negated requirement must set ``negate=True``.

Exit code 0 = all green, 1 = at least one finding. Wire this into pytest:

    def test_sandbox_selfcheck():
        import subprocess, sys
        assert subprocess.run(
            [sys.executable, "tools/selfcheck_sandbox.py"], check=False
        ).returncode == 0
"""

from __future__ import annotations

import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lm_optimizer.services.sandbox_lab import (  # noqa: E402
    RESEARCH_PACKAGE,
    SANDBOX_TASKS,
    SandboxTask,
    score_attempt,
)
from lm_optimizer.services.web_validator import validate_web_files  # noqa: E402

FINDINGS: list[str] = []


def finding(kind: str, task: str, detail: str) -> None:
    FINDINGS.append(f"[{kind}] {task}: {detail}")


# --- fixtures --------------------------------------------------------------
# Every fixture is what a model actually returned in results/ (or a correct
# answer). `expect` is the score the harness SHOULD give.

PERFECT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard</title>
<style>
  .grid { display: grid; grid-template-columns: repeat(4, 1fr); }
  @media (max-width: 640px) { .grid { grid-template-columns: 1fr; } }
</style>
</head>
<body data-theme="light">
<h1>Metrics</h1>
<div class="grid"><div>1</div><div>2</div><div>3</div><div>4</div></div>
<select id="filter"><option>all</option></select>
<button id="theme-toggle">dark</button>
<script>
document.getElementById('theme-toggle').addEventListener('click', function () {
  document.body.dataset.theme = 'dark';
});
</script>
</body>
</html>
"""

PERFECT_CALENDAR = json.dumps(
    {
        "title": "Project Kickoff",
        "start": "2026-11-10T10:00:00+01:00",
        "end": "2026-11-10T10:45:00+01:00",
        "attendees": ["alice@example.com", "bob@example.com"],
        "location": "Meet",
    }
)

PERFECT_EMAIL = (
    "Subject: Kickoff follow-up\n\n"
    "Dear Client,\n\n"
    "Thank you for your time at the kickoff. The next step is to send the API\n"
    "draft by 2026-11-07 so we can lock the scope before development starts.\n\n"
    "Best regards,\nAlex Doe\n"
)

PERFECT_BLEND_PY = """
import bpy

def block(x, y, z, name, material):
    bpy.ops.mesh.primitive_cube_add(location=(x, y, z))
    obj = bpy.context.active_object
    obj.name = name
    obj.data.materials.append(bpy.data.materials[material])
    return obj

for m in ("grass", "dirt", "stone", "trunk", "leaves", "chest"):
    bpy.data.materials.new(m)

block(0, 0, 1, "grass_top", "grass")
block(0, 0, 0, "dirt", "dirt")
block(0, 0, -1, "stone", "stone")
block(1, 0, 1, "trunk", "trunk")
block(1, 0, 2, "leaves", "leaves")
block(-1, 0, 1, "chest", "chest")
bpy.ops.object.camera_add(location=(6, -6, 6))
bpy.ops.object.light_add(type="SUN")

cam = bpy.data.objects["Camera"]
cam.keyframe_insert("rotation_euler", frame=1)
cam.keyframe_insert("rotation_euler", frame=120)
scene = bpy.context.scene
scene.frame_start, scene.frame_end = 1, 120
bpy.ops.wm.save_as_mainfile(filepath="scene.blend")
for frame in range(1, 121, 24):
    scene.frame_set(frame)
    scene.render.filepath = f"frames/{frame:04d}.png"
    bpy.ops.render.render(write_still=True)
"""

PERFECT_RESEARCH = (
    "Which load parameters the API accepts: context_length, flash_attention, "
    "offload_kv_cache_to_gpu, eval_batch_size, physical_batch_size, parallel, "
    "context_checkpoints, num_experts and speculative_draft_max_tokens "
    "(primary_official).\n\n"
    "MTP effect on a dense 27B: acceptance ~73% at n=3 drafts, decode throughput "
    "31.2 -> 40.3 tok/s on a V100 (technical_secondary).\n\n"
    "The Q3/Q4 conflict: both community claims (conflicting_source) were "
    "measured on Apple Silicon, where the Q3 kernel is unusually slow, so the "
    "comparison does not resolve on generic hardware. The outdated 17.5 GB "
    "guidance (outdated_source) predates 3-bit quants and KV quantization.\n\n"
    "The irrelevant_source document (BASIC/cassette history) does not bear on "
    "this question and was not used. Nothing in the sources states a VRAM "
    "figure for Q4_K_M on this GPU, so that is not stated here.\n"
)

PERFECT_DEEP = """
Sub-questions
1. How much VRAM does a 70B MoE need at Q4_K_M?
2. What decode speed is realistic on a 24 GB consumer GPU?
3. Does CPU offloading change feasibility?

Search strategies
1. "70B MoE Q4_K_M VRAM requirement"
2. "Mixtral 8x7B llama.cpp tokens per second RTX 3090"
3. "llama.cpp --n-gpu-layers offload benchmark"

Source quality criteria
Prefer primary project docs and papers; independent measurement over
anecdote; require a stated GPU, driver and parameters.

Resolving conflicts
Prefer measured empirical benchmarks over theoretical estimates; test the most
aggressive quant first and document the trade-off; verify hardware and params.

Preliminary synthesis
At Q4_K_M a 70B MoE weights file is roughly 35-40 GB, so 24 GB cannot hold it;
it runs only with heavy CPU offload, and decode speed falls with the number of
offloaded layers. Feasible, not comfortable.
"""

PERFECT_WEB_FETCH = json.dumps(
    {
        "tool": "web_fetch",
        "url": "https://www.nvidia.com/en-us/geforce/graphics-cards/rtx-3060/",
        "title": "GeForce RTX 3060",
        "facts": ["6 GB GDDR6 memory", "Laptop variants ship with 6 GB"],
        "citation": "nvidia.com/en-us/geforce/graphics-cards/rtx-3060/",
    }
)

PERFECT_WEB_SEARCH = """```python
import requests
from bs4 import BeautifulSoup

QUERIES = [
    "RTX 3060 Laptop GPU 6 GB VRAM local LLM inference",
    "llama.cpp offload 6GB VRAM tokens per second",
    "Q4_K_M 7B model VRAM requirement",
]
HEADERS = {"User-Agent": "Mozilla/5.0 (research script)"}

def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return r.text
    except Exception as exc:
        print(f"fetch failed: {exc}")
        return ""

def extract(html):
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(" ", strip=True)

if __name__ == "__main__":
    findings = []
    for q in QUERIES:
        page = fetch("https://example.invalid/search?q=" + q.replace(" ", "+"))
        if page:
            findings.append(extract(page)[:200])
    print("summary:", findings)
```
"""

#: (task_id, fixture name, file the fixture is materialised as, content, expected)
FIXTURES: list[tuple[str, str, str, str, tuple[float, float]]] = [
    ("web_dashboard", "perfect_html", "index.html", PERFECT_HTML, (0.9, 1.0)),
    ("web_dashboard", "prose_dump", "index.html",
     "The user wants a self-contained HTML dashboard with 4 metrics, a filter, "
     "a model detail view and a light/dark theme toggle. Previous failures: "
     "missing viewport meta tag, missing media queries. So I must include "
     '<meta name="viewport" content="width=device-width, initial-scale=1"> and '
     "CSS @media queries. I will use a grid layout.", (0.0, 0.1)),
    ("web_dashboard", "empty", "index.html", "", (0.0, 0.05)),
    ("calendar_event", "perfect_json", "calendar.json", PERFECT_CALENDAR, (0.95, 1.0)),
    ("calendar_event", "fenced_json", "calendar.json",
     "```json\n" + PERFECT_CALENDAR + "\n```", (0.95, 1.0)),
    ("calendar_event", "prose_json", "calendar.json",
     "Here is the event you asked for:\n" + PERFECT_CALENDAR, (0.95, 1.0)),
    ("email_write", "perfect_email", "email.txt", PERFECT_EMAIL, (0.95, 1.0)),
    ("email_write", "placeholder_email", "email.txt",
     PERFECT_EMAIL.replace("Alex Doe", "[Your Name]"), (0.0, 0.80)),
    ("blender_skyblock", "perfect_script", "scene.blend", PERFECT_BLEND_PY, (0.0, 0.2)),
    ("blender_skyblock", "prose_dump", "scene.blend",
     "We need answer user's request. Need produce Blender Python script. "
     "bpy.ops.mesh is the cube op; keyframe_insert on the camera; "
     "save_as_mainfile at the end; frame_start=1 frame_end=120; "
     "grass tree chest camera light render.", (0.0, 0.2)),
    ("research_synthesis", "perfect_answer", "output.txt", PERFECT_RESEARCH, (0.9, 1.0)),
    ("deep_research", "perfect_plan", "deep_research.txt", PERFECT_DEEP, (0.9, 1.0)),
    ("web_fetch_brief", "perfect_json", "web_fetch.json", PERFECT_WEB_FETCH, (0.95, 1.0)),
    ("web_fetch_brief", "fenced_json", "web_fetch.json",
     "```json\n" + PERFECT_WEB_FETCH + "\n```", (0.95, 1.0)),
    ("web_search", "perfect_script", "web_search.py", PERFECT_WEB_SEARCH, (0.95, 1.0)),
]


def score_fixture(task: SandboxTask, files: dict[str, str]) -> float:
    custom = None
    if task.kind.value == "web":
        custom = {
            c.name: (c.passed, c.detail) for c in validate_web_files(files)
        }
    score, _failing, _critical = score_attempt(task, files, custom_results=custom)
    return score


def check_fixtures() -> None:
    print("1. fixtures — can the harness score a known answer correctly?")
    rows = []
    for task_id, name, filename, content, (low, high) in FIXTURES:
        task = SANDBOX_TASKS[task_id]
        got = score_fixture(task, {filename: content})
        ok = low <= got <= high
        rows.append((task_id, name, got, low, high, ok))
        if not ok:
            finding(
                "fixtures",
                task_id,
                f"{name}: scored {got:.2f}, expected {low:.2f}..{high:.2f}",
            )
    width = max(len(n) for _t, n, *_ in rows)
    for task_id, name, got, low, high, ok in rows:
        print(
            f"   {'PASS' if ok else 'FAIL'}  {task_id:<20s} {name:<{width}s} "
            f"score={got:.2f}  want {low:.2f}-{high:.2f}"
        )


# --- reachability ----------------------------------------------------------

#: Words a prompt may use to make a literal derivable.
_DERIVABLE_HINTS = {
    "10:45": ("45", "forty-five", "three quarters"),
    "11:00": ("60", "one hour", "sixty"),
}

#: Tokens that must be reproduced verbatim: dates, times, quantities.
_DATA_TOKEN_RE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}")


def _literals(pattern: str) -> list[str]:
    """Data literals a check demands the model to reproduce.

    Vocabulary a model is *supposed* to invent ("Dear", "grid", "grass") is
    ignored on purpose - only data can be unreachable.
    """
    rough = re.sub(r"\\[sSdDwWbB.^$*+?(){}|]", " ", pattern)
    return sorted(set(_DATA_TOKEN_RE.findall(rough)))


def _prompt_haystack(task: SandboxTask) -> str:
    return task.prompt.lower()


def check_reachable() -> None:
    print("\n2. reachable — is every date/time a check demands actually provided?")
    for task_id, task in sorted(SANDBOX_TASKS.items()):
        haystack = _prompt_haystack(task)
        for check in task.checks:
            if check.kind != "regex" or check.negate:
                continue
            for literal in _literals(str(check.value or "")):
                if literal.lower() in haystack:
                    continue
                hints = _DERIVABLE_HINTS.get(literal, ())
                if any(h.lower() in haystack for h in hints):
                    continue
                finding(
                    "reachable",
                    task_id,
                    f"check {check.name!r} requires {literal!r} but the prompt "
                    "never supplies or implies it",
                )
                print(
                    f"   FAIL  {task_id:<20s} {check.name:<22s} "
                    f"unreachable literal {literal!r}"
                )


# --- wiring ----------------------------------------------------------------


def check_wiring() -> None:
    print("\n3. wiring — do custom validator names match task check names?")
    empty = {"index.html": ""}
    validator_names = {c.name for c in validate_web_files(empty)}
    for task in SANDBOX_TASKS.values():
        if task.kind.value != "web":
            continue
        task_names = {c.name for c in task.checks}
        orphan_validator = validator_names - task_names
        no_source = task_names - validator_names
        for name in sorted(orphan_validator):
            finding(
                "wiring",
                task.id,
                f"validator emits {name!r} but no task check consumes it "
                "(the result is computed then discarded)",
            )
            print(f"   FAIL  {task.id:<20s} discarded validator check {name!r}")
        for name in sorted(no_source):
            if name in {"no_external_scripts", "no_external_styles"}:
                continue  # produced by validate_web_files under the same name
            finding(
                "wiring",
                task.id,
                f"task check {name!r} has no custom validator result, so it "
                "falls back to a regex over the whole (prose) file",
            )
            print(f"   FAIL  {task.id:<20s} no validator for check {name!r}")


# --- contract --------------------------------------------------------------

TEXT_EXTENSIONS = {".txt", ".md", ".json", ".html", ".htm", ".py", ".csv"}
BINARY_EXTENSIONS = {".blend", ".exe", ".png", ".jpg", ".zip", ".glb", ".fbx"}


def check_contract() -> None:
    print("\n4. contract — can the declared artifact be produced by text output?")
    for task_id, task in sorted(SANDBOX_TASKS.items()):
        if task.artifacts:
            first = task.artifacts[0]
            suffix = Path(first.rstrip("/")).suffix.lower()
            if suffix in BINARY_EXTENSIONS:
                finding(
                    "contract",
                    task_id,
                    f"primary artifact {first!r} is a binary type, but the "
                    "runner writes the model's text into artifacts[0] "
                    "(sandbox_runner.py:294) — the file can never be valid",
                )
                print(
                    f"   FAIL  {task_id:<20s} text written into {first!r}"
                )
        for check in task.checks:
            if check.name.startswith("no_") and not check.negate:
                finding(
                    "contract",
                    task_id,
                    f"check {check.name!r} is named 'no_*' but negate=False, so "
                    "it only passes when the forbidden thing is present",
                )
                print(f"   FAIL  {task_id:<20s} inverted check {check.name!r}")


def check_prompt_material() -> None:
    print("\n5. material — does a task that says 'provided documents' provide them?")
    for task_id, task in sorted(SANDBOX_TASKS.items()):
        said = "provided source documents" in task.prompt.lower()
        gave = any(key in task.prompt for key in RESEARCH_PACKAGE)
        if said and not gave:
            finding(
                "material",
                task_id,
                "prompt says 'Using only the provided source documents' but no "
                "document text is included",
            )
            print(f"   FAIL  {task_id:<20s} references documents that are never sent")


def check_critical() -> None:
    print("\n6. critical — is an explicit 'only'/'no X' a hard gate?")
    for task_id, task in sorted(SANDBOX_TASKS.items()):
        prompt = task.prompt.lower()
        strict = ("only" in prompt) or ("no placeholders" in prompt)
        if not strict:
            continue
        negated = [c for c in task.checks if c.negate]
        if not negated or any(c.critical for c in negated):
            continue
        names = ", ".join(repr(c.name) for c in negated)
        finding(
            "critical",
            task_id,
            f"the prompt demands strict output, but {names} is not critical: an "
            "instruction violation only costs partial credit (email_write scores "
            "0.73 with a [Your Name] placeholder left in)",
        )
        print(f"   FAIL  {task_id:<20s} negated check is not a hard gate: {names}")


def main() -> int:
    buf = io.StringIO()
    with redirect_stdout(buf):
        check_fixtures()
        check_reachable()
        check_wiring()
        check_contract()
        check_prompt_material()
        check_critical()
    output = buf.getvalue()
    print(output)
    print("=" * 78)
    if FINDINGS:
        print(f"{len(FINDINGS)} finding(s):\n")
        for item in FINDINGS:
            print(f"  - {item}")
        print(
            "\nThese are harness defects, not model failures. Fix them before "
            "trusting any sandbox score."
        )
        return 1
    print("all checks green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
