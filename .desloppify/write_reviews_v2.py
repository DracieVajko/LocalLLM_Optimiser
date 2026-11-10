"""Write the post-fix review scores (run 20261103_135748)."""

import importlib.util
import json
from pathlib import Path

RUN = Path(".desloppify/subagents/runs/20261103_135748/results")
RUN.mkdir(parents=True, exist_ok=True)

spec = importlib.util.spec_from_file_location("wr", ".desloppify/write_reviews.py")
wr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wr)
DATA = wr.DATA

RESOLVED = {
    "cli_init_cycle",
    "legacy_engine_checkpoint_cycle",
    "duplicate_optimization_state",
    "untested_legacy_core",
    "legacy_web_stack",
    "legacy_benchmark_runner",
    "duplicate_persistence_paths",
    "gputil_deprecated",
    "remaining_import_cycles",
    "service_print_debug",
    "service_print_instead_of_logging",
    "implicit_localhost_trust",
    "save_failed_report_none_semantics",
    "type_ignore_without_codes",
    "no_audit_log_for_mutations",
    "import_time_logging_side_effect",
    "no_route_auth",
}


def issue(dim, ident, summary, files, evidence, suggestion, confidence="high",
          impact="module", fix="multi_file_refactor"):
    return {
        "dimension": dim,
        "identifier": ident,
        "summary": summary,
        "related_files": files,
        "evidence": evidence,
        "suggestion": suggestion,
        "confidence": confidence,
        "impact_scope": impact,
        "fix_scope": fix,
    }


