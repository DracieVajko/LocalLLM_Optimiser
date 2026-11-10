"""End-to-end API smoke test on a small model (quality-only, one test)."""

import time

from fastapi.testclient import TestClient

from lm_optimizer.api.main import app

PAYLOAD = {
    "model_id": "qwen3.8-9b-distill",
    "profile": "quality",
    "quality_threshold": 0.9,
    "advanced_settings": {
        "quality_only": True,
        "test_names": ["short_instruction"],
        "skip_phases": ["speed", "context_speed", "recovery", "validation", "context"],
        "max_context": 2048,
        "min_context": 2048,
        "benchmark_repetitions": 1,
        "validation_repetitions_max": 2,
        "warmup_runs": 0,
        "enable_rope": False,
        "enable_cpu_moe": False,
        "enable_speculative": False,
    },
}

with TestClient(app, raise_server_exceptions=False) as client:
    response = client.post("/api/optimize", json=PAYLOAD)
    print("POST /api/optimize", response.status_code, response.text[:200])
    response.raise_for_status()
    run_id = response.json()["id"]

    for _ in range(120):
        run = client.get(f"/api/runs/{run_id}")
        if run.status_code == 200:
            data = run.json()
            status = data.get("status")
            print("run status:", status)
            if status in {"success", "failed", "completed_no_validator"}:
                break
        time.sleep(2)
    else:
        raise SystemExit("run did not finish in time")

    final = client.get(f"/api/runs/{run_id}")
    print("final", final.status_code, final.json().get("status"))
    configs = client.get(f"/api/runs/{run_id}/configurations")
    print("configurations", configs.status_code, configs.text[:300])
    detail = client.get(f"/api/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json().get("best_config_id") is not None
    print("OK: API run produced a winner")
