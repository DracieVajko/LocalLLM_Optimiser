#!/usr/bin/env python
"""Run minecraft_world retake for the requested models, one at a time."""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
LOG = ROOT / "results" / "minecraft_retake.log"

MODELS = [
    "nvidia-nemotron-3.5-bolt-74b-a9b",
    "nvidia-nemotron-3.5-bolt-e4b",
    "swift-qwen3.8-27b",
]

def unload_all():
    import subprocess
    try:
        subprocess.run(["lms", "unload", "--all"], capture_output=True, text=True, timeout=120)
    except Exception as e:
        print(f"unload_all error: {e}", flush=True)

def run_one(model):
    print(f"\n===== {model} =====", flush=True)
    unload_all()
    time.sleep(3)
    started = time.time()
    cmd = [str(PY), "-m", "lm_optimizer.cli.main", "lab", "sandbox",
           "--task", "minecraft_world", "--model", model]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=str(ROOT))
        elapsed = round(time.time() - started)
        tail = ((r.stdout or "")[-1500:] + "\n--- STDERR ---\n" + (r.stderr or "")[-800:])
        print(tail, flush=True)
        print(f"===== {model}: exit {r.returncode} in {elapsed}s =====", flush=True)
        return r.returncode
    except subprocess.TimeoutExpired:
        print(f"===== {model}: TIMEOUT after 600s =====", flush=True)
        return -1
    finally:
        unload_all()

if __name__ == "__main__":
    with open(LOG, "w", encoding="utf-8") as f:
        sys.stdout = f
        sys.stderr = f
        print(f"Minecraft retake started {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        for m in MODELS:
            run_one(m)
        print(f"\nMinecraft retake finished {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)