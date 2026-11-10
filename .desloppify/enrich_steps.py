"""Enrich every cluster step with detail and issue refs."""

import os
import pathlib
import subprocess

exe = pathlib.Path(os.environ["APPDATA"]) / "Python" / "Python314" / "Scripts" / "desloppify.exe"

STEPS = {
    "cli-workflow-extraction": [
        ("Move _connect_guarded, _preflight_optimize and host cleanup into services/host_lifecycle.py; keep CLI wrappers for console output.", ["cli_monolith"]),
        ("Create services/optimization_workflow.py that calls prepare_run/execute and returns a result object; CLI renders.", ["giant_command_bodies"]),
        ("Reduce optimize/auto to argument parsing, workflow call and console rendering; target <150 lines each.", ["multi_responsibility_commands"]),
        ("Cover prepare -> execute -> report with fakes; assert the CLI calls the service once.", ["overloaded_optimize_auto"]),
    ],
    "settings-boundary-typing": [
        ("Add a typed model with defaults; construct once in routes.start_optimization and cli._optimize_advanced.", ["advanced_settings_bag"]),
        ("Factory in services/benchmark.py used by CLI and API to prevent argument drift.", ["duplicated_service_wiring"]),
        ("Replace dict[str, Any] in lmstudio_defaults.py and duel.py with TypedDicts; keep JSON at the edge.", ["dict_any_annotations", "dict_any_defaults"]),
        ("Parse once in parse_phase_skips and compare OptimizationPhase members; strings only at CLI/JSON.", ["enum_bypass", "untyped_service_surface", "implicit_settings_handoff"]),
    ],
    "error-handling-audit": [
        ("Helper logs at debug with exc_info and a context message; returns None.", ["defensive_silent_catches"]),
        ("Convert the 41 optimizer and 30 route silent blocks; keep documented idempotent cleanup.", ["silent_pass_concentration"]),
        ("Clients raise, services return outcome objects, repositories return None; add a Raises section to public methods.", ["mixed_failure_contracts"]),
        ("Single attempt function + retry loop; add is_successful(run) predicate.", ["retry_fallback_branching", "long_success_condition", "async_without_await", "sync_work_in_async"]),
    ],
    "api-contracts": [
        ("Define Pydantic schemas for status, models, runs, progress and presets; set response_model.", ["untyped_responses"]),
        ("Middleware or dependency maps domain exceptions; 500 details stay generic.", ["api_error_translation"]),
        ("One presenter returns the full config shape; remove ad-hoc dict mutation.", ["api_convert_wrappers", "ad_hoc_boundary_mapping", "dict_return_shapes", "docstring_error_paths"]),
        ("Use include_router with a pinned FastAPI version; assert route count/prefixes at startup.", ["manual_router_registration", "mixed_sync_async_handlers"]),
    ],
    "services-structure": [
        ("orchestration, benchmarking, persistence, reporting, host_lifecycle; keep a compatibility facade.", ["services_flat_grab_bag", "flat_services_ownership", "services_flat_overload"]),
        ("hardware.py, configuration.py, benchmark.py, run.py; re-export from domain/__init__.", ["domain_hub_module"]),
        ("Replace api.client imports; then delete api/client.py after tests migrate.", ["legacy_client_in_discovery", "legacy_client_boundary"]),
        ("RunRegistry created in lifespan; inject via dependency; remove module-level mutations.", ["module_level_mutable_api_state", "import_time_route_surgery"]),
    ],
    "report-and-test-config": [
        ("Each section returns lines; save_best_report composes them; output stays byte-identical.", ["report_monolith"]),
        ("load_candidate, measure_candidate, evaluate_candidate, record_candidate; _test_config composes.", ["test_config_multi_responsibility"]),
    ],
    "tests-conventions": [
        ("Document tests/ as canonical; mark integration vs unit; add CI matrix.", ["two_test_roots", "split_test_roots"]),
        ("Cover timeout, 4xx/5xx and malformed payloads for LM Studio and Ollama clients.", ["live_path_coverage"]),
        ("Internal aggregates dataclasses; Pydantic only at HTTP edge; BenchmarkConfig typed.", ["mixed_domain_type_strategies"]),
        ("Add a path check or pytest marker enforcement; fail PRs that add tests to the wrong root.", ["two_test_roots"]),
    ],
    "security-and-docs": [
        ("Generate a token when host is non-loopback; require it for POST/PUT/DELETE; UI reads it from env.", ["no_token_for_remote"]),
        ("Add side-effect/output sections to save_best_report and _test_config, or split them.", ["docstring_scope_drift"]),
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


for name, steps in STEPS.items():
    for idx, (detail, refs) in enumerate(steps, start=1):
        rc, out = run([
            "plan", "cluster", "update", name,
            "--update-step", str(idx),
            "--detail", detail,
            "--issue-refs", *refs,
        ])
        print(f"{name} step {idx}: rc={rc} {out.strip()[-100:]}")

rc, out = run(["plan", "cluster", "list", "--verbose"])
print("=== clusters ===")
print(out[-2500:])
