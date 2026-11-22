"""Watch the local Prism server, then run the remaining LM Studio ladders.

User instruction: check Prism after ~2 hours. If Prism is no longer active,
start the ladder. If it is still active, wait until GPU and RAM are free,
then start the ladder.

This script is intentionally conservative: it only starts LM Studio ladders
when the GPU is idle for several consecutive checks and enough system RAM is
available, so it never fights Prism for the GPU.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "prism_watch.log"
INITIAL_WAIT_S = 2 * 60 * 60          # 2 hours
POLL_S = 5 * 60                       # 5 minutes
MAX_WAIT_S = 14 * 60 * 60             # safety cap
IDLE_CHECKS_REQUIRED = 3              # consecutive idle checks before ladders
GPU_IDLE_PERCENT = 8.0
RAM_FREE_GB = 12.0
PRISM_URL = "http://127.0.0.1:8101/health"

MODELS = [
    "mirothinker-v1.5-30b-q2ks-mixed-autoround",
    "nvidia-nemotron-3.5-bolt-e4b",
    "openai-gpt-oss-20b-claude-4.5-opus-heretic-uncensored-i1",
]


def log(message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    line = f"[{stamp}] {message}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def prism_health() -> dict | None:
    try:
        with urllib.request.urlopen(PRISM_URL, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return None


def gpu_util() -> tuple[float, float, float] | None:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            text=True, timeout=10,
        )
        parts = [p.strip() for p in out.strip().splitlines()[0].split(",")]
        return float(parts[0]), float(parts[1]), float(parts[2])
    except Exception:
        return None


def ram_free_gb() -> float | None:
    try:
        import psutil

        return round(psutil.virtual_memory().available / (1024 ** 3), 1)
    except Exception:
        return None


def wait_until_free() -> None:
    """Wait for Prism to stop or for GPU+RAM to stay idle."""
    started = time.monotonic()
    idle_streak = 0
    while time.monotonic() - started < MAX_WAIT_S:
        health = prism_health()
        gpu = gpu_util()
        ram = ram_free_gb()

        if health is None:
            log("Prism is not responding — treating it as inactive; starting ladders.")
            return

        gpu_pct = gpu[0] if gpu else None
        ram_ok = ram is not None and ram >= RAM_FREE_GB
        gpu_ok = gpu_pct is not None and gpu_pct <= GPU_IDLE_PERCENT
        current_model = health.get("current_model")

        log(
            "Prism alive"
            f" current_model={current_model!r}"
            f" gpu_util={gpu_pct}"
            f" ram_free_gb={ram}"
            f" idle_streak={idle_streak}"
        )

        if gpu_ok and ram_ok and current_model in (None, ""):
            idle_streak += 1
            if idle_streak >= IDLE_CHECKS_REQUIRED:
                log("GPU and RAM have been free for several checks — starting ladders.")
                return
        else:
            idle_streak = 0

        time.sleep(POLL_S)

    log("Safety cap reached while waiting for GPU/RAM — starting ladders anyway.")


def run_ladders() -> int:
    script = ROOT / "_ladders_remaining.py"
    script.write_text(
        "import subprocess, sys, os\n"
        f"models = {MODELS!r}\n"
        "for m in models:\n"
        "    print(f'\\n===== LADDER: {m} =====', flush=True)\n"
        "    cmd = [sys.executable, '-m', 'lm_optimizer', 'lab', 'context-explorer', m,\n"
        "           '--min-context', '2048', '--max-context', '262144', '--repetitions', '1']\n"
        "    r = subprocess.run(cmd, cwd=os.getcwd())\n"
        "    print(f'exit code for {m}: {r.returncode}', flush=True)\n"
        "print('\\nALL REMAINING LADDERS DONE')\n",
        encoding="utf-8",
    )
    log(f"Running ladders for: {', '.join(MODELS)}")
    proc = subprocess.run([sys.executable, str(script)], cwd=str(ROOT))
    log(f"Ladder runner exited with {proc.returncode}")
    return proc.returncode


def main() -> int:
    log(f"Prism watcher started; first check in {INITIAL_WAIT_S // 3600} h.")
    time.sleep(INITIAL_WAIT_S)
    log("Initial 2-hour wait complete; checking Prism now.")
    wait_until_free()
    return run_ladders()


if __name__ == "__main__":
    raise SystemExit(main())
