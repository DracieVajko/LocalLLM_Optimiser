#!/usr/bin/env python
"""Run deep_research_report for both Gemma models."""
import subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
LOG = ROOT / "results" / "gemma_deepresearch.log"

MODELS = [
    "google/gemma-4-12b-qat",
    "google/gemma-4-26b-a4b-qat",
]

def unload_all():
    try:
        subprocess.run(["lms", "unload", "--all"], capture_output=True, text=True, timeout=120)
    except Exception:
        pass
    time.sleep(10)

def run_one(model):
    print(f"\n===== {model} :: deep_research_report =====", flush=True)
    unload_all()
    started = time.time()
    cmd = [str(PY), "-m", "lm_optimizer.cli.main", "lab", "sandbox",
           "--task", "deep_research_report", "--model", model]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=str(ROOT))
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
        tail = ((r.stdout or "")[-500:] + "\n--- STDERR ---\n" + (r.stderr or "")[-300:])
        print(tail, flush=True)
        print(f"===== {model}: exit {r.returncode} in {elapsed}s score={score} =====", flush=True)
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
        print(f"Gemma deep research started {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        for m in MODELS:
            run_one(m)
        print(f"\nGemma deep research finished {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)