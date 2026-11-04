"""Verify the overnight winners with a benchmark at their winner context."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

LOG = Path("logs/verify_optimized_models.log")
LOG.parent.mkdir(parents=True, exist_ok=True)

MODELS = [
    ("mirothinker-v1.5-30b-q2ks-mixed-autoround", 4096),
    ("google/gemma-4-26b-a4b-qat", 4096),
    ("qwen/qwen3-coder-30b", 4096),
]


def log(message: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def main() -> int:
    log("Verification benchmarks started")
    for model, context in MODELS:
        log(f"===== {model} (ctx={context}) =====")
        cmd = [
            sys.executable,
            "-m",
            "lm_optimizer.cli.main",
            "benchmark",
            model,
            "--context",
            str(context),
            "--repetitions",
            "1",
            "--max-tokens-scale",
            "0.5",
        ]
        log("RUN " + " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=7_200,
            )
        except subprocess.TimeoutExpired:
            log("TIMEOUT")
            continue
        log((result.stdout or "")[-6000:])
        log((result.stderr or "")[-2000:])
        log(f"EXIT {result.returncode}")
    log("Verification benchmarks finished")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
