"""Retry GPT-OSS 20B with a lower speed floor, then save and verify."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

from lm_optimizer.database.repositories import run_repo

MODEL = "openai-gpt-oss-20b-claude-4.5-opus-heretic-uncensored-i1"
LOG = Path("logs/retry_gpt_oss.log")
LOG.parent.mkdir(parents=True, exist_ok=True)


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
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
        )
    except subprocess.TimeoutExpired:
        log("TIMEOUT")
        return 124
    log((result.stdout or "")[-6000:])
    log((result.stderr or "")[-2000:])
    log(f"EXIT {result.returncode}")
    return result.returncode


def main() -> int:
    log("GPT-OSS retry started")
    args = [
        "optimize",
        MODEL,
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
        "2048",
        "--repetitions",
        "1",
        "--validation-repetitions-max",
        "2",
        "--warmup-runs",
        "0",
        "--min-generation-tok-s",
        "1.0",
        "--skip-phases",
        "speed,context_speed,recovery,validation,context",
        "--non-interactive",
        "--yes",
        "--no-enable-rope",
        "--no-enable-cpu-moe",
        "--no-enable-speculative",
    ]
    cli(args, timeout=14_400)
    for summary in run_repo.get_by_model(MODEL, limit=10):
        if summary.status.value not in ("success", "completed", "partial_success"):
            continue
        full = run_repo.get(str(summary.id))
        best = full.get_best_config() if full else None
        if best is None:
            continue
        log(f"winner run={full.id} ctx={best.context_length} score={best.score}")
        cli(["lab", "save-default", str(full.id)], timeout=600)
        cli(
            [
                "benchmark",
                MODEL,
                "--context",
                str(int(best.context_length or 4096)),
                "--repetitions",
                "1",
                "--max-tokens-scale",
                "0.5",
            ],
            timeout=7_200,
        )
        break
    log("GPT-OSS retry finished")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
