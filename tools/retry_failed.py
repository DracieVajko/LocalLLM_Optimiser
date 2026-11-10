"""Retry the failed bakeoff tasks, one model at a time.

Each entry runs a fresh ``lab bakeoff`` process, so the model gate unloads the
previous model before the next one loads. A per-run wall-clock limit stops a
crashed engine from blocking the whole queue.

Usage:
    python tools/retry_failed.py --list
    python tools/retry_failed.py                # run everything
    python tools/retry_failed.py --only bonsai  # substring match on model id
    python tools/retry_failed.py --timeout-min 45
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "results" / "retry"

#: (model id, tasks, extra CLI flags, why)
PLAN: list[tuple[str, str, list[str], str]] = [
    (
        "prism-ml/bonsai-27b",
        "minecraft_world,company_website,email_write",
        ["--safe", "--no-thinking"],
        "kwargs-in-JS and reasoning dump; retry with no-thinking",
    ),
    (
        "qwen3.8-9b-distill",
        "company_website,email_write",
        ["--safe", "--no-thinking"],
        "prose instead of HTML; retry with no-thinking",
    ),
    (
        "google/gemma-4-26b-a4b-qat",
        "email_write,company_website",
        ["--safe", "--no-thinking"],
        "engine 500 on chat; one more attempt",
    ),
    (
        "qwen/qwen3.6-35b-a3b",
        "email_write",
        ["--safe", "--no-thinking"],
        "engine 500 on chat; one more attempt",
    ),
    (
        "qwen3.8-27b-twin-turbo-fable-cold-fusion-709-ultra-heretic-uncensored-nm-dau-neo-mtp",
        "email_write,company_website",
        ["--safe", "--no-thinking"],
        "engine 500 on chat; one more attempt",
    ),
    (
        "openai-gpt-oss-20b-claude-4.5-opus-heretic-uncensored-i1",
        "email_write,company_website,blender_city",
        ["--safe", "--no-thinking"],
        "syntax errors and reasoning dump",
    ),
    (
        "nvidia-nemotron-3.5-bolt-e4b",
        ["--safe", "--no-thinking"],
        "bpy.ops.scene.clear does not exist",
    ),
    (
        "nvidia-nemotron-3.5-bolt-74b-a9b",
        "minecraft_world",
        ["--safe", "--no-thinking"],
        "duplicate generateWorld; slow (about 20 min)",
    ),
]


def _blender_path() -> str:
    for candidate in (
        Path(r"C:\Program Files\Blender Foundation\Blender 5.3"),
        Path(r"C:\Program Files\Blender Foundation\Blender 5.2"),
    ):
        if (candidate / "blender.exe").exists():
            return str(candidate)
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print the plan and exit")
    parser.add_argument("--only", default="", help="substring match on the model id")
    parser.add_argument("--timeout-min", type=float, default=45.0)
    parser.add_argument("--context", default="8192")
    args = parser.parse_args()

    plan = [row for row in PLAN if args.only.lower() in row[0].lower()] if args.only else PLAN
    if args.list:
        for model, tasks, flags, why in plan:
            print(f"{model}\n  tasks: {tasks}\n  flags: {' '.join(flags)}\n  why: {why}\n")
        return 0

    blender = _blender_path()
    if blender:
        import os

        os.environ["PATH"] = blender + os.pathsep + os.environ["PATH"]

    LOGS.mkdir(parents=True, exist_ok=True)
    python = ROOT / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = Path(sys.executable)

    failures = 0
    for index, (model, tasks, flags, why) in enumerate(plan, start=1):
        slug = "".join(c if c.isalnum() else "_" for c in model)[:60]
        log = LOGS / f"{index:02d}_{slug}.log"
        print(f"\n=== [{index}/{len(plan)}] {model} :: {tasks} ({why})", flush=True)
        cmd = [
            str(python),
            "-m",
            "lm_optimizer.cli.main",
            "lab",
            "bakeoff",
            "--models",
            model,
            "--tasks",
            tasks,
            "--context",
            args.context,
            *flags,
        ]
        started = time.perf_counter()
        try:
            with log.open("w", encoding="utf-8") as handle:
                subprocess.run(
                    cmd,
                    cwd=ROOT,
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    timeout=args.timeout_min * 60,
                )
            status = "done"
        except subprocess.TimeoutExpired:
            status = f"TIMEOUT after {args.timeout_min:.0f} min"
            failures += 1
        except Exception as exc:  # noqa: BLE001
            status = f"ERROR {type(exc).__name__}: {exc}"
            failures += 1
        elapsed = time.perf_counter() - started
        stamp = datetime.now().strftime("%H:%M:%S")
        print(f"    {status} in {elapsed / 60:.1f} min -> {log.name} ({stamp})", flush=True)

    print(f"\nfinished with {failures} timeout/error run(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
