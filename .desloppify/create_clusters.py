"""Create the manual triage clusters and add their review issues."""

import os
import pathlib
import subprocess

exe = pathlib.Path(os.environ["APPDATA"]) / "Python" / "Python314" / "Scripts" / "desloppify.exe"

clusters = {
    "cli-workflow-extraction": (
        "Extract preflight, host lifecycle, run execution and rendering from cli/main.py.",
        ["cli_monolith", "giant_command_bodies", "multi_responsibility_commands", "overloaded_optimize_auto"],
    ),
    "settings-boundary-typing": (
        "One typed AdvancedSettings boundary and BenchmarkService factory across CLI/API/optimizer.",
        ["advanced_settings_bag", "implicit_settings_handoff", "duplicated_service_wiring",
         "untyped_service_surface", "dict_any_annotations", "dict_any_defaults", "enum_bypass"],
    ),
    "error-handling-audit": (
        "Replace copied silent catches with one logged best-effort helper and flatten retry/success conditions.",
        ["silent_pass_concentration", "defensive_silent_catches", "mixed_failure_contracts",
         "retry_fallback_branching", "long_success_condition", "async_without_await", "sync_work_in_async"],
    ),
    "api-contracts": (
        "Response models, one error mapping and one presenter path for the FastAPI routes.",
        ["untyped_responses", "api_error_translation", "api_convert_wrappers", "ad_hoc_boundary_mapping",
         "manual_router_registration", "mixed_sync_async_handlers", "dict_return_shapes", "docstring_error_paths"],
    ),
    "services-structure": (
        "Split the flat services package, break the domain hub and retire the legacy api/client boundary.",
        ["services_flat_grab_bag", "flat_services_ownership", "services_flat_overload", "domain_hub_module",
         "legacy_client_boundary", "legacy_client_in_discovery", "module_level_mutable_api_state",
         "import_time_route_surgery"],
    ),
    "report-and-test-config": (
        "Split the report builder and the 244-line _test_config into composable steps.",
        ["report_monolith", "test_config_multi_responsibility"],
    ),
    "tests-conventions": (
        "Choose a canonical test root and add transport-level contract tests for host clients.",
        ["two_test_roots", "split_test_roots", "live_path_coverage", "mixed_domain_type_strategies"],
    ),
    "security-and-docs": (
        "Add an optional remote API token and align long-function docstrings with their side effects.",
        ["no_token_for_remote", "docstring_scope_drift"],
    ),
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


for name, (description, issues) in clusters.items():
    rc, out = run(["plan", "cluster", "create", name, "--description", description])
    print(f"create {name}: rc={rc} {out.strip()[:160]}")
    rc, out = run(["plan", "cluster", "add", name, *issues])
    print(f"add {name}: rc={rc} {out.strip()[:220]}")

rc, out = run(["plan", "cluster", "list", "--verbose"])
print("=== cluster list ===")
print(out[-4000:])
