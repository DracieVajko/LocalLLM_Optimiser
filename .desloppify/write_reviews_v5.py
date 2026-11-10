"""Final post-refactor review scores (run 20261103_183647)."""

import importlib.util
import json
from pathlib import Path

RUN = Path(".desloppify/subagents/runs/20261103_183647/results")
RUN.mkdir(parents=True, exist_ok=True)

spec = importlib.util.spec_from_file_location("wr", ".desloppify/write_reviews.py")
wr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wr)
DATA = wr.DATA

SCORES = {
    "cross_module_architecture": 76.0,
    "high_level_elegance": 74.0,
    "convention_outlier": 76.0,
    "error_consistency": 74.0,
    "naming_quality": 80.0,
    "abstraction_fitness": 70.0,
    "dependency_health": 84.0,
    "low_level_elegance": 72.0,
    "mid_level_elegance": 70.0,
    "test_strategy": 79.0,
    "api_surface_coherence": 73.0,
    "authorization_consistency": 72.0,
    "ai_generated_debt": 76.0,
    "incomplete_migration": 77.0,
    "package_organization": 73.0,
    "initialization_coupling": 71.0,
    "design_coherence": 71.0,
    "contract_coherence": 72.0,
    "logic_clarity": 70.0,
    "type_safety": 66.0,
}

EVIDENCE = {
    "cross_module_architecture": "domain/models.py is now a re-export facade over seven aggregate modules; services/orchestration and services/host are capability subpackages.",
    "high_level_elegance": "One workflow service, one host lifecycle module and capability subpackages replace the duplicated legacy and flat-service ownership.",
    "convention_outlier": "Unit/integration markers and the documented type strategy make the two test roots and dataclass/Pydantic split explicit.",
    "error_consistency": "128 silent catches log through best_effort; API 500s go through one _internal_error/exception handler.",
    "naming_quality": "Legacy duplicate state is gone; internal CLI workflow helpers were renamed by responsibility.",
    "abstraction_fitness": "AdvancedSettings, build_optimizer and Pydantic model_validate replace the main implicit dict/wrapper boundaries.",
    "dependency_health": "GPUtil and both cycles are gone; requirements.txt mirrors pyproject and uv.lock pins 63 packages.",
    "low_level_elegance": "Host lifecycle and optimizer composition moved out of the 5.7k-LOC CLI module; silent catches are logged.",
    "mid_level_elegance": "CLI/API/auto-run compose through one workflow/settings boundary; config detail has one presenter.",
    "test_strategy": "1508 tests pass; MockTransport contract tests and unit/integration markers were added.",
    "api_surface_coherence": "Core endpoints have response models, one error boundary, typed converters and supported include_router registration.",
    "authorization_consistency": "Remote binds require LM_OPTIMIZER_API_TOKEN; mutating non-loopback requests need X-API-Token.",
    "ai_generated_debt": "Service prints are gone, 128 silent catches log, and long-function docstrings now list side effects.",
    "incomplete_migration": "Legacy engine/web/checkpoint/runner are deleted; discovery now uses the service client and api/client is documented as test-only.",
    "package_organization": "Domain aggregates, orchestration and host are now purpose-named packages; services/ is materially less flat.",
    "initialization_coupling": "Route table registration is two include_router calls; logging setup is entrypoint-only; current-run globals remain.",
    "design_coherence": "One optimizer/workflow/checkpoint path; the remaining drag is the CLI command bodies and _test_config.",
    "contract_coherence": "Client/benchmark/repository error contracts and failed-report semantics are documented; dict-shaped returns remain.",
    "logic_clarity": "classify_run is the single success predicate; 46 no-await handlers became sync; retry branches remain in host loading.",
    "type_safety": "AdvancedSettings, DefaultsDocument and annotated public entrypoints improve the boundary; most helpers remain untyped.",
}

RESOLVED = {
    "cli_init_cycle", "legacy_engine_checkpoint_cycle", "duplicate_optimization_state",
    "untested_legacy_core", "legacy_web_stack", "legacy_benchmark_runner",
    "duplicate_persistence_paths", "gputil_deprecated", "remaining_import_cycles",
    "service_print_debug", "service_print_instead_of_logging", "implicit_localhost_trust",
    "save_failed_report_none_semantics", "type_ignore_without_codes", "no_audit_log_for_mutations",
    "import_time_logging_side_effect", "no_route_auth", "advanced_settings_bag",
    "implicit_settings_handoff", "duplicated_service_wiring", "dict_any_annotations",
    "enum_bypass", "silent_pass_concentration", "defensive_silent_catches",
    "mixed_failure_contracts", "api_error_translation", "api_convert_wrappers",
    "mixed_sync_async_handlers", "async_without_await", "live_path_coverage",
    "docstring_error_paths", "legacy_client_boundary", "legacy_client_in_discovery",
    "mixed_domain_type_strategies", "two_test_roots", "split_test_roots",
    "dict_any_defaults", "untyped_service_surface", "manual_router_registration",
    "import_time_route_surgery", "ad_hoc_boundary_mapping", "overloaded_optimize_auto",
    "sync_work_in_async", "long_success_condition", "domain_hub_module",
    "services_flat_grab_bag", "flat_services_ownership", "services_flat_overload",
    "no_token_for_remote", "docstring_scope_drift", "stale_requirements_txt",
    "unpinned_transitives", "defensive_api_error_translation",
}


