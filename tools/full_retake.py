#!/usr/bin/env python
"""Run retakes from fastest to slowest model."""
import subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
LOG = ROOT / "results" / "retake_all.log"

# (model, task) pairs ordered by model speed (fastest first)
RUNS = [
    ("nvidia-nemotron-3.5-bolt-e4b", "blender_city"),
    ("nvidia-nemotron-3.5-bolt-e4b", "deep_research_report"),
    ("openai-gpt-oss-20b-claude-4.5-opus-heretic-uncensored-i1", "blender_city"),
    ("google/gemma-4-26b-a4b-qat", "blender_city"),
    ("mirothinker-v1.5-30b-q2ks-mixed-autoround", "deep_research_report"),
    ("swift-qwen3.8-27b", "blender_city"),
    ("swift-qwen3.8-27b", "minecraft_world"),
    ("nvidia-nemotron-3.5-bolt-74b-a9b", "blender_city"),
    ("nvidia-nemotron-3.5-bolt-74b-a9b", "minecraft_world"),
]

def unload_all():
    import subprocess
    try:
        subprocess.run(["lms", "unload", "--all"], capture_output=True, text=True, timeout=120)
    except Exception as e:
        print(f"unload_all error: {e}", flush=True)

def run_one(model, task):
    print(f"\n===== {model} :: {task} =====", flush=True)
    unload_all()
    time.sleep(5)
    started = time.time()
    cmd = [str(PY), "-m", "lm_optimizer.cli.main", "lab", "sandbox",
           "--task", task, "--model", model]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, cwd=str(ROOT))
        elapsed = round(time.time() - started)
        # find score
        score = None
        for line in (r.stdout or "").split("\n"):
            if '"final_score"' in line:
                try:
                    import json
                    # parse the json line
                    obj = json.loads(line.strip().rstrip(","))
                    score = obj.get("final_score")
                except Exception:
                    pass
        tail = ((r.stdout or "")[-800:] + "\n--- STDERR ---\n" + (r.stderr or "")[-500:])
        print(tail, flush=True)
        print(f"===== {model} :: {task}: exit {r.returncode} in {elapsed}s score={score} =====", flush=True)
        return r.returncode
    except subprocess.TimeoutExpired:
        print(f"===== {model} :: {task}: TIMEOUT after 1800s =====", flush=True)
        return -1
    finally:
        unload_all()

if __name__ == "__main__":
    with open(LOG, "w", encoding="utf-8") as f:
        sys.stdout = f
        sys.stderr = f
        print(f"Full retake started {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        for model, task in RUNS:
            run_one(model, task)
        print(f"\nFull retake finished {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)