"""Probe LM Studio's memory guardrail for a model across load configs.

Runs each config with an empty server (``lms unload --all`` first) so the
guardrail estimate is not inflated by another resident model.

Usage:
    python tools/probe_load_guardrail.py --model <model-key>
"""

from __future__ import annotations

import argparse
import subprocess
import time

import httpx

BASE = "http://127.0.0.1:1234"

CONFIGS = [
    ("min ctx2k p1 b128 kvram", {"context_length": 2048, "parallel": 1, "eval_batch_size": 128, "physical_batch_size": 128, "offload_kv_cache_to_gpu": False}),
    ("ctx2k p1 b2048 kvram", {"context_length": 2048, "parallel": 1, "eval_batch_size": 2048, "physical_batch_size": 512, "offload_kv_cache_to_gpu": False}),
    ("ctx2k p4 b2048 kvram", {"context_length": 2048, "parallel": 4, "eval_batch_size": 2048, "physical_batch_size": 512, "offload_kv_cache_to_gpu": False}),
    ("ctx4k p1 b2048 kvgpu", {"context_length": 4096, "parallel": 1, "eval_batch_size": 2048, "physical_batch_size": 512, "offload_kv_cache_to_gpu": True}),
    ("ctx4k p4 b2048 kvgpu", {"context_length": 4096, "parallel": 4, "eval_batch_size": 2048, "physical_batch_size": 512, "offload_kv_cache_to_gpu": True}),
    ("ctx8k p4 b2048 kvgpu", {"context_length": 8192, "parallel": 4, "eval_batch_size": 2048, "physical_batch_size": 512, "offload_kv_cache_to_gpu": True}),
]


def unload_all() -> str:
    proc = subprocess.run(
        ["lms", "unload", "--all"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return (proc.stdout or proc.stderr or "").strip()


def loaded_models(http: httpx.Client) -> list[str]:
    data = http.get(f"{BASE}/api/v1/models", timeout=30).json()
    names: list[str] = []
    for item in data.get("models", []):
        for _ in item.get("loaded_instances") or []:
            names.append(item.get("key", ""))
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--out", default="results/guardrail_probe.log")
    args = parser.parse_args()

    lines: list[str] = []
    with httpx.Client(timeout=900) as http:
        for label, cfg in CONFIGS:
            print(f"[clean] {unload_all()}", flush=True)
            time.sleep(2)
            before = loaded_models(http)
            print(f"[{label}] loaded before: {before}", flush=True)
            body = {"model": args.model, **cfg, "echo_load_config": True}
            response = http.post(f"{BASE}/api/v1/models/load", json=body)
            if response.status_code == 200:
                data = response.json()
                print(f"[{label}] LOADED status={data.get('status')}", flush=True)
                # Do not keep it resident: the next config must see an empty server.
                print(f"[clean] {unload_all()}", flush=True)
                time.sleep(2)
            else:
                try:
                    message = response.json().get("error", {}).get("message", "")
                except Exception:
                    message = response.text
                print(f"[{label}] HTTP {response.status_code} -> {message[:260]}", flush=True)
            line = f"{label}: {response.status_code}"
            if response.status_code != 200:
                line += f" {message[:260]}"
            lines.append(line)
        print(f"[final] loaded: {loaded_models(http)}", flush=True)

    from pathlib import Path

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