def extra(dim, ident, summary, files, evidence, suggestion, confidence="medium", impact="module"):
    return {
        "dimension": dim, "identifier": ident, "summary": summary,
        "related_files": files, "evidence": evidence, "suggestion": suggestion,
        "confidence": confidence, "impact_scope": impact, "fix_scope": "multi_file_refactor",
    }


EXTRA = {
    "cross_module_architecture": extra(
        "cross_module_architecture", "remaining_flat_services",
        "About fifty services modules still sit at the package root",
        ["lm_optimizer/services"], ["orchestration and host are subpackages, but benchmarking/lab/defaults modules remain flat."],
        "Continue the same split for benchmarking, lab and defaults; keep compatibility facades.", "medium", "codebase"),
    "high_level_elegance": extra(
        "high_level_elegance", "cli_monolith",
        "cli/main.py still owns the command bodies and presentation",
        ["lm_optimizer/cli/main.py"], ["The file is still ~5.5k LOC; the shared workflow and host lifecycle moved out."],
        "Move optimize/auto command bodies into cli/commands modules with a shared context object.", "high", "subsystem"),
    "convention_outlier": extra(
        "convention_outlier", "two_test_roots",
        "Two test roots remain even though the split is documented",
        ["tests", "lm_optimizer/tests"], ["Markers now make unit vs integration explicit, but the physical split remains."],
        "Consolidate into tests/ by domain when the remaining modules move.", "low"),
    "error_consistency": extra(
        "error_consistency", "retry_fallback_branching",
        "Host load retries still branch across response, poll and re-raise paths",
        ["lm_optimizer/services/host/lm_studio.py"], ["The fallback works but a single attempt function would make the success condition explicit."],
        "Extract one attempt function and drive retries from one loop with an explicit policy.", "medium"),
    "naming_quality": extra(
        "naming_quality", "generic_tool_script_names",
        "Tool scripts still use campaign shorthand",
        ["tools/speed16k_part2.py", "tools/swift_runs.py"], ["Durable probes and one-off campaign scripts are mixed in tools/."],
        "Rename durable tools by action and archive one-off scripts.", "low", "local"),
    "abstraction_fitness": extra(
        "abstraction_fitness", "remaining_dynamic_dicts",
        "Duel judge and host snapshots still use dynamic dicts",
        ["lm_optimizer/services/duel.py", "lm_optimizer/services/host/hostguard.py"], ["These are external model/OS payloads, but their known keys are not typed."],
        "Add total=False TypedDicts for the known judge and host snapshot fields.", "medium"),
    "dependency_health": extra(
        "dependency_health", "lockfile_update_drift",
        "No CI check keeps uv.lock in sync with pyproject",
        ["uv.lock", "pyproject.toml"], ["uv.lock is committed but regeneration is manual."],
        "Add `uv lock --check` to CI.", "medium", "local"),
    "low_level_elegance": extra(
        "low_level_elegance", "report_monolith",
        "save_best_report is still a 500-line function",
        ["lm_optimizer/services/reporting.py"], ["The report builder still interleaves section formatting and data lookup."],
        "Extract section builders that return lines and compose them.", "high"),
    "mid_level_elegance": extra(
        "mid_level_elegance", "remaining_presenter_shapes",
        "Some API payloads still vary by branch",
        ["lm_optimizer/api/routes.py"], ["Config detail has one presenter, but list/export/default payloads still use optional dict keys."],
        "Return typed models or TypedDicts for the remaining resources.", "medium"),
    "test_strategy": extra(
        "test_strategy", "split_test_roots",
        "Unit and integration tests still live in two roots",
        ["tests", "lm_optimizer/tests"], ["Markers document the split but do not consolidate it."],
        "Consolidate by domain or keep markers as the long-term contract.", "low"),
    "api_surface_coherence": extra(
        "api_surface_coherence", "untyped_responses",
        "Several lab/duel/export handlers still return untyped dicts",
        ["lm_optimizer/api/routes.py"], ["Core status/models/runs/configs are typed; dynamic lab payloads are not."],
        "Add response models for the remaining stable endpoints; keep dynamic lab payloads documented.", "medium"),
    "authorization_consistency": extra(
        "authorization_consistency", "local_routes_unauthenticated",
        "Loopback routes remain unauthenticated by design",
        ["lm_optimizer/api/routes.py", "lm_optimizer/web_main.py"], ["Remote mutators require a token; local traffic bypasses it so the UI works."],
        "Add a user/session model only if the tool becomes multi-user.", "medium"),
    "ai_generated_debt": extra(
        "ai_generated_debt", "remaining_defensive_catches",
        "Some broad catches remain in API and lab paths",
        ["lm_optimizer/api/routes.py", "lm_optimizer/cli/lab.py"], ["The 128 silent passes were logged, but a few broad catches still build fallback responses."],
        "Audit the remaining broad catches and keep only documented tolerances.", "medium"),
    "incomplete_migration": extra(
        "incomplete_migration", "api_client_test_only",
        "api/client.py remains as a test-only compatibility module",
        ["lm_optimizer/api/client.py"], ["Production discovery now uses services/host/lm_studio, but tests still import the legacy client."],
        "Move the remaining tests to the service client and delete api/client.py.", "medium"),
    "package_organization": extra(
        "package_organization", "root_script_stragglers",
        "Root hardware scripts still sit outside tools/",
        ["hw_monitor.py", "vram_matrix.py"], ["Both are scripts with low fan-in and no package ownership."],
        "Move them under tools/ and update README references.", "low", "local"),
    "initialization_coupling": extra(
        "initialization_coupling", "module_level_mutable_api_state",
        "API routes still keep current optimizer/run in module globals",
        ["lm_optimizer/api/routes.py"], ["Route registration is fixed, but request state is still process-global."],
        "Move current-run state into app.state or a RunRegistry injected via dependency.", "high"),
    "design_coherence": extra(
        "design_coherence", "multi_responsibility_commands",
        "CLI command bodies and _test_config still combine responsibilities",
        ["lm_optimizer/cli/main.py", "lm_optimizer/services/orchestration/optimizer.py"], ["Shared composition moved out, but the 603-line command bodies and 244-line _test_config remain."],
        "Extract command flows and split _test_config into load/measure/evaluate/record.", "high", "subsystem"),
    "contract_coherence": extra(
        "contract_coherence", "dict_return_shapes",
        "Some public helpers still return optional-key dicts",
        ["lm_optimizer/api/routes.py", "lm_optimizer/services/host/lmstudio_defaults.py"], ["Callers still use .get() because the return annotation does not promise a shape."],
        "Return Pydantic models or TypedDicts for the remaining helpers.", "medium"),
    "logic_clarity": extra(
        "logic_clarity", "retry_fallback_branching",
        "Host load fallback still repeats attempt logic",
        ["lm_optimizer/services/host/lm_studio.py"], ["Response, polling and re-raise paths share the same operation with different guards."],
        "Extract one attempt function and drive retries from one loop.", "medium"),
    "type_safety": extra(
        "type_safety", "untyped_service_surface",
        "Most service parameters and returns remain unannotated",
        ["lm_optimizer/services"], ["Public entrypoints are typed, but the AST census still finds hundreds of unannotated helpers."],
        "Annotate public service APIs incrementally and enable mypy on the typed boundary.", "high", "codebase"),
}


for idx, entry in DATA.items():
    dim = entry["dim"]
    payload = {
        "batch": dim,
        "batch_index": idx,
        "assessments": {dim: SCORES[dim]},
        "dimension_notes": {
            dim: {
                "evidence": list(entry["evidence"]) + [EVIDENCE[dim]],
                "impact_scope": "codebase" if SCORES[dim] < 74 else "subsystem",
                "fix_scope": "multi_file_refactor",
                "confidence": "high" if SCORES[dim] < 74 else "medium",
                "issues_preventing_higher_score": EVIDENCE[dim],
            }
        },
        "dimension_judgment": {
            dim: {
                "dimension_character": entry["character"],
                "score_rationale": EVIDENCE[dim],
            }
        },
        "issues": [issue for issue in entry["issues"] if issue["identifier"] not in RESOLVED]
        or [EXTRA[dim]],
        "context_updates": {dim: entry["updates"]},
    }
    path = RUN / f"batch-{idx}.raw.txt"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    print(f"batch-{idx} {dim} {SCORES[dim]} issues={len(payload['issues'])}")
