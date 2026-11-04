"""Night run: full treatment for both Swift 27B variants (dense).

Flint was dropped from LM Studio's inventory (its GGUF file remains, but the
server no longer lists it and every chat timed out), so the two remaining
untested models are the Swift Q2_K and Q4_K_S variants.

Per model: quality optimize at 4096 -> save LM Studio default -> benchmark
-> all nine sandbox tasks. Every step is bounded; a failure continues.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

LOG = Path("logs/night_swift.log")
LOG.parent.mkdir(parents=True, exist_ok=True)

MODELS = [
    "swift-qwen3.8-27b@q2_k",
    "swift-qwen3.8-27b@q4_k_s",
]
#: Default list; optional CLI args select a subset (used by the watcher).
DEFAULT_MODELS = MODELS

SANDBOX_TASKS = [
    "web_dashboard",
    "research_synthesis",
    "blender_skyblock",
    "email_write",
    "calendar_event",
    "email_and_calendar",
    "web_fetch_brief",
    "web_search",
    "deep_research",
]


def log(message: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def cli(args: list[str], timeout: int) -> int:
    cmd = [sys.executable, "-m", "lm_optimizer.cli.main", *args]
    log("RUN " + " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        log("TIMEOUT after %ss" % timeout)
        return 124
    log((result.stdout or "")[-6000:])
    if result.stderr:
        log("STDERR: " + (result.stderr or "")[-2000:])
    log(f"EXIT {result.returncode}")
    return result.returncode


def winner(model: str, since: datetime | None = None):
    from lm_optimizer.database.repositories import run_repo

    for summary in run_repo.get_by_model(model, limit=10):
        if summary.status.value not in ("success", "completed", "partial_success"):
            continue
        if since is not None and summary.created_at < since:
            continue
        full = run_repo.get(str(summary.id))
        best = full.get_best_config() if full else None
        if best is not None:
            return full, best
    return None, None


def main() -> int:
    models = sys.argv[1:] or DEFAULT_MODELS
    log("===== Night Swift run started =====")
    log("models: " + ", ".join(models))
    for model in models:
        run_started = datetime.now()
        log(f"===== {model} =====")
        cli(
            [
                "optimize",
                model,
                "--profile",
                "quality",
                "--quality-only",
                "--quality",
                "0.9",
                "--quality-context",
                "4096",
                "--max-context",
                "4096",
                "--min-context",
                "4096",
                "--repetitions",
                "1",
                "--validation-repetitions-max",
                "2",
                "--warmup-runs",
                "0",
                "--min-generation-tok-s",
                "0.5",
                "--skip-phases",
                "speed,context_speed,recovery,validation,context",
                "--non-interactive",
                "--yes",
                "--no-enable-rope",
                "--no-enable-cpu-moe",
                "--no-enable-speculative",
            ],
            timeout=14_400,
        )
        run, best = winner(model, since=run_started)
        if run is not None and best is not None:
            ctx = int(best.context_length or 4096)
            log(f"winner run={run.id} ctx={ctx} score={best.score}")
            cli(
                ["lab", "save-default", str(run.id), "--context", str(ctx)],
                timeout=600,
            )
            bench_ctx = ctx
        else:
            log("no validated winner; benchmarking with the server default")
            bench_ctx = 4096
        cli(
            [
                "benchmark",
                model,
                "--context",
                str(bench_ctx),
                "--repetitions",
                "1",
                "--max-tokens-scale",
                "0.5",
            ],
            timeout=10_800,
        )
        for task in SANDBOX_TASKS:
            cli(
                ["lab", "sandbox", "--task", task, "--model", model],
                timeout=1800,
            )
    log("===== Night Swift run finished =====")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
