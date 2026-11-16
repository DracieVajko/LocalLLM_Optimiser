"""Sequential vision benchmark queue: retries + nemotron 74b full suite."""

from __future__ import annotations

import subprocess
import sys
import time

PY = sys.executable
BASE = [
    PY,
    "-m",
    "lm_optimizer.cli.main",
    "lab",
    "bakeoff",
    "--no-thinking",
    "--context",
    "4096",
    "--origin",
    "local",
    "--safe",
]

RUNS = [
    ("google/gemma-4-26b-a4b-qat", "vision_dense_market_street"),
    ("swift-qwen3.8-27b", "vision_data_budget_chart"),
    (
        "nvidia-nemotron-3.5-bolt-74b-a9b",
        ",".join(
            [
                "vision_counting_coins",
                "vision_data_budget_chart",
                "vision_logic_penrose_triangle",
                "vision_ocr_prescription",
                "vision_objects_living_room",
                "vision_dense_market_street",
                "vision_dense_city_traffic",
                "vision_ui_confluence_page",
            ]
        ),
    ),
]


def unload_all() -> None:
    try:
        import httpx
    except ImportError:
        return
    try:
        models = httpx.get("http://127.0.0.1:1234/api/v1/models", timeout=15).json()["models"]
    except Exception:
        return
    for model in models:
        for instance in model.get("loaded_instances") or []:
            try:
                httpx.post(
                    "http://127.0.0.1:1234/api/v1/models/unload",
                    json={"instance_id": instance.get("id") or model.get("key")},
                    timeout=60,
                )
            except Exception:
                continue


def main() -> int:
    for index, (model, tasks) in enumerate(RUNS, 1):
        print(f"=== [{index}/{len(RUNS)}] {model} :: {tasks}", flush=True)
        unload_all()
        started = time.time()
        command = BASE + ["--models", model, "--tasks", tasks]
        result = subprocess.run(command, capture_output=True, text=True)
        tail = (result.stdout or "")[-1500:] + (result.stderr or "")[-800:]
        print(tail, flush=True)
        print(f"=== [{index}] exit {result.returncode} in {round(time.time() - started)}s", flush=True)
        unload_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