OVERRIDES = {
    "cross_module_architecture": {
        "score": 67.0,
        "evidence": [
            "Both former import cycles are gone: cli/__init__.py no longer re-exports the app, and the legacy engine/checkpoint pair was deleted.",
            "domain/models.py is still imported by 112 modules and logging_config.py by 43; services/optimizer.py by 41, so hub blast radius remains.",
            "lm_optimizer/services/ still holds 29k LOC in one flat package with no capability boundaries.",
            "discovery/inspector.py still imports LMStudioClient/LoadConfig from the legacy api/client instead of services/lm_studio.py.",
        ],
        "character": "Dependency direction is materially cleaner after removing the legacy stack and both cycles. The remaining structural drag is scale: a handful of hub modules and a flat services package still make change impact hard to localize.",
        "rationale": "Removing the cycles and the parallel legacy stack is a real improvement, so this is now solid in direction. The 112-importer domain hub and the 29k-LOC flat services package keep it from strong.",
        "issues": [
            issue("cross_module_architecture", "services_flat_grab_bag",
                  "services/ is a flat 29k-LOC package with no capability boundaries",
                  ["lm_optimizer/services/optimizer.py", "lm_optimizer/services/benchmark.py", "lm_optimizer/services/reporting.py", "lm_optimizer/services/lm_studio.py"],
                  ["251 structural issues are attributed to lm_optimizer/services.",
                   "The directory mixes phase orchestration, benchmarking, reporting, host lifecycle and UI support."],
                  "Split services/ into purpose-named subpackages (orchestration, benchmarking, persistence, reporting, host_lifecycle) and move modules; preserve public import paths with a temporary facade.",
                  impact="codebase", fix="architectural_change"),
            issue("cross_module_architecture", "domain_hub_module",
                  "domain/models.py is a 112-importer hub that combines every aggregate",
                  ["lm_optimizer/domain/models.py"],
                  ["The file defines hardware, model identity, benchmark cases, load configuration, quality scores, runs and profile weights in 683 LOC.",
                   "Any change to one model forces a rebuild of the import graph for 112 modules."],
                  "Split domain/models.py by aggregate (hardware.py, configuration.py, benchmark.py, run.py) and re-export from domain/__init__.py during migration.",
                  confidence="medium", impact="codebase", fix="multi_file_refactor"),
            issue("cross_module_architecture", "legacy_client_boundary",
                  "discovery/ still crosses into the legacy api/client module",
                  ["lm_optimizer/discovery/inspector.py", "lm_optimizer/api/client.py", "lm_optimizer/services/lm_studio.py"],
                  ["inspector.py imports LMStudioClient, LoadConfig and ModelInfo from api.client.",
                   "The current host client lives in services/lm_studio.py."],
                  "Port inspector.py to the service client; then retire api/client.py or clearly mark it as a test-only compatibility module.",
                  impact="module", fix="multi_file_refactor"),
        ],
    },
    "high_level_elegance": {
        "score": 66.0,
        "evidence": [
            "One optimization engine now owns orchestration (services/optimizer.py); the duplicate legacy engine was removed.",
            "cli/main.py is still 5,718 LOC and owns parsing, preflight, host lifecycle, phase orchestration, reporting and rendering for 25+ commands.",
            "services/ remains a flat 29k-LOC package instead of capability-aligned ownership boundaries.",
            "The FastAPI app is the single documented web implementation; ui/web.py is gone.",
        ],
        "character": "Top-level ownership is clearer now that only one engine and one web app exist. The remaining problem is concentration: the CLI and the flat services package still own too many lifecycles.",
        "rationale": "Removing the second engine and legacy UI fixes the biggest ownership ambiguity, so the score moves up. The monolith CLI and flat services package still prevent a strong score.",
        "issues": [
            issue("high_level_elegance", "cli_monolith",
                  "cli/main.py mixes command parsing with application orchestration and rendering",
                  ["lm_optimizer/cli/main.py"],
                  ["The file is 5,718 LOC and contains the 603-line optimize and auto command bodies, 244-line preflight, and 362-line result renderer.",
                   "Preflight, host lifecycle and report generation are reusable operations but live inside the CLI module."],
                  "Extract preflight/host lifecycle into services and move command bodies into cli/commands/* modules; keep main.py to Typer registration and output composition.",
                  impact="subsystem", fix="multi_file_refactor"),
            issue("high_level_elegance", "flat_services_ownership",
                  "No capability-level ownership inside services/",
                  ["lm_optimizer/services/optimizer.py", "lm_optimizer/services/benchmark.py", "lm_optimizer/services/reporting.py"],
                  ["A single flat directory contains orchestration, benchmark execution, report rendering, host defaults and recommendation logic.",
                   "Structural debt by area reports 251 items in lm_optimizer/services."],
                  "Group services by capability and make each subpackage expose a small __init__ API.",
                  impact="codebase", fix="architectural_change"),
        ],
    },
    "dependency_health": {
        "score": 82.0,
        "evidence": [
            "Both import cycles are gone (cycles detector reports no open issues).",
            "GPUtil was removed from pyproject and from all GPU discovery paths; nvidia-smi and rocm-smi are the only backends.",
            "The dependency set is focused: httpx, pydantic-settings, FastAPI/uvicorn, Typer/Rich, structlog, numpy, psutil.",
            "No duplicate HTTP client or settings framework was found.",
        ],
        "character": "Dependencies now have clear roles and the two maintenance hazards (unmaintained GPUtil and import cycles) are gone. The declared set is small, though the legacy requirements.txt has drifted from pyproject.",
        "rationale": "Removing GPUtil and both cycles addresses every concrete code issue found in the previous review. The stale requirements.txt is the remaining reproducibility gap, so the score is strong but not exemplary.",
        "issues": [
            issue("dependency_health", "stale_requirements_txt",
                  "requirements.txt still lists GPUtil and omits runtime dependencies",
                  ["requirements.txt", "pyproject.toml"],
                  ["requirements.txt still contains GPUtil>=1.4.0 after the dependency was removed from pyproject.",
                   "It omits pyyaml, scipy, tenacity, orjson, jinja2 and websockets that pyproject declares."],
                  "Generate requirements.txt from pyproject (pip-compile/uv export) or delete it in favor of `pip install -e .`; this prevents the two dependency lists from drifting.",
                  confidence="high", impact="module", fix="single_edit"),
        ],
    },
    "test_strategy": {
        "score": 77.0,
        "evidence": [
            "The suite now has 1,494 passing tests in about three minutes, giving fast feedback.",
            "The untested legacy engine and checkpoint modules were deleted, so the critical-untested surface disappeared.",
            "Tests are still split across tests/ (62 files) and lm_optimizer/tests/ (70 files) with different fixture conventions.",
            "Server-load and host-lifecycle paths are covered mainly by fakes/monkeypatching rather than a fake HTTP transport.",
        ],
        "character": "Coverage is broad and fast, and the largest untested risk was removed with the legacy stack. The remaining weakness is organization and transport-level realism, not missing core tests.",
        "rationale": "Deleting the untested compatibility path and keeping 1,494 tests green is a clear improvement. The two test roots and fake-only transport coverage keep it below strong.",
        "issues": [
            issue("test_strategy", "split_test_roots",
                  "Two test roots with different conventions obscure the canonical suite",
                  ["tests/test_benchmark_cache.py", "lm_optimizer/tests/test_core.py", "pyproject.toml"],
                  ["testpaths includes both roots.", "Fixture setup and import style differ between them."],
                  "Consolidate into tests/ by domain, or document and enforce the split with pytest markers (unit vs integration) and a CI matrix.",
                  confidence="medium", impact="subsystem", fix="multi_file_refactor"),
            issue("test_strategy", "live_path_coverage",
                  "Server-load and host-lifecycle paths are covered only by fakes",
                  ["lm_optimizer/services/lm_studio.py", "tests/test_load_timeout_fallback.py"],
                  ["Load-response loss and echo-probe failures required new fallback tests after live findings.",
                   "Most coverage uses monkeypatched clients rather than a fake HTTP transport."],
                  "Add httpx.MockTransport-based contract tests for the LM Studio and Ollama clients covering timeout, 4xx/5xx and malformed payloads.",
                  confidence="medium", impact="module", fix="multi_file_refactor"),
        ],
    },
    "incomplete_migration": {
        "score": 74.0,
        "evidence": [
            "The deprecated ui/web.py, optimizer/engine.py, storage/checkpoint.py and benchmark/runner.py stack was deleted.",
            "api/main.py is the single web app and services/optimizer.py the single orchestrator; the legacy engine's tests and imports were removed.",
            "discovery/inspector.py still imports LMStudioClient/LoadConfig/ModelInfo from the legacy api/client.py.",
            "api/client.py remains because tests and discovery still use it, while the active host client is services/lm_studio.py.",
        ],
        "character": "The large migration is complete: one engine, one web app and one checkpoint store. The remaining coexistence is narrow and localized to the legacy API client used by discovery and tests.",
        "rationale": "Deleting the deprecated stack resolves the structural half of the migration and removes the 2.0 legacy caveat. The remaining legacy client boundary keeps it from strong until discovery is ported.",
        "issues": [
            issue("incomplete_migration", "legacy_client_in_discovery",
                  "discovery/inspector.py still uses the legacy api/client instead of the service client",
                  ["lm_optimizer/discovery/inspector.py", "lm_optimizer/api/client.py", "lm_optimizer/services/lm_studio.py"],
                  ["inspector.py imports LMStudioClient, LoadConfig and ModelInfo from api.client.",
                   "The current host client lives in services/lm_studio.py."],
                  "Port inspector.py to the service client and delete api/client.py once tests stop importing it.",
                  impact="module", fix="multi_file_refactor"),
        ],
    },
    "design_coherence": {
        "score": 65.0,
        "evidence": [
            "The duplicate legacy engine, checkpoint manager and web stack are gone, so checkpoint/persistence ownership is now singular.",
            "cli/main.py optimize/auto are still 603-line functions that perform parsing, preflight, orchestration and rendering in one body.",
            "services/optimizer.py _test_config is still 244 lines and combines load, benchmark, quality, persistence and cleanup.",
            "Advanced settings still travel as a wide dict, so responsibilities leak across layers.",
        ],
        "character": "Design is more coherent at the architecture level after removing the parallel stack. At the function level, the CLI and _test_config still mix several responsibilities, so local reasoning remains hard.",
        "rationale": "Removing duplicate persistence and the legacy engine resolves the biggest incoherence. The 600-line commands and 244-line _test_config remain structural drags.",
        "issues": [
            issue("design_coherence", "multi_responsibility_commands",
                  "Command functions own several distinct responsibilities",
                  ["lm_optimizer/cli/main.py"],
                  ["optimize/auto combine argument validation, preflight, host lifecycle, run execution and report rendering.",
                   "The same responsibilities are also implemented in the API path."],
                  "Extract a shared optimization workflow service and keep CLI commands as thin adapters that parse input and render results.",
                  impact="subsystem", fix="architectural_change"),
            issue("design_coherence", "test_config_multi_responsibility",
                  "_test_config combines load, benchmark, quality and persistence",
                  ["lm_optimizer/services/optimizer.py"],
                  ["The 244-line function loads a model, runs cases, evaluates quality, records results and cleans up in one body.",
                   "Failure handling for each stage is interleaved."],
                  "Split into load_candidate, measure_candidate, evaluate_candidate and record_candidate steps composed by _test_config.",
                  impact="module", fix="multi_file_refactor"),
        ],
    },
    "authorization_consistency": {
        "score": 68.0,
        "evidence": [
            "All 62 API routes still have no authentication; this is now documented as a localhost-only threat model in README.",
            "web_main refuses a non-loopback bind unless LM_OPTIMIZER_ALLOW_REMOTE=1, making remote exposure a deliberate opt-in.",
            "Apply, restore, save-default and save-ollama-default routes now emit structured config_change audit events.",
            "The default bind is 127.0.0.1 and CORS is restricted to localhost origins.",
        ],
        "character": "Authorization is still absent by design for a local tool, but the trust boundary is now explicit and enforced at startup, and state-changing operations leave an audit trail.",
        "rationale": "Documenting and enforcing localhost-only default access plus adding mutation audit logs addresses the practical risk for this deployment model. Remote exposure still has no token, so a strong score would require an authentication layer.",
        "issues": [
            issue("authorization_consistency", "no_token_for_remote",
                  "Remote exposure is allowed without any authentication token",
                  ["lm_optimizer/web_main.py", "lm_optimizer/api/routes.py"],
                  ["LM_OPTIMIZER_ALLOW_REMOTE=1 permits a non-loopback bind while all 62 routes remain unauthenticated.",
                   "State-changing endpoints include apply, restore, save-default and delete."],
                  "If remote bind is allowed, require a generated API token for mutating routes or an authenticating reverse proxy.",
                  confidence="high", impact="codebase", fix="multi_file_refactor"),
        ],
    },
    "ai_generated_debt": {
        "score": 69.0,
        "evidence": [
            "The only real service-layer print() calls (deepresearch.py) were replaced with a formatting function rendered by the CLI.",
            "Defensive overengineering remains: 152 silent broad catches, concentrated in optimizer.py (41), routes.py (30) and cli/main.py (14).",
            "Comment ratio is 2.5%, so restating comments are not the main issue.",
            "Some long functions still carry docstrings that describe only one of several responsibilities.",
        ],
        "character": "The code reads as purposeful rather than generated: comments are sparse and service print output is gone. The remaining debt is behavioral, mostly defensive exception handling in orchestration paths.",
        "rationale": "Removing the service prints and keeping comments why-focused supports a solid score. Copied silent catches and docstring scope drift keep it from strong.",
        "issues": [
            issue("ai_generated_debt", "defensive_silent_catches",
                  "Defensive broad catches hide failures in service code",
                  ["lm_optimizer/services/optimizer.py", "lm_optimizer/api/routes.py", "lm_optimizer/cli/main.py"],
                  ["optimizer.py contains 41 'except ...: pass' blocks, routes.py 30, cli/main.py 14.",
                   "Many wrap optional enrichment/persistence rather than documented tolerances."],
                  "Replace copied catches with one logged best-effort helper and let unexpected exceptions propagate; keep only documented tolerances.",
                  impact="subsystem", fix="multi_file_refactor"),
            issue("ai_generated_debt", "docstring_scope_drift",
                  "Docstrings on long functions describe only one responsibility",
                  ["lm_optimizer/services/reporting.py", "lm_optimizer/services/optimizer.py"],
                  ["save_best_report is documented as saving a report but also builds diagnostics, presets and ladder sections.",
                   "_test_config documents loading but also benchmarks, scores and cleans up."],
                  "Either split the function so the docstring is accurate, or expand it to list all side effects and outputs.",
                  confidence="medium", impact="local", fix="single_edit"),
        ],
    },
    "convention_outlier": {
        "score": 75.0,
        "evidence": [
            "snake_case remains consistent across 1,666 detected names and every package directory.",
            "Domain objects still mix dataclasses, Pydantic models and plain dicts without a documented rule.",
            "Service-layer print() output was removed; the CLI owns console rendering.",
            "Tests remain split across tests/ (62 files) and lm_optimizer/tests/ (70 files).",
        ],
        "character": "Lexical conventions are stable and console output now lives in the CLI where it belongs. The remaining drift is structural: type strategy and test layout vary by directory without an explicit rule.",
        "rationale": "Removing service prints strengthens an already consistent style. Mixed type strategies and two test roots keep it solid but uneven.",
        "issues": [
            issue("convention_outlier", "mixed_domain_type_strategies",
                  "Domain objects use three different type strategies without a documented boundary",
                  ["lm_optimizer/domain/models.py", "lm_optimizer/api/schemas.py", "lm_optimizer/services/benchmark.py"],
                  ["domain/models.py uses dataclasses for runs/configurations.",
                   "api/schemas.py uses Pydantic BaseModel for the same concepts at the HTTP edge.",
                   "BenchmarkConfig is a dataclass with mutable defaults while request settings are dicts."],
                  "Document the rule: dataclasses for internal aggregates, Pydantic only at the HTTP boundary, and a typed config object instead of raw dicts.",
                  confidence="medium", impact="subsystem", fix="multi_file_refactor"),
            issue("convention_outlier", "two_test_roots",
                  "Tests live in two roots with different layout and fixture conventions",
                  ["tests/test_benchmark_cache.py", "lm_optimizer/tests/test_core.py", "pyproject.toml"],
                  ["pyproject testpaths includes both lm_optimizer/tests and tests.",
                   "The two roots use different import styles and fixture organization for the same services."],
                  "Pick one root (tests/) and migrate lm_optimizer/tests in batches, or document the split explicitly and enforce it in pytest markers.",
                  confidence="medium", impact="subsystem", fix="multi_file_refactor"),
        ],
    },
    "contract_coherence": {
        "score": 68.0,
        "evidence": [
            "save_failed_report now documents both None outcomes and auto_run chooses the writer from run.get_best_config() instead of inferring from a None return.",
            "Several public helpers are still annotated -> dict while returning different shapes by branch.",
            "Client methods raise on transport errors while repository methods return None; neither documents a Raises section consistently.",
            "None is still used as a multi-purpose sentinel in some service returns.",
        ],
        "character": "Contracts are honest in the typed domain core and the failed-report ambiguity is resolved. At the service/API edges, dict returns and undocumented failure paths still make callers read the body.",
        "rationale": "Documenting the None semantics and making the caller check explicit fixes the clearest contract lie. Dict-shaped returns and missing Raises sections keep it solid but uneven.",
        "issues": [
            issue("contract_coherence", "dict_return_shapes",
                  "Public helpers annotated -> dict return different key sets by branch",
                  ["lm_optimizer/api/routes.py", "lm_optimizer/services/lmstudio_defaults.py"],
                  ["Several handlers and default helpers return dict with optional keys added conditionally.",
                   "Callers use .get(...) because the annotation does not promise a shape."],
                  "Return Pydantic models or TypedDicts with required/optional fields, and keep raw dicts only at serialization boundaries.",
                  confidence="medium", impact="module", fix="multi_file_refactor"),
            issue("contract_coherence", "docstring_error_paths",
                  "Docstrings describe the happy path but omit raised errors",
                  ["lm_optimizer/services/lm_studio.py"],
                  ["Client methods raise on transport errors without a documented Raises section.",
                   "Some service helpers return None/False for invalid input instead of raising."],
                  "Add Raises/Returns sections for public functions and align annotations with every return path.",
                  confidence="medium", impact="local", fix="single_edit"),
        ],
    },
    "type_safety": {
        "score": 61.0,
        "evidence": [
            "693 parameters and 264 returns in production code still have no annotation; 109 functions are annotated -> dict and 47 -> Any.",
            "77 dict[str, Any] annotations remain, concentrated in defaults/duel/hostguard modules.",
            "All 20 type: ignore comments now carry error codes (and optional-dependency reasons).",
            "Enum types exist for phases/stages/status but are bypassed with raw string comparisons in several places.",
        ],
        "character": "The typed domain core and Pydantic request models remain trustworthy, and suppression comments are now auditable. Most of the service and CLI surface is still untyped or dict/Any, so annotations only partially describe runtime behavior.",
        "rationale": "Tagging every ignore and correcting the Optional list annotations is a real hygiene improvement. The untyped majority of parameters and dict-returning APIs keep this as significant drag.",
        "issues": [
            issue("type_safety", "untyped_service_surface",
                  "Most service parameters and returns lack annotations",
                  ["lm_optimizer/services/optimizer.py", "lm_optimizer/services/benchmark.py", "lm_optimizer/cli/auto_run.py"],
                  ["The AST census finds 693 unannotated parameters and 264 unannotated returns.",
                   "Public service methods accept advanced settings and config fragments as bare dicts."],
                  "Annotate public entrypoints first (prepare_run, execute, run_cases, auto_run) with concrete types and enable mypy/pyright on those modules.",
                  impact="codebase", fix="multi_file_refactor"),
            issue("type_safety", "dict_any_annotations",
                  "dict[str, Any] is used where a concrete shape is known",
                  ["lm_optimizer/services/lmstudio_defaults.py", "lm_optimizer/services/duel.py", "lm_optimizer/services/hostguard.py"],
                  ["lmstudio_defaults.py has 23 dict[str, Any] annotations for a JSON document with known keys.",
                   "Key strings are repeated across merge/apply/diff functions."],
                  "Define TypedDicts (or dataclasses) for the LM Studio defaults document, duel payload and host guard state.",
                  impact="module", fix="multi_file_refactor"),
            issue("type_safety", "enum_bypass",
                  "Raw string literals bypass phase/stage/status enums",
                  ["lm_optimizer/services/optimizer.py", "lm_optimizer/cli/main.py"],
                  ["The enum bypass census reports 30 comparisons against raw strings.",
                   "Skip-phase handling compares strings such as 'quality' instead of OptimizationPhase members in places."],
                  "Normalize input once into enum members (parse_phase_skips) and compare enums internally; keep strings only at CLI/JSON boundaries.",
                  confidence="medium", impact="module", fix="multi_file_refactor"),
        ],
    },
    "naming_quality": {
        "score": 79.0,
        "evidence": [
            "Domain vocabulary remains strong: model, run, configuration, phase, stage, winner, finalist, ladder are used consistently.",
            "The duplicate OptimizationState class was removed with the legacy engine, so the canonical name is unambiguous.",
            "cli/main.py still uses optimize (603 lines), _optimize (185), _run_optimization (55), auto (603) and _auto (402) for different layers of the same workflow.",
            "tools/ still has campaign-shorthand names such as speed16k_part2.py and swift_runs.py.",
        ],
        "character": "Names usually predict behavior and the duplicate type name is gone. The remaining friction is overloaded workflow verbs in the CLI and ad-hoc tool script names.",
        "rationale": "Removing the duplicate OptimizationState resolves the clearest naming ambiguity. Overloaded optimize/auto verbs and tool shorthand keep it below strong.",
        "issues": [
            issue("naming_quality", "overloaded_optimize_auto",
                  "optimize/auto names are reused for commands and internal workflow bodies",
                  ["lm_optimizer/cli/main.py"],
                  ["optimize and auto are 603-line Typer command functions.",
                   "_optimize and _auto are separate 185/402-line helpers, and _run_optimization is a third layer."],
                  "Rename internal helpers by responsibility and keep command names for the CLI surface only.",
                  impact="module", fix="single_edit"),
            issue("naming_quality", "generic_tool_script_names",
                  "Tool scripts use campaign shorthand instead of purpose names",
                  ["tools/speed16k_part2.py", "tools/swift_runs.py", "tools/full_standard_rest.py"],
                  ["The tools/ directory contains 39 scripts named after one-off campaigns.",
                   "A reader cannot tell from the name which script is still useful or what input it expects."],
                  "Rename durable scripts by action and target and archive one-off campaign scripts under tools/archive/ with a README.",
                  confidence="medium", impact="local", fix="multi_file_refactor"),
        ],
    },
    "initialization_coupling": {
        "score": 67.0,
        "evidence": [
            "setup_logging is now called only under web_main's __main__ guard; importing logging_config no longer creates log directories.",
            "api/routes.py still keeps _current_optimizer and _current_run_id in module-level globals mutated by handlers.",
            "api/main.py still performs route re-registration and late imports at module scope to work around include_router.",
            "config remains a module-level pydantic-settings singleton imported by 33 modules.",
        ],
        "character": "Boot order is less surprising now that logging setup is explicit at the entrypoint. The API layer still couples requests to process-global run state and performs import-time route surgery.",
        "rationale": "Removing the import-time logging side effect is a real fix. Module-level current-run state and route registration keep the dimension solid but uneven.",
        "issues": [
            issue("initialization_coupling", "module_level_mutable_api_state",
                  "API routes keep current optimizer/run in module-level globals",
                  ["lm_optimizer/api/routes.py"],
                  ["_current_optimizer and _current_run_id are assigned inside request handlers and read by later requests.",
                   "The scan reports 5 mutations of module-level state in this file."],
                  "Move current-run state into app.state or a small RunRegistry created in the lifespan hook and injected via dependency.",
                  impact="module", fix="multi_file_refactor"),
            issue("initialization_coupling", "import_time_route_surgery",
                  "api/main.py rewrites the route table at import time",
                  ["lm_optimizer/api/main.py"],
                  ["Lines 63-106 manually recreate and filter APIRoutes because include_router was reported broken.",
                   "Late imports inside the module add hidden initialization order."],
                  "Use a supported include_router pattern, move optional routers into a registration function called from the lifespan hook, and assert the final route table in a test.",
                  confidence="medium", impact="module", fix="multi_file_refactor"),
        ],
    },
}


for idx, entry in DATA.items():
    dim = entry["dim"]
    effective = dict(entry)
    override = OVERRIDES.get(dim)
    if override:
        effective.update(override)
    issues = [
        item for item in effective["issues"]
        if item["identifier"] not in RESOLVED
    ]
    payload = {
        "batch": dim,
        "batch_index": idx,
        "assessments": {dim: effective["score"]},
        "dimension_notes": {
            dim: {
                "evidence": effective["evidence"],
                "impact_scope": "codebase" if effective["score"] < 62 else "subsystem",
                "fix_scope": "multi_file_refactor",
                "confidence": "high" if effective["score"] < 65 else "medium",
                "issues_preventing_higher_score": effective["rationale"],
            }
        },
        "dimension_judgment": {
            dim: {
                "dimension_character": effective["character"],
                "score_rationale": effective["rationale"],
            }
        },
        "issues": issues,
        "context_updates": {dim: effective["updates"]},
    }
    path = RUN / f"batch-{idx}.raw.txt"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    print(f"wrote {path} ({dim}, score {effective['score']}, issues {len(issues)})")

print("done")
