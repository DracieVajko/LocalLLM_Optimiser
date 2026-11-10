"""Retry the failed bakeoff tasks, one model at a time.

Each entry runs a fresh ``lab bakeoff`` process, so the model gate unloads the
previous model before the next one loads. A per-run wall-clock limit stops a
crashed engine from blocking the whole queue.

Usage:
    python tools/retry_failed.py --list
    python tools/retry_failed.py --wait-idle       # start only when LM Studio is quiet
    python tools/retry_failed.py --only bonsai     # substring match on model id
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
#: Ordered small/fast first; the 74B is last because it runs at ~0.4 tok/s.
PLAN: list[tuple[str, str, list[str], str]] = [
    (
        "nvidia-nemotron-3.5-bolt-e4b",
        "company_website,blender_city",
        ["--safe", "--no-thinking"],
        "new company-site task and the dense city blend task",
    ),
    (
        "prism-ml/bonsai-27b",
        "company_website,blender_city,minecraft_world",
        ["--safe", "--no-thinking"],
        "reasoning dump; retry with no-thinking",
    ),
    (
        "qwen3.8-9b-distill",
        "company_website,blender_city",
        ["--safe", "--no-thinking"],
        "prose instead of HTML on the old web task",
    ),
    (
        "swift-qwen3.8-27b",
        "company_website,blender_city",
        ["--safe", "--no-thinking"],
        "bracket errors in long Python; new city task",
    ),
    (
        "openai-gpt-oss-20b-claude-4.5-opus-heretic-uncensored-i1",
        "company_website,blender_city",
        ["--safe", "--no-thinking"],
        "syntax errors and reasoning dump",
    ),
    (
        "google/gemma-4-26b-a4b-qat",
        "company_website,blender_city",
        ["--safe", "--no-thinking"],
        "engine 500 on the old run; no-thinking fixed email",
    ),
    (
        "qwen/qwen3.6-35b-a3b",
        "company_website,email_write",
        ["--safe", "--no-thinking"],
        "engine 500 on chat; one more attempt",
    ),
    (
        "qwen3.8-27b-twin-turbo-fable-cold-fusion-709-ultra-heretic-uncensored-nm-dau-neo-mtp",
        "email_write",
        ["--safe", "--no-thinking"],
        "engine 500 on chat; one more attempt",
    ),
    (
        "nvidia-nemotron-3.5-bolt-74b-a9b",
        "company_website",
        ["--safe", "--no-thinking"],
        "0.4 tok/s; one page only, needs the long timeout",
    ),
]

#: A model is only started when the backend has been quiet this long.
IDLE_SETTLE_S = 180.0


def _blender_path() -> str:
    for candidate in (
        Path(r"C:\Program Files\Blender Foundation\Blender 5.3"),
        Path(r"C:\Program Files\Blender Foundation\Blender 5.2"),
    ):
        if (candidate / "blender.exe").exists():
            return str(candidate)
    return ""


def _loaded_models(url: str) -> list[str]:
    import httpx

    try:
        response = httpx.get(f"{url.rstrip('/')}/api/v0/models", timeout=10)
        response.raise_for_status()
    except Exception:  # noqa: BLE001 - a dead server is "not busy" for our purpose
        return []
    return [
        str(model.get("id"))
        for model in response.json().get("data", [])
        if model.get("state") == "loaded"
    ]


def wait_until_idle(url: str, settle_s: float, poll_s: float = 60.0, max_hours: float = 12.0) -> None:
    """Block until no model has been loaded for *settle_s* seconds."""
    quiet_since: float | None = None
    deadline = time.monotonic() + max_hours * 3600
    while time.monotonic() < deadline:
        loaded = _loaded_models(url)
        if loaded:
            quiet_since = None
            print(f"[wait] busy: {', '.join(loaded)}", flush=True)
        else:
            quiet_since = quiet_since or time.monotonic()
            waited = time.monotonic() - quiet_since
            print(f"[wait] idle {waited:.0f}/{settle_s:.0f}s", flush=True)
            if waited >= settle_s:
                print("[wait] LM Studio is idle, starting", flush=True)
                return
        time.sleep(poll_s)
    raise SystemExit("LM Studio did not become idle in time")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print the plan and exit")
    parser.add_argument("--only", default="", help="substring match on the model id")
    parser.add_argument("--timeout-min", type=float, default=45.0)
    parser.add_argument("--context", default="8192")
    parser.add_argument(
        "--wait-idle",
        action="store_true",
        help="wait until LM Studio has no loaded model for 3 minutes first",
    )
    parser.add_argument("--url", default="http://127.0.0.1:1234")
    args = parser.parse_args()

    plan = [row for row in PLAN if args.only.lower() in row[0].lower()] if args.only else PLAN
    if args.list:
        for model, tasks, flags, why in plan:
            print(f"{model}\n  tasks: {tasks}\n  flags: {' '.join(flags)}\n  why: {why}\n")
        return 0

    if args.wait_idle:
        wait_until_idle(args.url, IDLE_SETTLE_S)

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
