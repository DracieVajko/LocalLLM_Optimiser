"""Export the exact sandbox prompts so a human can paste them into any chat UI.

Writes one text file per task into ``benchmarks/compare/prompts/`` (tracked) and,
with ``--desktop``, a copy of the whole bundle to the Desktop.

Usage:
    python tools/export_prompts.py
    python tools/export_prompts.py --desktop
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lm_optimizer.services.sandbox_lab import SANDBOX_TASKS  # noqa: E402

COMPARE = ROOT / "benchmarks" / "compare"
PROMPTS = COMPARE / "prompts"

TASKS = (
    "email_write",
    "minecraft_world",
    "company_website",
    "deep_research_report",
    "blender_city",
)

DESKTOP = Path.home() / "Desktop" / "frontier_bench"


def export_prompts() -> list[str]:
    PROMPTS.mkdir(parents=True, exist_ok=True)
    written = []
    for task_id in TASKS:
        task = SANDBOX_TASKS[task_id]
        path = PROMPTS / f"{task_id}.txt"
        path.write_text(task.prompt.rstrip() + "\n", encoding="utf-8")
        written.append(task_id)
    # A renamed task must not leave its old prompt behind for someone to paste.
    for stale in PROMPTS.glob("*.txt"):
        if stale.stem not in TASKS:
            stale.unlink()
    (PROMPTS / "index.json").write_text(
        json.dumps(
            {
                task_id: {
                    "artifact": SANDBOX_TASKS[task_id].artifacts[0],
                    "prompt_file": f"{task_id}.txt",
                    "title": SANDBOX_TASKS[task_id].title,
                }
                for task_id in TASKS
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return written


def build_prompt_sheet() -> Path:
    """One page with every prompt in a copy-paste block, for a chat UI."""
    lines = [
        "# All frontier prompts",
        "",
        "Paste one prompt per conversation. Do not add follow-ups, do not ask for",
        "a different design. Save each answer with the importer below.",
        "",
    ]
    for task_id in TASKS:
        task = SANDBOX_TASKS[task_id]
        artifact = task.artifacts[0]
        lines += [
            f"## {task_id}",
            "",
            f"Save the answer as `{artifact}` via:",
            "",
            "```powershell",
            f"python tools/compare_models.py --provider chatgpt --task {task_id} --clipboard",
            "```",
            "",
            "Prompt:",
            "",
            "```text",
            task.prompt.rstrip(),
            "```",
            "",
        ]
    path = COMPARE / "PROMPTS_ALL.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def build_desktop_bundle() -> Path:
    if DESKTOP.exists():
        shutil.rmtree(DESKTOP)
    (DESKTOP / "prompts").mkdir(parents=True)
    (DESKTOP / "reference_deepseek").mkdir(parents=True)

    for task_id in TASKS:
        shutil.copyfile(PROMPTS / f"{task_id}.txt", DESKTOP / "prompts" / f"{task_id}.txt")

    sheet = build_prompt_sheet()
    shutil.copyfile(sheet, DESKTOP / "PROMPTS_ALL.md")

    reference = COMPARE / "deepseek"
    for task_id in TASKS:
        artifact = SANDBOX_TASKS[task_id].artifacts[0]
        source = reference / task_id / artifact
        if source.exists():
            target = DESKTOP / "reference_deepseek" / task_id
            target.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target / artifact)

    (DESKTOP / "README.md").write_text(README_TEXT, encoding="utf-8")
    return DESKTOP


README_TEXT = """# Frontier test bundle

Same tasks, same prompts that the local models get. Run each one in ChatGPT
(or Gemini, Perplexity, Odysseus), then import the answer so it can be scored
and screenshotted next to the local models.

## 1. Run a task

Open `prompts/<task>.txt`, copy **all** of it, paste into the assistant.
No extra instructions, no follow-up messages.

| Task | What you should get back |
|---|---|
| `email_write` | plain text email (no code fence needed) |
| `minecraft_world` | one HTML file in a ```html fence |
| `company_website` | one HTML file |
| `deep_research_report` | one HTML report |
| `blender_city` | a Python script in a ```python fence |

## 2. Import the answer

Copy the assistant's whole answer, then run (in the repo):

```powershell
python tools/compare_models.py --provider chatgpt --task minecraft_world --clipboard
```

Markdown fences are stripped automatically. If the answer is already a file:

```powershell
python tools/compare_models.py --provider chatgpt --task minecraft_world --file C:\\path\\answer.html
```

## 3. Score and render everything

```powershell
$env:PATH += ";C:\\Program Files\\Blender Foundation\\Blender 5.3"
python tools/compare_models.py --tasks all --include-bakeoff
```

Then open `results/compare/gallery.html`.

## Reference

`reference_deepseek/` holds the DeepSeek artifacts that score 1.0, so you can
see what a full-marks answer looks like for each task. They are committed in
`benchmarks/compare/deepseek/` in the repo.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop", action="store_true", help="also build the Desktop bundle")
    args = parser.parse_args()

    written = export_prompts()
    print(f"prompts: {', '.join(written)} -> {PROMPTS}")
    if args.desktop:
        target = build_desktop_bundle()
        print(f"desktop bundle: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
