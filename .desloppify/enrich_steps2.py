"""Replace every cluster step detail with an executor-ready, file-scoped sentence."""

import os
import pathlib
import subprocess

exe = pathlib.Path(os.environ["APPDATA"]) / "Python" / "Python314" / "Scripts" / "desloppify.exe"

DETAILS = {
    "cli-workflow-extraction": [
        "Create lm_optimizer/services/host_lifecycle.py and move _connect_guarded, _preflight_optimize and host cleanup there; keep thin console wrappers in lm_optimizer/cli/main.py.",
        "Create lm_optimizer/services/optimization_workflow.py that calls prepare_run/execute and returns a result object; lm_optimizer/cli/main.py renders that object.",
        "In lm_optimizer/cli/main.py, reduce the optimize and auto command bodies to argument parsing, one workflow call and console rendering; target under 150 lines each.",
        "Add tests/test_optimization_workflow.py covering prepare -> execute -> report with fakes; assert lm_optimizer/cli/main.py calls the workflow service once.",
    ],
    "settings-boundary-typing": [
        "Add lm_optimizer/services/advanced_settings.py with a typed AdvancedSettings model; construct it once in api/routes.py start_optimization and cli/main.py _optimize_advanced.",
        "Add build_benchmark_service(settings) to lm_optimizer/services/benchmark.py and call it from lm_optimizer/cli/main.py and lm_optimizer/api/routes.py so defaults cannot drift.",
        "Replace dict[str, Any] in lm_optimizer/services/lmstudio_defaults.py and lm_optimizer/services/duel.py with TypedDicts; keep raw JSON only at the file/HTTP edge.",
        "In lm_optimizer/services/optimizer.py parse skip phases once in parse_phase_skips and compare OptimizationPhase members; convert strings only at the CLI/JSON boundary.",
    ],
    "error-handling-audit": [
        "Add lm_optimizer/services/best_effort.py with a helper that logs at debug with exc_info and a context message, then returns None.",
        "In lm_optimizer/services/optimizer.py (41 blocks), lm_optimizer/api/routes.py (30) and lm_optimizer/cli/main.py (14), replace except/pass with the logged best-effort helper where failure is tolerated.",
        "Document the layer contract in lm_optimizer/services/lm_studio.py and lm_optimizer/services/benchmark.py: clients raise, services return outcome objects, repositories return None; add Raises sections.",
        "In lm_optimizer/services/optimizer.py and lm_optimizer/services/lm_studio.py, drive retries from one attempt function and one loop; add is_successful(run) in lm_optimizer/services/run_summary.py.",
    ],
    "api-contracts": [
        "Add Pydantic response schemas in lm_optimizer/api/schemas.py for status, models, runs, progress and presets, then set response_model on the matching handlers in lm_optimizer/api/routes.py.",
        "Add an exception-to-HTTP mapping layer in lm_optimizer/api/main.py (middleware or dependency) and raise typed domain errors from lm_optimizer/api/routes.py instead of ad-hoc HTTPException(500).",
        "Consolidate config response enrichment in lm_optimizer/api/routes.py into one presenter that returns the full ConfigurationResultResponse; remove _enrich_config_detail dict mutation.",
        "In lm_optimizer/api/main.py replace the manual APIRoute recreation with include_router on a pinned FastAPI version, and add a startup assertion for route count and /api prefixes.",
    ],
    "services-structure": [
        "Split lm_optimizer/services/ into orchestration, benchmarking, persistence, reporting and host_lifecycle subpackages; keep a small compatibility facade in services/__init__.py.",
        "Split lm_optimizer/domain/models.py into hardware.py, configuration.py, benchmark.py and run.py, then re-export the names from lm_optimizer/domain/__init__.py.",
        "Port lm_optimizer/discovery/inspector.py from lm_optimizer/api/client.py to lm_optimizer/services/lm_studio.py; delete api/client.py after tests/test_persistence_loop_* migrate.",
        "In lm_optimizer/api/routes.py replace _current_optimizer and _current_run_id globals with a RunRegistry stored on app.state and injected from the lifespan in lm_optimizer/api/main.py.",
    ],
    "report-and-test-config": [
        "In lm_optimizer/services/reporting.py extract one section builder per report block that returns lines; make save_best_report compose them while keeping output byte-identical.",
        "In lm_optimizer/services/optimizer.py split _test_config into load_candidate, measure_candidate, evaluate_candidate and record_candidate, then compose them in _test_config.",
    ],
    "tests-conventions": [
        "Document tests/ as the canonical root in pyproject.toml and README, add unit/integration pytest markers, and enforce the layout in CI.",
        "Add tests/test_lm_studio_transport.py and tests/test_ollama_transport.py using httpx.MockTransport for timeout, 4xx/5xx and malformed payloads.",
        "Document in README that lm_optimizer/domain/models.py uses dataclasses internally and lm_optimizer/api/schemas.py uses Pydantic only at the HTTP edge; make BenchmarkConfig typed.",
        "Add a CI path check or pytest marker enforcement so new tests cannot be added to the wrong root; update pyproject.toml markers.",
    ],
    "security-and-docs": [
        "In lm_optimizer/web_main.py generate an API token when the bind is non-loopback and require it for POST/PUT/DELETE in lm_optimizer/api/main.py; have the UI read it from an environment variable.",
        "Expand the docstrings of save_best_report in lm_optimizer/services/reporting.py and _test_config in lm_optimizer/services/optimizer.py to list every side effect and output.",
    ],
}


def run(args):
    result = subprocess.run(
        [str(exe), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


for name, details in DETAILS.items():
    for idx, detail in enumerate(details, start=1):
        rc, out = run(["plan", "cluster", "update", name, "--update-step", str(idx), "--detail", detail])
        print(f"{name} step {idx}: rc={rc} len={len(detail)}")

print("done")
