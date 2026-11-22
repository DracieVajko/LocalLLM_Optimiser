#!/usr/bin/env python
"""Blender retake: fastest to slowest."""
import subprocess, sys, time, json, httpx
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
LOG = ROOT / "results" / "blender_retake3.log"

MODELS = [
    "nvidia-nemotron-3.5-bolt-e4b",
    "openai-gpt-oss-20b-claude-4.5-opus-heretic-uncensored-i1",
    "google/gemma-4-26b-a4b-qat",
    "swift-qwen3.8-27b",
    "nvidia-nemotron-3.5-bolt-74b-a9b",
]

def unload_all():
    try:
        subprocess.run(["lms", "unload", "--all"], capture_output=True, text=True, timeout=120)
    except Exception as e:
        print(f"unload_all error: {e}", flush=True)
    time.sleep(10)

def run_one(model):
    print(f"\n===== {model} :: blender_city =====", flush=True)
    unload_all()
    started = time.time()
    cmd = [str(PY), "-m", "lm_optimizer.cli.main", "lab", "sandbox",
           "--task", "blender_city", "--model", model,
           "--blender", r"C:\Program Files\Blender Foundation\Blender 5.3\blender.exe"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, cwd=str(ROOT))
        elapsed = round(time.time() - started)
        score = None
        for line in (r.stdout or "").split("\n"):
            if '"final_score"' in line:
                try:
                    obj = json.loads(line.strip().rstrip(","))
                    score = obj.get("final_score")
                except Exception:
                    pass
        tail = ((r.stdout or "")[-800:] + "\n--- STDERR ---\n" + (r.stderr or "")[-400:])
        print(tail, flush=True)
        print(f"===== {model}: exit {r.returncode} in {elapsed}s score={score} =====", flush=True)
        return r.returncode
    except subprocess.TimeoutExpired:
        print(f"===== {model}: TIMEOUT after 1800s =====", flush=True)
        return -1
    finally:
        unload_all()

if __name__ == "__main__":
    with open(LOG, "w", encoding="utf-8") as f:
        sys.stdout = f
        sys.stderr = f
        print(f"Blender retake3 started {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        for m in MODELS:
            run_one(m)
        print(f"\nBlender retake3 finished {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)