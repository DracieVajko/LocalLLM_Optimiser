"""Sequential retry queue: failed or missing core runs. One model at a time.

KV-cache quantization escalation: start at Q4, and if any task scores 0.0 or
is not_measured, escalate to Q5, then Q8. If all three fail, skip the model
to save time. Each run is labelled with the quant actually used.

Model/task combinations (fresh start, frontier excluded):
  e4b              -> all core tasks (allrounder fast)
  gpt-oss 20b      -> all core tasks (allrounder fast)
  gemma 26b        -> email + website + research (writer)
  mirothinker 30b  -> email + website + research (deep research)
  swift 27b        -> email + website + research (coder)
  twin-turbo 27b   -> email + website + research (coder)
  nemotron 74b     -> all core tasks (final boss)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_URL = os.environ.get("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234").rstrip("/")
BIG_TASKS = "email_write,company_website,minecraft_world,blender_city,deep_research_report"
WRITER_TASKS = "email_write,company_website,deep_research_report"
CODER_TASKS = "email_write,company_website,deep_research_report"

QUEUE = [
    {"model": "google/gemma-4-26b-a4b-qat", "tasks": "minecraft_world,blender_city", "safe": True},
    {"model": "openai-gpt-oss-20b-claude-4.5-opus-heretic-uncensored-i1", "tasks": "blender_city", "safe": False},
    {"model": "swift-qwen3.8-27b", "tasks": "blender_city", "safe": True},
    {"model": "nvidia-nemotron-3.5-bolt-74b-a9b", "tasks": "blender_city", "safe": True, "timeout_min": 900},
]

KV_QUANTS = ["q4_0", "q5_0", "q8_0"]
STATE = Path("results") / "retry_queue_state.json"
LOG = Path("results") / "retry_queue.log"


def unload_all() -> None:
    try:
        import httpx
    except ImportError:
        return
    try:
        models = httpx.get(f"{BASE_URL}/api/v1/models", timeout=15).json().get("models", [])
    except Exception:
        return
    for model in models:
        for instance in model.get("loaded_instances") or []:
            instance_id = instance.get("id") or model.get("key")
            try:
                httpx.post(f"{BASE_URL}/api/v1/models/unload", json={"instance_id": instance_id}, timeout=60)
            except Exception:
                continue


def set_kv_quant(model: str, quant: str) -> None:
    from lm_optimizer.services.lmstudio_defaults import set_kv_cache_quant
    try:
        set_kv_cache_quant(model, quant)
    except Exception as e:
        print(f"  WARNING: could not set KV quant to {quant}: {e}")


def check_failed(model: str, quant: str) -> bool:
    """Check if any recent run for this model at this quant scored 0 or not_measured."""
    from pathlib import Path
    import json
    runs_path = Path("results/bakeoff/runs.jsonl")
    if not runs_path.exists():
        return True
    rows = [json.loads(l) for l in runs_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    recent = [r for r in rows if r.get("model") == model and r.get("settings", {}).get("kv_quant") == quant]
    if not recent:
        return True
    for r in recent:
        if r.get("status") == "not_measured":
            return True
        if r.get("final_score") == 0.0 or r.get("final_score") is None:
            return True
    return False


def mark(index: int, entry: dict, status: str, started: float, extra: str = "") -> None:
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    state[str(index)] = {
        "model": entry["model"],
        "tasks": entry["tasks"],
        "status": status,
        "started": datetime.fromtimestamp(started).isoformat(timespec="seconds"),
        "finished": datetime.now().isoformat(timespec="seconds") if status != "running" else None,
        "seconds": round(time.time() - started, 1),
        "note": extra,
    }
    STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")


def run_bakeoff(entry: dict, quant: str) -> int:
    """Run the bakeoff for one model at one KV quant level."""
    command = [
        sys.executable, "-m", "lm_optimizer.cli.main", "lab", "bakeoff",
        "--models", entry["model"],
        "--tasks", entry["tasks"],
        "--no-thinking",
        "--context", "4096",
        "--origin", "local",
        "--kv-quant", quant,
    ]
    if entry.get("safe"):
        command.append("--safe")

    timeout = 60 * int(entry.get("timeout_min", 90))
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        return result.returncode
    except subprocess.TimeoutExpired:
        return -1


def main() -> int:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text("{}", encoding="utf-8")
    only = set(sys.argv[1:])
    with LOG.open("a", encoding="utf-8") as log:
        for index, entry in enumerate(QUEUE):
            if only and entry["model"] not in only:
                continue
            started = time.time()
            model_short = entry["model"].split("/")[-1][:40]
            log.write(f"\n=== [{index}] {datetime.now().isoformat(timespec='seconds')} {model_short} :: {entry['tasks']} ===\n")
            log.flush()

            skipped = False
            for qi, quant in enumerate(KV_QUANTS):
                log.write(f"\n--- quant attempt {qi+1}/{len(KV_QUANTS)}: {quant} ---\n")
                log.flush()
                mark(index, entry, "running", started, f"quant={quant}")
                unload_all()
                set_kv_quant(entry["model"], quant)
                rc = run_bakeoff(entry, quant)
                unload_all()

                if rc != 0:
                    log.write(f"[bakeoff exit {rc}]\n")
                    log.flush()
                    mark(index, entry, "error", started, f"quant={quant} exit {rc}")
                    skipped = True
                    break

                # Check if any task failed
                if check_failed(entry["model"], quant):
                    log.write(f"[some tasks failed at {quant}, escalating]\n")
                    log.flush()
                    if qi < len(KV_QUANTS) - 1:
                        continue
                    else:
                        log.write(f"[all quants failed, skipping {model_short}]\n")
                        log.flush()
                        mark(index, entry, "skipped", started, "all quants failed")
                        skipped = True
                        break
                else:
                    log.write(f"[all tasks passed at {quant}]\n")
                    log.flush()
                    mark(index, entry, "done", started, f"quant={quant} all passed")
                    skipped = True
                    break

            if not skipped:
                mark(index, entry, "done", started, "completed")

        log.write(f"\n=== queue finished {datetime.now().isoformat(timespec='seconds')} ===\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
