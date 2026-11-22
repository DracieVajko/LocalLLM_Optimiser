#!/usr/bin/env python
"""Re-run minecraft_world for nemotron 74b and swift."""
import subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
LOG = ROOT / "results" / "minecraft_retake3.log"

MODELS = [
    "nvidia-nemotron-3.5-bolt-74b-a9b",
    "swift-qwen3.8-27b",
]

def unload_all():
    try:
        subprocess.run(["lms", "unload", "--all"], capture_output=True, text=True, timeout=120)
    except Exception as e:
        print(f"unload_all error: {e}", flush=True)
    time.sleep(10)

def run_one(model):
    print(f"\n===== {model} :: minecraft_world =====", flush=True)
    unload_all()
    started = time.time()
    cmd = [str(PY), "-m", "lm_optimizer.cli.main", "lab", "sandbox",
           "--task", "minecraft_world", "--model", model]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200, cwd=str(ROOT))
        elapsed = round(time.time() - started)
        score = None
        for line in (r.stdout or "").split("\n"):
            if '"final_score"' in line:
                try:
                    import json
                    obj = json.loads(line.strip().rstrip(","))
                    score = obj.get("final_score")
                except Exception:
                    pass
        tail = ((r.stdout or "")[-800:] + "\n--- STDERR ---\n" + (r.stderr or "")[-400:])
        print(tail, flush=True)
        print(f"===== {model}: exit {r.returncode} in {elapsed}s score={score} =====", flush=True)
        return r.returncode
    except subprocess.TimeoutExpired:
        print(f"===== {model}: TIMEOUT after 1200s =====", flush=True)
        return -1
    finally:
        unload_all()

if __name__ == "__main__":
    with open(LOG, "w", encoding="utf-8") as f:
        sys.stdout = f
        sys.stderr = f
        print(f"Minecraft retake3 started {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        for m in MODELS:
            run_one(m)
        print(f"\nMinecraft retake3 finished {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)