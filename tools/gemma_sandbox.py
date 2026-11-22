#!/usr/bin/env python
"""Run sandbox benchmarks for new Gemma models."""
import subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
LOG = ROOT / "results" / "gemma_sandbox.log"

MODELS = [
    "google/gemma-4-e4b",
    "google/gemma-4-12b-qat",
]

TASKS = ["email_write", "company_website", "minecraft_world", "vision_counting_coins", "vision_ui_confluence_page"]

def unload_all():
    try:
        subprocess.run(["lms", "unload", "--all"], capture_output=True, text=True, timeout=120)
    except Exception:
        pass
    time.sleep(8)

def run_one(model, task):
    print(f"\n===== {model} :: {task} =====", flush=True)
    unload_all()
    started = time.time()
    cmd = [str(PY), "-m", "lm_optimizer.cli.main", "lab", "sandbox",
           "--task", task, "--model", model]
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
        print(f"===== {model} :: {task}: exit {r.returncode} in {elapsed}s score={score} =====", flush=True)
        return r.returncode
    except subprocess.TimeoutExpired:
        print(f"===== {model} :: {task}: TIMEOUT after 600s =====", flush=True)
        return -1
    finally:
        unload_all()

if __name__ == "__main__":
    with open(LOG, "w", encoding="utf-8") as f:
        sys.stdout = f
        sys.stderr = f
        print(f"Gemma sandbox started {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        for m in MODELS:
            for t in TASKS:
                run_one(m, t)
        print(f"\nGemma sandbox finished {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)