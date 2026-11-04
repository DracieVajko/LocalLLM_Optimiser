"""Set all model defaults to context 32768 and run identical benchmark per model.

Skips Swift 27B (dense, per user request). Runs in background.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

LOG = Path("logs/benchmarks_32k.log")
LOG.parent.mkdir(parents=True, exist_ok=True)

MODELS = [
    ("prism-ml/bonsai-27b", "f1f8574e-6e40-45fb-88bc-fa522b964e7b"),
    ("nvidia-nemotron-3.5-bolt-e4b", "78c252af-baf4-414d-b813-3e583f20ab4e"),
    ("qwen3.8-9b-distill", "be9c922a-da38-40e8-bc69-f71e7a5467f4"),
    ("mirothinker-v1.5-30b-q2ks-mixed-autoround", "952b1cff-d74c-4f5f-b64b-18892266857b"),
    ("google/gemma-4-26b-a4b-qat", "830df106-da7c-4629-b531-a90e73d02334"),
    ("qwen/qwen3-coder-30b", "ff74d7b0-c51d-460b-a3b6-0e0f777ff260"),
    ("openai-gpt-oss-20b-claude-4.5-opus-heretic-uncensored-i1", "22aee0c8-33a9-4c78-83ff-7c6e8a33751b"),
    ("qwen/qwen3.6-35b-a3b", "4de58d2c-3243-4f1f-846d-19e7ef3019ea"),
    ("nvidia-nemotron-3.5-bolt-74b-a9b-24gb", "78efeec6-5804-4823-85c8-054dd242cda1"),
]

CONTEXT = 32768


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
    tail = (result.stdout or "")[-8000:]
    err = (result.stderr or "")[-3000:]
    if tail:
        log(tail)
    if err:
        log("STDERR: " + err)
    log(f"EXIT {result.returncode}")
    return result.returncode


def main() -> int:
    log("===== Benchmarks at context %d (all models, same benchmark) =====" % CONTEXT)
    for model, run_id in MODELS:
        log(f"===== {model} =====")
        # 1. Update LM Studio default to context 32768
        rc = cli(
            ["lab", "save-default", str(run_id), "--context", str(CONTEXT)],
            timeout=600,
        )
        if rc != 0:
            log(f"save-default failed for {model}; continuing with benchmark anyway")
        # 2. Run identical benchmark at context 32768
        rc = cli(
            [
                "benchmark",
                model,
                "--context",
                str(CONTEXT),
                "--repetitions",
                "1",
                "--max-tokens-scale",
                "0.5",
            ],
            timeout=10_800,
        )
        if rc != 0:
            log(f"benchmark failed for {model}; continuing")
    log("===== All benchmarks finished =====")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
