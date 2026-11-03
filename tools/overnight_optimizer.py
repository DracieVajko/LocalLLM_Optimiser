"""Overnight optimizer queue: smallest models first, best configs then benchmarks.

Skips the dense Swift 27B and the already-finished small models. Each model
gets a bounded speed search, quality gate at a safe context, a saved LM Studio
default (offloadRatio=1.0) and a verification benchmark.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

from lm_optimizer.database.repositories import run_repo

LOG = Path("logs/overnight_optimizer.log")
LOG.parent.mkdir(parents=True, exist_ok=True)

QUEUE = [
    # model, max_context, quality_context
    ("mirothinker-v1.5-30b-q2ks-mixed-autoround", 8192, 4096),
    ("openai-gpt-oss-20b-claude-4.5-opus-heretic-uncensored-i1", 8192, 4096),
    ("google/gemma-4-26b-a4b-qat", 8192, 4096),
    ("qwen/qwen3-coder-30b", 8192, 4096),
    ("qwen/qwen3.6-35b-a3b", 8192, 4096),
    ("nvidia-nemotron-3.5-bolt-74b-a9b-24gb", 4096, 2048),
    ("recursivesi/flint", 4096, 2048),
]

COMMON = [
    "--profile",
    "balanced",
    "--quality",
    "0.9",
    "--max-speed-probes",
    "2",
    "--max-finalists",
    "1",
    "--benchmark-repetitions",
    "1",
    "--validation-repetitions-max",
    "2",
    "--warmup-runs",
    "0",
    "--skip-phases",
    "context_speed,context,recovery,validation",
    "--non-interactive",
    "--yes",
    "--no-enable-rope",
    "--no-enable-cpu-moe",
    "--no-enable-speculative",
]


def log(message: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True)


def _cli(args: list[str], timeout: int) -> int:
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
    tail = (result.stdout or "")[-6000:]
    err = (result.stderr or "")[-3000:]
    if tail:
        log(tail)
    if err:
        log("STDERR: " + err)
    log(f"EXIT {result.returncode}")
    return result.returncode


def _winner(model_id: str):
    for run in run_repo.get_by_model(model_id, limit=10):
        if run.status.value not in ("success", "completed", "partial_success"):
            continue
        best = run.get_best_config()
        if best is not None:
            return run, best
    return None, None


def main() -> int:
    log("Overnight optimizer queue started")
    for model, max_ctx, quality_ctx in QUEUE:
        log(f"===== {model} (max_ctx={max_ctx}, quality_ctx={quality_ctx}) =====")
        args = [
            "optimize",
            model,
            *COMMON,
            "--max-context",
            str(max_ctx),
            "--min-context",
            "2048",
            "--quality-context",
            str(quality_ctx),
        ]
        rc = _cli(args, timeout=14_400)
        if rc != 0:
            log(f"optimize failed/timed out for {model}; continuing")
        run, best = _winner(model)
        if run is None or best is None:
            log(f"NO WINNER for {model}")
            continue
        ctx = int(best.context_length or quality_ctx)
        log(f"winner run={run.id} ctx={ctx} score={best.score}")
        _cli(
            ["lab", "save-default", str(run.id)],
            timeout=600,
        )
        _cli(
            [
                "benchmark",
                model,
                "--context",
                str(ctx),
                "--repetitions",
                "1",
                "--max-tokens-scale",
                "0.5",
            ],
            timeout=7_200,
        )
    log("Overnight optimizer queue finished")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
