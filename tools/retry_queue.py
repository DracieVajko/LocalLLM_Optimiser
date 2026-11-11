"""Sequential retry queue: failed or missing core runs. One model at a time.

KV-cache quantization and CPU threads are read from LM Studio's per-model
defaults at run start, so each row is labelled with the setting actually used.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BIG_TASKS = "email_write,company_website,minecraft_world,blender_city,deep_research_report"

QUEUE = [
    {
        "model": "prism-ml/bonsai-27b",
        "tasks": "minecraft_world,blender_city,deep_research_report",
        "safe": True,
    },
    {
        "model": "qwen3.8-9b-distill",
        "tasks": "minecraft_world,blender_city,deep_research_report",
        "safe": False,
    },
    {
        "model": "nvidia-nemotron-3.5-bolt-e4b",
        "tasks": "blender_city,deep_research_report",
        "safe": False,
    },
    {
        "model": "swift-qwen3.8-27b",
        "tasks": "minecraft_world,blender_city,deep_research_report",
        "safe": True,
    },
    {
        "model": "openai-gpt-oss-20b-claude-4.5-opus-heretic-uncensored-i1",
        "tasks": "email_write,blender_city,deep_research_report",
        "safe": False,
    },
    {
        "model": "google/gemma-4-26b-a4b-qat",
        "tasks": "company_website,minecraft_world,blender_city,deep_research_report",
        "safe": True,
    },
    {
        "model": "mirothinker-v1.5-30b-q2ks-mixed-autoround",
        "tasks": BIG_TASKS,
        "safe": True,
        "timeout_min": 180,
    },
    {
        "model": "qwen/qwen3.6-35b-a3b",
        "tasks": "email_write",
        "safe": True,
    },
    {
        "model": "qwen3.8-27b-twin-turbo-fable-cold-fusion-709-ultra-heretic-uncensored-nm-dau-neo-mtp",
        "tasks": "email_write",
        "safe": True,
    },
    {
        "model": "qwen3.8-27b-twin-turbo-fable-cold-fusion-709-ultra-heretic-uncensored-nm-dau-neo-mtp",
        "tasks": BIG_TASKS,
        "safe": True,
        "timeout_min": 300,
    },
    {
        "model": "nvidia-nemotron-3.5-bolt-74b-a9b",
        "tasks": BIG_TASKS,
        "safe": True,
        "timeout_min": 720,
    },
]

STATE = Path("results") / "retry_queue_state.json"
LOG = Path("results") / "retry_queue.log"


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


def main() -> int:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text("{}", encoding="utf-8")
    only = set(sys.argv[1:])
    with LOG.open("a", encoding="utf-8") as log:
        for index, entry in enumerate(QUEUE):
            if only and entry["model"] not in only:
                continue
            started = time.time()
            command = [
                sys.executable,
                "-m",
                "lm_optimizer.cli.main",
                "lab",
                "bakeoff",
                "--models",
                entry["model"],
                "--tasks",
                entry["tasks"],
                "--no-thinking",
                "--context",
                "4096",
                "--origin",
                "local",
            ]
            if entry.get("safe"):
                command.append("--safe")
            log.write(
                f"\n=== [{index}] {datetime.now().isoformat(timespec='seconds')} "
                f"{entry['model']} :: {entry['tasks']} safe={bool(entry.get('safe'))}\n"
            )
            log.flush()
            mark(index, entry, "running", started)
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=60 * int(entry.get("timeout_min", 90)),
                )
                tail = (result.stdout or "")[-4000:] + (result.stderr or "")[-2000:]
                log.write(tail + f"\n[exit {result.returncode}]\n")
                log.flush()
                mark(
                    index,
                    entry,
                    "done" if result.returncode == 0 else "error",
                    started,
                    f"exit {result.returncode}",
                )
            except subprocess.TimeoutExpired:
                log.write(f"[timeout after {entry.get('timeout_min', 90)} min]\n")
                log.flush()
                mark(index, entry, "timeout", started)
        log.write(f"\n=== queue finished {datetime.now().isoformat(timespec='seconds')}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
