"""Run every sandbox task on every model.

Skips Swift 27B (dense, per user request).
Results go to results/sandbox/<task>/<timestamp>/
and results/sandbox_all_models.jsonl summary.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

LOG = Path("logs/sandbox_all_models.log")
LOG.parent.mkdir(parents=True, exist_ok=True)
SUMMARY = Path("results") / "sandbox_all_models.jsonl"

MODELS = [
    "prism-ml/bonsai-27b",
    "nvidia-nemotron-3.5-bolt-e4b",
    "qwen3.8-9b-distill",
    "mirothinker-v1.5-30b-q2ks-mixed-autoround",
    "google/gemma-4-26b-a4b-qat",
    "qwen/qwen3-coder-30b",
    "openai-gpt-oss-20b-claude-4.5-opus-heretic-uncensored-i1",
    "qwen/qwen3.6-35b-a3b",
    "nvidia-nemotron-3.5-bolt-74b-a9b-24gb",
    # "recursivesi/flint",  # vynechany - chat timeoutuje (model nereaguje)
]

TASKS = [
    "company_website",
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
    tail = (result.stdout or "")[-4000:]
    err = (result.stderr or "")[-2000:]
    if tail:
        log(tail)
    if err:
        log("STDERR: " + err)
    log(f"EXIT {result.returncode}")
    return result.returncode


def main() -> int:
    log("===== Sandbox all models x all tasks =====")
    log(f"Models: {len(MODELS)}, Tasks: {len(TASKS)}, Total runs: {len(MODELS) * len(TASKS)}")
    total = 0
    ok = 0
    failed = 0
    for model in MODELS:
        log(f"===== MODEL: {model} =====")
        for task in TASKS:
            total += 1
            log(f"--- [{total}/{len(MODELS) * len(TASKS)}] {model} x {task} ---")
            rc = cli(["lab", "sandbox", "--task", task, "--model", model], timeout=3600)
            entry = {
                "model": model,
                "task": task,
                "rc": rc,
                "ok": rc == 0,
            }
            with SUMMARY.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            if rc == 0:
                ok += 1
                log(f"OK {model} x {task}")
            else:
                failed += 1
                log(f"FAILED {model} x {task} (rc={rc})")
    log(f"===== Finished: {total} runs, {ok} ok, {failed} failed =====")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
