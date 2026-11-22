#!/usr/bin/env python
"""Re-run all failed/timed-out sandbox tasks, fastest model first."""
import subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
LOG = ROOT / "results" / "retake_failed.log"

RUNS = [
    ("google/gemma-4-e4b", "email_write"),
    ("google/gemma-4-e4b", "vision_ui_confluence_page"),
    ("google/gemma-4-e4b", "minecraft_world"),
    ("google/gemma-4-12b-qat", "vision_counting_coins"),
    ("google/gemma-4-12b-qat", "vision_ui_confluence_page"),
    ("swift-qwen3.8-27b", "minecraft_world"),
    ("nvidia-nemotron-3.5-bolt-74b-a9b", "minecraft_world"),
]

def unload_all():
    try:
        subprocess.run(["lms", "unload", "--all"], capture_output=True, text=True, timeout=120)
    except Exception:
        pass
    time.sleep(10)

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
        tail = ((r.stdout or "")[-400:] + "\n--- STDERR ---\n" + (r.stderr or "")[-200:])
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
        print(f"Retake started {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        for model, task in RUNS:
            run_one(model, task)
        print(f"\nRetake finished {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)