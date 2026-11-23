"""Second Prism watcher: wait for a 15-minute idle window, then run ladders.

User instruction: Prism is working again. Check in ~2 hours whether it still
uses VRAM/RAM. If it has been idle for at least 15 minutes (no model loading),
start the next ladder tests.

The ladder batch prioritises models whose retrieval/fill proof was missing
because of the old 300 s prefill timeout, then retries the models that failed
to load (they may now load if LM Studio's guardrail/engine changed).
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
LOG = ROOT / "prism_watch2.log"
INITIAL_WAIT_S = 2 * 60 * 60          # ~2 hours
POLL_S = 60                           # 1 minute
IDLE_REQUIRED_S = 15 * 60             # 15 minutes of continuous idle
MAX_WAIT_S = 16 * 60 * 60             # safety cap
GPU_IDLE_PERCENT = 8.0
RAM_FREE_GB = 10.0
PRISM_URL = "http://127.0.0.1:8101/health"
LMS_URL = "http://127.0.0.1:1234/v1/models"

MODELS = [
    # Retrieval/fill proof missing under the old 300 s prefill timeout.
    "google/gemma-4-12b-qat",
    "google/gemma-4-26b-a4b-qat",
    "mirothinker-v1.5-30b-q2ks-mixed-autoround",
    # Load failures worth retrying after LM Studio restarts/config changes.
    "nvidia-nemotron-3.5-bolt-74b-a9b",
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


def lms_alive() -> bool:
    try:
        with urllib.request.urlopen(LMS_URL, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


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


def ensure_lms() -> None:
    """Start the detached LM Studio server if it is not listening."""
    if lms_alive():
        log("LM Studio server already running.")
        return
    lms_exe = Path.home() / ".lmstudio" / "bin" / "lms.exe"
    if not lms_exe.exists():
        log("lms.exe not found — ladders will likely fail.")
        return
    log("Starting LM Studio server detached...")
    subprocess.Popen(
        [str(lms_exe), "server", "start", "-p", "1234"],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        time.sleep(2)
        if lms_alive():
            log("LM Studio server is up.")
            return
    log("LM Studio server did not come up in 60 s.")


def wait_for_idle_window() -> None:
    """Wait until Prism has been idle (no model, low GPU, free RAM) for 15 min."""
    started = time.monotonic()
    idle_since: float | None = None
    while time.monotonic() - started < MAX_WAIT_S:
        health = prism_health()
        gpu = gpu_util()
        ram = ram_free_gb()

        if health is None:
            log("Prism is not responding — treating the GPU as free.")
            return

        gpu_pct = gpu[0] if gpu else None
        ram_ok = ram is not None and ram >= RAM_FREE_GB
        gpu_ok = gpu_pct is not None and gpu_pct <= GPU_IDLE_PERCENT
        # A resident model is fine: the criterion is no *loading/inference*
        # activity (GPU idle + free RAM) for 15 continuous minutes, not an
        # empty Prism.
        idle = bool(gpu_ok and ram_ok)

        if idle:
            if idle_since is None:
                idle_since = time.monotonic()
            idle_for = int(time.monotonic() - idle_since)
        else:
            idle_since = None
            idle_for = 0

        log(
            "Prism"
            f" current_model={health.get('current_model')!r}"
            f" gpu_util={gpu_pct}"
            f" ram_free_gb={ram}"
            f" idle_for_s={idle_for}"
        )

        if idle_for >= IDLE_REQUIRED_S:
            log("Prism idle for >= 15 min — starting the next ladder batch.")
            return

        time.sleep(POLL_S)

    log("Safety cap reached — starting ladders anyway.")


def run_ladders() -> int:
    ensure_lms()
    script = ROOT / "_ladders_batch2.py"
    script.write_text(
        "import subprocess, sys, os\n"
        f"models = {MODELS!r}\n"
        "if not models:\n"
        "    print('No models to run', flush=True)\n"
        "    raise SystemExit(0)\n"
        "for m in models:\n"
        "    print(f'\\n===== LADDER: {m} =====', flush=True)\n"
        "    cmd = [sys.executable, '-m', 'lm_optimizer', 'lab', 'context-explorer', m,\n"
        "           '--min-context', '2048', '--max-context', '262144', '--repetitions', '1']\n"
        "    r = subprocess.run(cmd, cwd=os.getcwd())\n"
        "    print(f'exit code for {m}: {r.returncode}', flush=True)\n"
        "print('\\nBATCH 2 LADDERS DONE')\n",
        encoding="utf-8",
    )
    log(f"Running ladders: {', '.join(MODELS)}")
    proc = subprocess.run([sys.executable, str(script)], cwd=str(ROOT))
    log(f"Ladder batch exited with {proc.returncode}")
    try:
        script.unlink()
    except OSError:
        pass
    return proc.returncode


def main() -> int:
    log(f"Prism watcher 2 started; first check in {INITIAL_WAIT_S // 3600} h, "
        f"needs {IDLE_REQUIRED_S // 60} min of continuous idle.")
    time.sleep(INITIAL_WAIT_S)
    log("Initial wait complete; checking Prism.")
    wait_for_idle_window()
    return run_ladders()


if __name__ == "__main__":
    raise SystemExit(main())
