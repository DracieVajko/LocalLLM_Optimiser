import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
LOG = ROOT / "results" / "gemma_optimize.log"

MODELS = [
    "google/gemma-4-e4b",
    "google/gemma-4-12b",
    "google/gemma-4-12b-qat",
]

def unload_all():
    try:
        subprocess.run(["lms", "unload", "--all"], capture_output=True, text=True, timeout=120)
    except Exception:
        pass
    time.sleep(8)

def run_one(model):
    print(f"\n===== OPTIMIZE {model} =====", flush=True)
    unload_all()
    started = time.time()
    cmd = [
        str(PY), "-m", "lm_optimizer.cli.main", "optimize", model,
        "--preset", "standard",
        "--repetitions", "1",
        "--validation", "1",
        "--max-speed-probes", "10",
        "--max-finalists", "2",
        "--yes",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10800, cwd=str(ROOT))
        elapsed = round(time.time() - started)
        tail = ((r.stdout or "")[-1500:] + "\n--- STDERR ---\n" + (r.stderr or "")[-800:])
        print(tail, flush=True)
        print(f"===== {model}: exit {r.returncode} in {elapsed}s =====", flush=True)
        return r.returncode
    except subprocess.TimeoutExpired:
        print(f"===== {model}: TIMEOUT after 10800s =====", flush=True)
        return -1
    finally:
        unload_all()

if __name__ == "__main__":
    with open(LOG, "w", encoding="utf-8") as f:
        sys.stdout = f
        sys.stderr = f
        print(f"Gemma optimize started {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        for m in MODELS:
            run_one(m)
        print(f"\nGemma optimize finished {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)