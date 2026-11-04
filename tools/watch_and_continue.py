"""Watch manually started Swift runs, finish the pair, then run benchmarks.

The user starts the first Swift model manually. This watcher:

1. waits until the machine is idle (no lm_optimizer process, no loaded model),
2. marks the models that were active as completed,
3. starts the *other* Swift variant with the full night treatment
   (optimize -> save default -> benchmark -> all sandbox tasks),
4. once both variants are done, launches the remaining-model benchmark sweep.

It never starts the first Swift model: if nothing was started, it waits.
State is persisted in ``logs/watch_and_continue_state.json`` so a restart
does not relaunch finished work.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import psutil

ROOT = Path(__file__).resolve().parents[1]
SWIFT = ["swift-qwen3.8-27b@q2_k", "swift-qwen3.8-27b@q4_k_s"]
STATE_PATH = Path("logs/watch_and_continue_state.json")
LOG_PATH = Path("logs/watch_and_continue.log")
CHECK_SECONDS = 60
IDLE_CHECKS_REQUIRED = 3
MARKERS = (
    "lm_optimizer",
    "night_swift.py",
    "benchmarks_32k.py",
    "sandbox_all_models.py",
)


def log(message: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "completed": [],
        "in_progress": [],
        "benchmarks_started": False,
        "idle_streak": 0,
        "launch_grace_until": 0.0,
    }


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def active_work() -> tuple[set[str], list[int]]:
    """Swift models mentioned by running optimizer processes + their PIDs."""
    models: set[str] = set()
    pids: list[int] = []
    me = os.getpid()
    for proc in psutil.process_iter(["pid", "cmdline"]):
        pid = proc.info.get("pid")
        if not pid or pid == me:
            continue
        cmdline = proc.info.get("cmdline") or []
        joined = " ".join(str(part) for part in cmdline)
        if not any(marker in joined for marker in MARKERS):
            continue
        pids.append(pid)
        for model in SWIFT:
            if model in joined:
                models.add(model)
    return models, pids


def loaded_models() -> tuple[set[str], bool]:
    """Loaded instance ids from LM Studio; ``ok=False`` means state unknown."""
    try:
        response = httpx.get("http://127.0.0.1:1234/api/v1/models", timeout=15)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return set(), False
    loaded: set[str] = set()
    for model in payload.get("models", []):
        key = str(model.get("key") or "")
        for instance in model.get("loaded_instances") or []:
            loaded.add(str(instance.get("id") or key))
    return loaded, True


def launch(args: list[str], log_file: Path) -> subprocess.Popen:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handle = log_file.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, *args],
        cwd=ROOT,
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    log(f"launched pid={proc.pid}: {' '.join(args)}")
    return proc


def main() -> int:
    state = load_state()
    log("watcher started")
    log(f"state: {json.dumps(state)}")
    while True:
        models, pids = active_work()
        loaded, loaded_ok = loaded_models()
        busy = bool(pids) or not loaded_ok or bool(loaded)

        if models:
            for model in models:
                if model not in state["in_progress"] and model not in state["completed"]:
                    state["in_progress"].append(model)
                    log(f"detected active: {model}")

        grace = float(state.get("launch_grace_until") or 0.0)
        if time.time() < grace:
            busy = True

        if busy:
            state["idle_streak"] = 0
            save_state(state)
            time.sleep(CHECK_SECONDS)
            continue

        state["idle_streak"] = int(state.get("idle_streak") or 0) + 1
        save_state(state)
        log(
            f"idle streak {state['idle_streak']}/{IDLE_CHECKS_REQUIRED} "
            f"(in_progress={state['in_progress']}, completed={state['completed']})"
        )
        if state["idle_streak"] < IDLE_CHECKS_REQUIRED:
            time.sleep(CHECK_SECONDS)
            continue

        # Promote in-progress work to completed.
        for model in list(state["in_progress"]):
            state["in_progress"].remove(model)
            if model not in state["completed"]:
                state["completed"].append(model)
                log(f"completed: {model}")

        if all(model in state["completed"] for model in SWIFT):
            if not state.get("benchmarks_started"):
                state["benchmarks_started"] = True
                state["idle_streak"] = 0
                save_state(state)
                log("both Swift variants done -> launching remaining benchmarks")
                proc = launch(
                    ["tools/benchmarks_32k.py"],
                    Path("logs/benchmarks_32k_stdout.log"),
                )
                proc.wait()
                log(f"benchmarks finished with exit {proc.returncode}")
                return 0
            log("both Swift variants already done; exiting")
            return 0

        missing = [model for model in SWIFT if model not in state["completed"]]
        if len(missing) == 1 and not state["in_progress"]:
            model = missing[0]
            state["in_progress"] = [model]
            state["idle_streak"] = 0
            state["launch_grace_until"] = time.time() + 180
            save_state(state)
            log(f"starting the other Swift variant: {model}")
            launch(
                ["tools/night_swift.py", model],
                Path("logs/night_swift_watcher.log"),
            )
            time.sleep(CHECK_SECONDS)
            continue

        state["idle_streak"] = 0
        save_state(state)
        log("waiting for the user to start a Swift run")
        time.sleep(CHECK_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
