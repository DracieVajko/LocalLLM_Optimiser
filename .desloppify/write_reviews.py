"""Write desloppify review batch results (authored from code evidence)."""

import json
from pathlib import Path

RUN = Path(".desloppify/subagents/runs/20261103_123745/results")
RUN.mkdir(parents=True, exist_ok=True)


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


DATA = {}

# --------------------------------------------------------------------------
DATA[1] = {
    "dim": "cross_module_architecture",
    "score": 57.0,
    "evidence": [
        "Two import cycles are detected: cli/__init__.py <-> cli/main.py and optimizer/engine.py <-> storage/checkpoint.py.",
        "domain/models.py is imported by 112 modules and logging_config.py by 43; services/optimizer.py is imported by 41, so changes there have a very large blast radius.",
        "lm_optimizer/services/ holds 29,278 LOC (98.4% of package LOC) and mixes orchestration, backends, persistence, reporting and UI helpers in one flat package.",
        "A deprecated parallel stack (ui/web.py, optimizer/engine.py, storage/checkpoint.py, api/client.py) is still imported by discovery/inspector.py and several tests.",
    ],
    "character": "The import graph has two real cycles and a small number of very high fan-in hubs, while the largest package is a flat grab bag of unrelated concerns. A developer cannot rely on dependency direction to tell them what may change independently.",
    "rationale": "The domain model as shared vocabulary is reasonable, and the backend seam is explicit, but cycles, hub modules and a 29k-LOC flat services package make boundaries unreliable. This is a significant structural drag rather than an isolated rough edge.",
    "issues": [
        issue(
            "cross_module_architecture",
            "cli_init_cycle",
            "cli/__init__.py re-exports app from cli/main.py, creating a package-level import cycle",
            ["lm_optimizer/cli/__init__.py", "lm_optimizer/cli/main.py"],
            ["cli/__init__.py does `from .main import app as cli_app`.",
             "cli/main.py imports other cli modules, so importing any cli submodule initializes the package entrypoint first."],
            "Keep cli/__init__.py free of re-exports (docstring only) or move the Typer app object to cli/app.py and have main import it; callers should import from the concrete module.",
        ),
        issue(
            "cross_module_architecture",
            "legacy_engine_checkpoint_cycle",
            "Legacy optimizer engine and checkpoint module import each other",
            ["lm_optimizer/optimizer/engine.py", "lm_optimizer/storage/checkpoint.py"],
            ["engine.py imports CheckpointManager from storage/checkpoint.py.",
             "checkpoint.py imports OptimizationState from optimizer/engine.py under TYPE_CHECKING."],
            "Move the shared OptimizationState/result types into optimizer/types.py (or domain), have both modules import that, and delete the legacy engine/checkpoint pair once callers migrate.",
        ),
        issue(
            "cross_module_architecture",
            "services_flat_grab_bag",
            "services/ is a flat 29k-LOC package with no capability boundaries",
            ["lm_optimizer/services/optimizer.py", "lm_optimizer/services/benchmark.py", "lm_optimizer/services/reporting.py", "lm_optimizer/services/lm_studio.py"],
            ["251 structural issues are attributed to lm_optimizer/services.",
             "The directory mixes phase orchestration (optimizer.py), benchmarking (benchmark.py), reporting (reporting.py), host lifecycle (lm_studio.py) and UI support (recommender.py)."],
            "Split services/ into purpose-named subpackages (orchestration, benchmarking, persistence, reporting, host_lifecycle) and move modules; this is a multi-step refactor that should preserve public import paths with a temporary facade.",
            impact="codebase",
            fix="architectural_change",
        ),
        issue(
            "cross_module_architecture",
            "domain_hub_module",
            "domain/models.py is a 112-importer hub that combines every aggregate",
            ["lm_optimizer/domain/models.py"],
            ["The file defines hardware, model identity, benchmark cases, load configuration, quality scores, runs and profile weights in 683 LOC.",
             "Any change to one model forces a rebuild of the import graph for 112 modules."],
            "Split domain/models.py by aggregate (hardware.py, configuration.py, benchmark.py, run.py) and re-export from domain/__init__.py during migration.",
            confidence="medium",
            impact="codebase",
            fix="multi_file_refactor",
        ),
    ],
    "updates": {
        "add": [
            {"header": "Explicit backend seam", "description": "backends/base.py defines BackendClient and assert_conforms, and OllamaClient implements the seam; backend-specific code is not spread through the domain.", "settled": True, "positive": True},
            {"header": "Single authoritative web app", "description": "web_main.py launches api.main:app, and ui/web.py is explicitly marked as deprecated reference code, so the current entrypoint is unambiguous.", "settled": True, "positive": True},
        ]
    },
}

# --------------------------------------------------------------------------
DATA[2] = {
    "dim": "high_level_elegance",
    "score": 61.0,
    "evidence": [
        "Two complete optimization stacks coexist: services/optimizer.py AdaptiveOptimizer (5,294 LOC) and optimizer/engine.py OptimizationEngine (806 LOC) with different state models.",
        "cli/main.py is 5,718 LOC and owns argument parsing, preflight, host lifecycle, phase orchestration, reporting and result rendering for 25+ commands.",
        "lm_optimizer/services/ is a flat 29k-LOC package instead of capability-aligned ownership boundaries.",
        "The repository still ships a deprecated ui/web.py plus its legacy client/engine/checkpoint dependencies.",
    ],
    "character": "Ownership is blurred because the codebase contains two generations of the optimizer and a CLI that is also a UI layer. A new engineer would struggle to say which module owns orchestration, which owns presentation, and which is dead legacy.",
    "rationale": "The phase vocabulary and the FastAPI entrypoint give some shape, but the coexistence of two engines and the monolithic CLI undermine top-level decomposition. This is mixed quality with a significant drag rather than a merely uneven surface.",
    "issues": [
        issue(
            "high_level_elegance",
            "two_optimization_engines",
            "Two optimization engines own overlapping responsibilities",
            ["lm_optimizer/services/optimizer.py", "lm_optimizer/optimizer/engine.py"],
            ["services/optimizer.py defines AdaptiveOptimizer, OptimizationState and the phase pipeline used by CLI/API.",
             "optimizer/engine.py defines OptimizationEngine, its own OptimizationStage/State/Result and is only kept for backward compatibility."],
            "Delete the legacy engine after migrating its three importers, or demote it to a thin adapter over AdaptiveOptimizer; keep one orchestration owner.",
            impact="codebase",
            fix="architectural_change",
        ),
        issue(
            "high_level_elegance",
            "cli_monolith",
            "cli/main.py mixes command parsing with application orchestration and rendering",
            ["lm_optimizer/cli/main.py"],
            ["The file is 5,718 LOC and contains the 603-line optimize and auto command bodies, 244-line preflight, and 362-line result renderer.",
             "Preflight, host lifecycle and report generation are reusable operations but live inside the CLI module."],
            "Extract preflight/host lifecycle into services and move command bodies into cli/commands/* modules; keep main.py to Typer registration and output composition.",
            impact="subsystem",
            fix="multi_file_refactor",
        ),
        issue(
            "high_level_elegance",
            "flat_services_ownership",
            "No capability-level ownership inside services/",
            ["lm_optimizer/services/optimizer.py", "lm_optimizer/services/benchmark.py", "lm_optimizer/services/reporting.py"],
            ["A single flat directory contains orchestration, benchmark execution, report rendering, host defaults and recommendation logic.",
             "Structural debt by area reports 251 items in lm_optimizer/services."],
            "Group services by capability and make each subpackage expose a small __init__ API; move reporting/UI formatting out of orchestration modules.",
            impact="codebase",
            fix="architectural_change",
        ),
    ],
    "updates": {
        "add": [
            {"header": "Documented authoritative entrypoint", "description": "The deprecated ui/web.py docstring names api.main:app as authoritative, which prevents a new engineer from wiring the wrong app.", "settled": True, "positive": True},
            {"header": "Phase vocabulary is explicit", "description": "OptimizationPhase/OptimizationStage enumerate the pipeline stages instead of relying on implicit string flow, which gives the orchestration a readable spine.", "settled": True, "positive": True},
        ]
    },
}

# --------------------------------------------------------------------------
DATA[3] = {
    "dim": "convention_outlier",
    "score": 73.0,
    "evidence": [
        "snake_case is consistent across all 1,666 detected names and every package directory.",
        "Domain objects mix dataclasses (domain/models.py), Pydantic models (api/schemas.py) and plain dicts (advanced settings) without a documented rule.",
        "print() is used 571 times (421 in cli/main.py, 108 in cli/lab.py) while the rest of the codebase uses structlog; services/optimizer.py and community_benchmarks.py also print.",
        "Tests are split across tests/ (62 files) and lm_optimizer/tests/ (70 files) with different fixture styles.",
    ],
    "character": "File and symbol naming follows one convention almost everywhere, so navigation by name is reliable. The outliers are not lexical but structural: type strategy, output mechanism and test layout change by directory without an explicit rule.",
    "rationale": "Consistent snake_case and mirrored test names keep the score solid, but mixed domain-object strategies, service-layer print calls and two test roots create recurring 'why is this different?' moments. This fits the upper end of solid-but-uneven.",
    "issues": [
        issue(
            "convention_outlier",
            "mixed_domain_type_strategies",
            "Domain objects use three different type strategies without a documented boundary",
            ["lm_optimizer/domain/models.py", "lm_optimizer/api/schemas.py", "lm_optimizer/services/benchmark.py"],
            ["domain/models.py uses dataclasses for runs/configurations.",
             "api/schemas.py uses Pydantic BaseModel for the same concepts at the HTTP edge.",
             "BenchmarkConfig is a dataclass with mutable defaults while request settings are dicts."],
            "Document the rule: dataclasses for internal aggregates, Pydantic only at the HTTP boundary, and a typed config object instead of raw dicts; apply it to BenchmarkConfig and advanced settings.",
            confidence="medium",
            impact="subsystem",
            fix="multi_file_refactor",
        ),
        issue(
            "convention_outlier",
            "service_print_instead_of_logging",
            "Service modules print to stdout instead of using structured logging",
            ["lm_optimizer/services/optimizer.py", "lm_optimizer/services/community_benchmarks.py", "lm_optimizer/services/deepresearch.py"],
            ["services/optimizer.py contains 5 print() calls; community_benchmarks.py contains 8; deepresearch.py contains 4.",
             "The rest of the codebase uses get_logger(...) and structured events."],
            "Replace service-layer print() with logger.info/debug and keep print only in CLI command handlers; console output should be a presentation concern.",
            confidence="high",
            impact="module",
            fix="single_edit",
        ),
        issue(
            "convention_outlier",
            "two_test_roots",
            "Tests live in two roots with different layout and fixture conventions",
            ["tests/test_benchmark_cache.py", "lm_optimizer/tests/test_core.py", "pyproject.toml"],
            ["pyproject testpaths includes both lm_optimizer/tests and tests.",
             "The two roots use different import styles and fixture organization for the same services."],
            "Pick one root (tests/) and migrate lm_optimizer/tests in batches, or document the split explicitly (unit vs integration) and enforce it in pytest markers.",
            confidence="medium",
            impact="subsystem",
            fix="multi_file_refactor",
        ),
    ],
    "updates": {
        "add": [
            {"header": "Consistent snake_case", "description": "1,666 detected names across all packages use snake_case, so lexical convention is not a source of friction.", "settled": True, "positive": True},
            {"header": "Mirrored test module names", "description": "Most test modules are named after the production module they cover, which makes coverage discovery predictable.", "settled": True, "positive": True},
        ]
    },
}

# --------------------------------------------------------------------------
DATA[4] = {
    "dim": "error_consistency",
    "score": 63.0,
    "evidence": [
        "522 'except Exception' handlers across 63 production files; 153 of them swallow the error with 'pass'.",
        "Silent-pass counts are concentrated in services/optimizer.py (41), api/routes.py (29) and cli/main.py (14).",
        "Strategy census mixes try/catch (352 in services), throws (140) and returns_null (90) with only 5 Result-type paths.",
        "Repositories commonly return None (7) while clients raise, and API handlers convert both into heterogeneous HTTP responses.",
    ],
    "character": "Error handling is defensive almost everywhere: broad catches and silent passes keep long-running optimization loops alive, but they also hide the cause and make failure modes depend on the call site. Predictability is low at module boundaries.",
    "rationale": "The per-case success flag in benchmarking is a good containment pattern, but 153 silent passes and mixed raise/None/Result strategies dominate. A developer cannot reliably predict whether a failed load, benchmark or persistence call throws, returns None or is swallowed.",
    "issues": [
        issue(
            "error_consistency",
            "silent_pass_concentration",
            "153 broad catches swallow errors with pass, concentrated in orchestration modules",
            ["lm_optimizer/services/optimizer.py", "lm_optimizer/api/routes.py", "lm_optimizer/cli/main.py"],
            ["optimizer.py has 41 'except ...: pass' blocks; routes.py has 29; cli/main.py has 14.",
             "These cover cleanup, persistence and optional enrichment paths without logging the exception."],
            "Introduce a small helper that logs at debug/warning with exc_info and use it for tolerated failures; reserve bare pass for documented idempotent cleanup.",
            impact="subsystem",
            fix="multi_file_refactor",
        ),
        issue(
            "error_consistency",
            "mixed_failure_contracts",
            "Related modules mix raising, returning None and success flags",
            ["lm_optimizer/services/lm_studio.py", "lm_optimizer/services/benchmark.py", "lm_optimizer/database/repositories.py"],
            ["LM Studio client methods raise on transport failure.",
             "Repositories return None for missing rows.",
             "BenchmarkService returns BenchmarkMetrics with success=False for case failures."],
            "Document the layer contract (clients raise, services return outcome objects, repositories return None) and apply it consistently; expose a shared Result/outcome type for benchmark and load operations.",
            confidence="medium",
            impact="subsystem",
            fix="multi_file_refactor",
        ),
        issue(
            "error_consistency",
            "api_error_translation",
            "API handlers translate the same underlying failures into ad-hoc HTTP responses",
            ["lm_optimizer/api/routes.py"],
            ["Handlers catch Exception and raise HTTPException with status 500 and truncated str(e) in several places.",
             "Other handlers let exceptions propagate to FastAPI defaults, producing a different response shape."],
            "Add a single exception-to-HTTP mapping layer or middleware and use typed domain exceptions; keep detail strings out of 500 responses.",
            confidence="medium",
            impact="module",
            fix="multi_file_refactor",
        ),
    ],
    "updates": {
        "add": [
            {"header": "Per-case benchmark outcomes", "description": "BenchmarkService records success=False and an error per case instead of aborting the whole sweep, which keeps one bad prompt from losing a run.", "settled": True, "positive": True},
            {"header": "Checkpoint-before-cancel", "description": "Cancellation paths explicitly checkpoint state before unwinding, preserving recoverability across failures.", "settled": True, "positive": True},
        ]
    },
}

# --------------------------------------------------------------------------
DATA[5] = {
    "dim": "naming_quality",
    "score": 77.0,
    "evidence": [
        "Domain vocabulary is strong: model, run, configuration, phase, stage, winner, finalist, ladder are used consistently.",
        "The name OptimizationState is defined twice (services/optimizer.py and optimizer/engine.py) with different fields, so imports are ambiguous.",
        "cli/main.py uses optimize (603 lines), _optimize (185), _run_optimization (55), auto (603) and _auto (402) for different layers of the same workflow.",
        "Generic helpers such as _require_backend, _handle_connection_error and _connect_guarded communicate intent reasonably; tools/ has ad-hoc names like speed16k_part2.py and swift_runs.py.",
    ],
    "character": "Names usually predict behavior and the domain vocabulary is coherent, which is the main strength. The friction comes from duplicated type names across generations and from overloaded workflow verbs in the CLI, where 'optimize' and 'auto' mean both the command and the internal routine.",
    "rationale": "Most names are precise enough to read without opening the implementation, so the score remains solid. Duplicate OptimizationState definitions and overloaded optimize/auto verbs pull it down because they force a reader to check which layer a symbol belongs to.",
    "issues": [
        issue(
            "naming_quality",
            "duplicate_optimization_state",
            "OptimizationState names two unrelated classes",
            ["lm_optimizer/services/optimizer.py", "lm_optimizer/optimizer/engine.py"],
            ["services/optimizer.py:620 defines OptimizationState for the adaptive run.",
             "optimizer/engine.py:42 defines a different OptimizationState for the legacy engine."],
            "Rename the legacy class LegacyOptimizationState (or delete it with the legacy stack) so the canonical state has an unambiguous name.",
        ),
        issue(
            "naming_quality",
            "overloaded_optimize_auto",
            "optimize/auto names are reused for commands and internal workflow bodies",
            ["lm_optimizer/cli/main.py"],
            ["optimize and auto are 603-line Typer command functions.",
             "_optimize and _auto are separate 185/402-line helpers, and _run_optimization is a third layer."],
            "Rename internal helpers by responsibility (e.g. _prepare_optimization, _execute_optimization, _render_optimization_result) and keep command names for the CLI surface only.",
            impact="module",
            fix="single_edit",
        ),
        issue(
            "naming_quality",
            "generic_tool_script_names",
            "Tool scripts use campaign shorthand instead of purpose names",
            ["tools/speed16k_part2.py", "tools/swift_runs.py", "tools/full_standard_rest.py"],
            ["The tools/ directory contains 39 scripts named after one-off campaigns (speed16k_*, swift_*).",
             "A reader cannot tell from the name which script is still useful or what input it expects."],
            "Rename durable scripts by action and target (e.g. benchmark_16k_suite.py) and archive one-off campaign scripts under tools/archive/ with a README.",
            confidence="medium",
            impact="local",
            fix="multi_file_refactor",
        ),
    ],
    "updates": {
        "add": [
            {"header": "Stable domain vocabulary", "description": "Terms such as run, configuration, phase, winner and ladder are used consistently across CLI, API and services, so domain names transfer between layers.", "settled": True, "positive": True},
        ]
    },
}

# --------------------------------------------------------------------------
DATA[6] = {
    "dim": "abstraction_fitness",
    "score": 65.0,
    "evidence": [
        "The abstraction census reports 20 facade modules, 26 pass-through wrappers, 51 indirection hotspots and 60 wide parameter bags.",
        "api/routes.py defines _convert_model/_convert_hardware/_convert_config/_convert_preset that only map domain objects to Pydantic schemas.",
        "Advanced settings travel as an untyped dict through prepare_run, execute and _test_config, so every consumer re-implements key lookup and defaults.",
        "77 dict[str, Any] annotations remain, concentrated in lmstudio_defaults.py (23), duel.py (11) and hostguard.py (8).",
    ],
    "character": "Most abstractions are direct domain helpers, but the codebase also carries a layer of adapter dicts and conversion wrappers that exist only to move data between representations. The cost is paid at every boundary, especially around settings and API serialization.",
    "rationale": "The backend seam and explicit phase helpers are earned abstractions, but wide dict parameter bags and conversion wrappers add navigation without adding policy. That is a recurring indirection cost, placing this in mixed territory.",
    "issues": [
        issue(
            "abstraction_fitness",
            "advanced_settings_bag",
            "Advanced settings are an untyped dict threaded through orchestration",
            ["lm_optimizer/services/optimizer.py", "lm_optimizer/api/routes.py", "lm_optimizer/services/benchmark.py"],
            ["prepare_run/execute/_test_config accept advanced_settings: dict and read keys with .get(...) defaults.",
             "CLI, API and auto-run each construct the dict independently, so a missing key behaves differently by entrypoint."],
            "Replace the dict with a typed AdvancedSettings dataclass/Pydantic model at the entrypoint, then pass the model inward; this removes repeated default logic and makes the contract explicit.",
            impact="subsystem",
            fix="multi_file_refactor",
        ),
        issue(
            "abstraction_fitness",
            "api_convert_wrappers",
            "API conversion helpers only forward fields into schemas",
            ["lm_optimizer/api/routes.py"],
            ["_convert_model, _convert_hardware, _convert_config and _convert_preset are thin field-by-field mappers.",
             "They add a second place to update whenever a domain field changes."],
            "Use Pydantic model_validate with from_attributes=True or schema constructors at the boundary, and keep only conversions that add policy (masking secrets, deriving metrics).",
            confidence="medium",
            impact="module",
            fix="single_edit",
        ),
        issue(
            "abstraction_fitness",
            "dict_any_defaults",
            "Config/defaults modules rely on dict[str, Any] instead of typed structures",
            ["lm_optimizer/services/lmstudio_defaults.py", "lm_optimizer/services/duel.py", "lm_optimizer/services/hostguard.py"],
            ["lmstudio_defaults.py has 23 dict[str, Any] annotations; duel.py 11; hostguard.py 8.",
             "Key names are string literals repeated across read/merge/apply/restore functions."],
            "Introduce TypedDicts or dataclasses for the LM Studio defaults document and duel payloads; keep raw dicts only at the JSON edge.",
            confidence="medium",
            impact="module",
            fix="multi_file_refactor",
        ),
    ],
    "updates": {
        "add": [
            {"header": "Backend seam has real implementations", "description": "The BackendClient protocol is implemented by OllamaClient and exercised by conformance checks, so the abstraction has more than one consumer.", "settled": True, "positive": True},
            {"header": "Phase helpers are policy-bearing", "description": "Functions such as parse_phase_skips and compose_granular_skips encode real skip semantics rather than forwarding arguments.", "settled": True, "positive": True},
        ]
    },
}

# --------------------------------------------------------------------------
DATA[7] = {
    "dim": "dependency_health",
    "score": 69.0,
    "evidence": [
        "Two import cycles remain in the package graph.",
        "GPUtil 1.4 is declared for GPU discovery but is unmaintained and emits a find_executable deprecation warning on Python 3.14.",
        "Dependencies are otherwise focused: httpx for HTTP, pydantic/pydantic-settings, FastAPI/uvicorn, Typer/Rich, structlog, numpy, psutil.",
        "No duplicate HTTP client library or duplicate settings framework was found.",
    ],
    "character": "The dependency set is small and mostly current, with clear roles for the CLI, API and HTTP layers. The main drag is the two cycles plus a legacy GPU helper whose maintenance status is poor.",
    "rationale": "A focused dependency list and no duplicate frameworks keep this dimension solid. Cycles and GPUtil keep it short of strong because both create avoidable upgrade and import-order risk.",
    "issues": [
        issue(
            "dependency_health",
            "gputil_deprecated",
            "GPUtil is unmaintained and only used for GPU discovery",
            ["pyproject.toml", "lm_optimizer/services/gpu_monitor.py"],
            ["pyproject declares GPUtil>=1.4.0.",
             "GPUtil imports distutils spawn.find_executable, which is deprecated on Python 3.14.",
             "gpu_monitor.py already shells out to nvidia-smi for the primary path."],
            "Remove GPUtil and parse nvidia-smi/psutil directly, or adopt pynvml if a library is required; this drops an unmaintained dependency.",
            confidence="high",
            impact="module",
            fix="single_edit",
        ),
        issue(
            "dependency_health",
            "remaining_import_cycles",
            "Two package cycles increase import-order fragility",
            ["lm_optimizer/cli/__init__.py", "lm_optimizer/cli/main.py", "lm_optimizer/optimizer/engine.py", "lm_optimizer/storage/checkpoint.py"],
            ["The cycles detector reports cli/__init__ <-> cli/main and engine <-> checkpoint.",
             "Both pairs are initialized during normal package imports."],
            "Break the cycles by moving shared types to leaf modules and keeping package __init__ files free of re-exports.",
        ),
    ],
    "updates": {
        "add": [
            {"header": "Focused dependency set", "description": "One HTTP client (httpx), one settings stack (pydantic-settings) and one CLI/UI stack (Typer/Rich + FastAPI) avoid duplicate-purpose libraries.", "settled": True, "positive": True},
        ]
    },
}

# --------------------------------------------------------------------------
DATA[8] = {
    "dim": "low_level_elegance",
    "score": 67.0,
    "evidence": [
        "36 functions are at least 120 lines; the worst are cli/main.py optimize/auto (603 each), reporting.save_best_report (531) and optimizer._test_config (244).",
        "Broad catches and silent passes recur inside these long bodies, so side effects and recovery paths are interleaved with the happy path.",
        "Small helpers such as _looks_incomplete, _sample_mem and _extract_mtp_metrics are direct and readable.",
        "Some async functions perform synchronous work without awaits, and several loops mix persistence, logging and control flow in one block.",
    ],
    "character": "At the helper level the code is direct and readable, but the large orchestration functions accumulate loading, benchmarking, quality checks, persistence and rendering in a single body. A reader must hold many side effects in mind at once.",
    "rationale": "Extraction level is balanced in the small services but collapses in the CLI and reporting monoliths; edge-case handling is precise in helpers but becomes defensive sprawl in long functions. This is solid in places and a significant drag in the hot paths.",
    "issues": [
        issue(
            "low_level_elegance",
            "giant_command_bodies",
            "CLI command bodies mix parsing, preflight, orchestration and rendering",
            ["lm_optimizer/cli/main.py"],
            ["optimize and auto are each 603 lines; _auto is 402 and _display_optimization_result is 362.",
             "Each body performs several side-effecting phases sequentially with shared local state."],
            "Extract one function per phase (prepare, execute, persist, render) and keep the command body as a short composition; pass a small prepared-context object instead of a dozen locals.",
            impact="subsystem",
            fix="multi_file_refactor",
        ),
        issue(
            "low_level_elegance",
            "report_monolith",
            "Report generation is one 531-line function with many inline formatting branches",
            ["lm_optimizer/services/reporting.py"],
            ["save_best_report builds every section (header, config table, quality, ladder, presets, diagnostics) in one body.",
             "Section formatting is interleaved with data lookup and fallback handling."],
            "Split into section builders that each return lines, then compose them in save_best_report; this keeps formatting testable without changing output.",
            confidence="high",
            impact="module",
            fix="multi_file_refactor",
        ),
        issue(
            "low_level_elegance",
            "sync_work_in_async",
            "Async functions perform blocking work without awaits",
            ["lm_optimizer/api/routes.py", "lm_optimizer/services/optimizer.py"],
            ["Several async handlers call synchronous repository/file helpers directly.",
             "Long CPU-bound preparation runs on the event loop instead of a thread."],
            "Move blocking repository/file work to asyncio.to_thread or a background task where it can delay the event loop; keep pure in-memory work inline.",
            confidence="medium",
            impact="module",
            fix="multi_file_refactor",
        ),
    ],
    "updates": {
        "add": [
            {"header": "Small pure helpers", "description": "Helpers such as _looks_incomplete, _sample_mem and _extract_mtp_metrics are short, side-effect-light and easy to test.", "settled": True, "positive": True},
        ]
    },
}

# --------------------------------------------------------------------------
DATA[9] = {
    "dim": "mid_level_elegance",
    "score": 61.0,
    "evidence": [
        "The advanced-settings dict is the main handoff object between CLI/API, optimizer and benchmark, with defaults re-applied at each layer.",
        "BenchmarkService is constructed separately in cli/main.py and api/routes.py with overlapping but not identical arguments, which previously produced CLI/UI parity gaps.",
        "prepare_run returns (run, baseline_config, advanced_settings) and execute takes the same dict again, so the boundary contract is implicit.",
        "API conversion happens through ad-hoc mappers plus dict enrichment (_enrich_config_detail) rather than one translation seam.",
    ],
    "character": "Module boundaries exist, but the data that crosses them is mostly raw dictionaries and tuples. Handoffs work, yet each layer must re-interpret the same keys, which makes integration seams fragile and duplicates policy.",
    "rationale": "The phase pipeline and the shared domain models give the integration some structure, but implicit dict handoffs and duplicated service construction make the seams harder to trust than the internals. This is mixed quality with recurring friction.",
    "issues": [
        issue(
            "mid_level_elegance",
            "implicit_settings_handoff",
            "Settings cross the CLI/API -> optimizer -> benchmark boundaries as an untyped dict",
            ["lm_optimizer/services/optimizer.py", "lm_optimizer/api/routes.py", "lm_optimizer/cli/main.py"],
            ["prepare_run/execute accept advanced_settings: dict.",
             "Each layer reads different keys and applies its own defaults."],
            "Define one AdvancedSettings model at the outer boundary, validate once, and pass it through; remove per-layer .get default logic.",
            impact="subsystem",
            fix="multi_file_refactor",
        ),
        issue(
            "mid_level_elegance",
            "duplicated_service_wiring",
            "BenchmarkService wiring is duplicated between CLI and API",
            ["lm_optimizer/cli/main.py", "lm_optimizer/api/routes.py"],
            ["Both entrypoints construct BenchmarkService and translate settings into config fields.",
             "The two argument lists drifted, which required a dedicated parity fix."],
            "Create a factory (build_benchmark_service(settings)) in services and call it from both entrypoints so defaults and flags cannot diverge.",
            confidence="high",
            impact="subsystem",
            fix="multi_file_refactor",
        ),
        issue(
            "mid_level_elegance",
            "ad_hoc_boundary_mapping",
            "API response mapping is split between converters and dict enrichment",
            ["lm_optimizer/api/routes.py"],
            ["_convert_config_result builds a schema, then _enrich_config_detail mutates its dict form with extra keys.",
             "Different endpoints apply different subsets of enrichment."],
            "Move enrichment into the schema/converter or a single presenter function, and return one response shape per resource.",
            confidence="medium",
            impact="module",
            fix="multi_file_refactor",
        ),
    ],
    "updates": {
        "add": [
            {"header": "Explicit phase pipeline", "description": "The optimizer exposes ordered phases and skip names, so the CLI/API handoff for phase control is at least named and testable.", "settled": True, "positive": True},
        ]
    },
}

# --------------------------------------------------------------------------
DATA[10] = {
    "dim": "test_strategy",
    "score": 73.0,
    "evidence": [
        "The suite has roughly 1,490 tests and completes in about five minutes, giving fast feedback for a project of this size.",
        "Two critical modules are untested according to the scan: optimizer/engine.py and storage/checkpoint.py (3 importers each).",
        "Tests are split across tests/ (62 files) and lm_optimizer/tests/ (70 files) with different fixture conventions.",
        "Most tests use fakes/monkeypatching rather than live servers, which keeps them deterministic but leaves some HTTP/load paths covered only by integration-style fakes.",
    ],
    "character": "Test coverage is broad and the suite is fast, so developers get real feedback. The gaps are structural: the legacy engine/checkpoint path is untested, and the two-root layout makes it unclear which tests are the canonical regression suite.",
    "rationale": "A large, fast suite with targeted phase and parity tests is a clear strength. Untested critical modules and duplicated test roots keep it from strong, because the safety net does not cover the code that is being retired.",
    "issues": [
        issue(
            "test_strategy",
            "untested_legacy_core",
            "Legacy engine and checkpoint modules have no direct tests",
            ["lm_optimizer/optimizer/engine.py", "lm_optimizer/storage/checkpoint.py"],
            ["The scan lists both as critical_untested with 3 importers.",
             "They are the compatibility path for ui/web.py and are still imported during test collection."],
            "Either add characterization tests before deleting them, or remove the legacy stack and its imports so the critical untested surface disappears.",
            impact="subsystem",
            fix="multi_file_refactor",
        ),
        issue(
            "test_strategy",
            "split_test_roots",
            "Two test roots with different conventions obscure the canonical suite",
            ["tests/test_benchmark_cache.py", "lm_optimizer/tests/test_core.py", "pyproject.toml"],
            ["testpaths includes both roots.",
             "Fixture setup and import style differ between them."],
            "Consolidate into tests/ by domain, or document and enforce the split with pytest markers (unit vs integration) and a CI matrix.",
            confidence="medium",
            impact="subsystem",
            fix="multi_file_refactor",
        ),
        issue(
            "test_strategy",
            "live_path_coverage",
            "Server-load and host-lifecycle paths are covered only by fakes",
            ["lm_optimizer/services/lm_studio.py", "tests/test_load_timeout_fallback.py"],
            ["Load-response loss and echo-probe failures required new fallback tests after live findings.",
             "Most coverage uses monkeypatched clients rather than a fake HTTP transport."],
            "Add httpx.MockTransport-based contract tests for the LM Studio and Ollama clients covering timeout, 4xx/5xx and malformed payloads.",
            confidence="medium",
            impact="module",
            fix="multi_file_refactor",
        ),
    ],
    "updates": {
        "add": [
            {"header": "Fast broad regression suite", "description": "About 1,490 tests run in roughly five minutes, covering phases, scoring, persistence and CLI/UI parity.", "settled": True, "positive": True},
            {"header": "Targeted regression tests for live findings", "description": "Load-response loss, echo-probe cleanup and context-speed ladder retries each gained a dedicated test after being found live.", "settled": True, "positive": True},
        ]
    },
}

# --------------------------------------------------------------------------
DATA[11] = {
    "dim": "api_surface_coherence",
    "score": 66.0,
    "evidence": [
        "api/routes.py defines 62 route handlers but only 12 declare a response_model.",
        "The remaining handlers return raw dicts, so the public schema is not visible in OpenAPI and changes silently.",
        "The API mixes async and sync handlers and uses heterogeneous error shapes (HTTPException detail vs default FastAPI validation).",
        "api/main.py manually re-registers routes at import time because include_router was reported broken, duplicating the router surface.",
    ],
    "character": "The API is broad and mostly REST-shaped, but its response contracts are inconsistent: some endpoints are typed, most are not. A client developer cannot rely on the generated schema or on a single error envelope.",
    "rationale": "Pydantic schemas exist for the core run/settings/comparison endpoints, which keeps the score solid, but 50 untyped handlers and the manual router surgery are recurring friction. This is solid but uneven rather than coherent.",
    "issues": [
        issue(
            "api_surface_coherence",
            "untyped_responses",
            "Most API handlers return untyped dicts instead of response models",
            ["lm_optimizer/api/routes.py", "lm_optimizer/api/schemas.py"],
            ["Only 12 of 62 @router handlers set response_model.",
             "Handlers such as list_models, get_status and get_runs build dicts inline."],
            "Add response_model (or typed return annotations) to every public handler and move inline dict construction into schemas/presenters.",
            impact="subsystem",
            fix="multi_file_refactor",
        ),
        issue(
            "api_surface_coherence",
            "manual_router_registration",
            "Routes are re-registered manually at import time in api/main.py",
            ["lm_optimizer/api/main.py"],
            ["Comments at lines 63-106 describe recreating routes because include_router failed.",
             "The workaround duplicates APIRoute handling and makes route ownership hard to follow."],
            "Pin the FastAPI version that works, use include_router normally, and add a startup assertion that the expected route count/prefixes exist.",
            confidence="medium",
            impact="module",
            fix="single_edit",
        ),
        issue(
            "api_surface_coherence",
            "mixed_sync_async_handlers",
            "Similar endpoints mix sync and async handlers",
            ["lm_optimizer/api/routes.py", "lm_optimizer/api/main.py"],
            ["Some handlers are async def, others are def, including endpoints that perform the same repository/file work.",
             "Blocking work in async handlers can stall the event loop."],
            "Standardize on async handlers for I/O endpoints and use def only for purely CPU-bound short handlers; document the rule.",
            confidence="medium",
            impact="module",
            fix="multi_file_refactor",
        ),
    ],
    "updates": {
        "add": [
            {"header": "Typed core contracts", "description": "Run, settings, compare, sandbox and judge endpoints use Pydantic response models, giving the most important payloads a stable schema.", "settled": True, "positive": True},
        ]
    },
}

# --------------------------------------------------------------------------
DATA[12] = {
    "dim": "authorization_consistency",
    "score": 59.0,
    "evidence": [
        "All 62 API routes in api/routes.py and all 8 handlers in ui/web.py have no authentication dependency.",
        "No RLS or per-table access control is present; the SQLite repositories are called directly.",
        "The default bind address is 127.0.0.1 with CORS restricted to localhost:8080, which limits exposure but is not an authorization boundary.",
        "Some endpoints mutate host state (apply defaults, delete runs, cancel jobs), so unauthenticated access is not read-only.",
    ],
    "character": "Authorization is uniformly absent rather than inconsistently applied: the app is a localhost tool, and every route trusts the local caller. Within that model the behavior is predictable, but the trust boundary is implicit and not documented at the API surface.",
    "rationale": "Consistent local-only binding and restrictive CORS are meaningful mitigations, so this is not a poor score. But state-changing endpoints with no auth, no token, and no documented local-only contract keep authorization quality below solid.",
    "issues": [
        issue(
            "authorization_consistency",
            "no_route_auth",
            "No API route enforces or documents an authentication boundary",
            ["lm_optimizer/api/routes.py", "lm_optimizer/api/main.py"],
            ["route_auth_coverage reports 0 authenticated handlers out of 62 in routes.py and 11 in main.py.",
             "State-changing endpoints include /apply, /runs/{id}/save-default and /runs/{id}/delete."],
            "Either add a local API token (generated at startup, required by mutating routes) or document the localhost-only threat model and enforce it with a startup host check that refuses non-loopback binds.",
            confidence="high",
            impact="codebase",
            fix="multi_file_refactor",
        ),
        issue(
            "authorization_consistency",
            "implicit_localhost_trust",
            "Localhost binding is the only access control and is not enforced at startup",
            ["lm_optimizer/config.py", "lm_optimizer/web_main.py"],
            ["config.web_ui.host defaults to 127.0.0.1 but can be overridden by environment.",
             "No startup guard rejects a non-loopback host or warns about unauthenticated exposure."],
            "Add a startup check: if host is not loopback and no API token is configured, refuse to start or require an explicit allow-remote flag.",
            confidence="high",
            impact="module",
            fix="single_edit",
        ),
        issue(
            "authorization_consistency",
            "no_audit_log_for_mutations",
            "State-changing actions are not audit-logged",
            ["lm_optimizer/api/routes.py", "lm_optimizer/services/lmstudio_defaults.py"],
            ["Apply/restore/save-default endpoints mutate LM Studio and Ollama configuration files.",
             "There is no record of which run or caller triggered the change."],
            "Log a structured audit event (action, model, run id, old/new config hash) for every apply/restore/save-default operation.",
            confidence="medium",
            impact="module",
            fix="single_edit",
        ),
    ],
    "updates": {
        "add": [
            {"header": "Localhost-first defaults", "description": "The web UI binds 127.0.0.1 by default and CORS allows only localhost origins, reducing accidental network exposure.", "settled": True, "positive": True},
        ]
    },
}

# --------------------------------------------------------------------------
DATA[13] = {
    "dim": "ai_generated_debt",
    "score": 67.0,
    "evidence": [
        "The codebase comment ratio is 2.5%, so restating comments are not the main problem.",
        "Defensive overengineering is visible in 153 silent broad catches and repeated None/empty checks around typed values.",
        "Service-layer print() calls (optimizer.py 5, community_benchmarks.py 8, deepresearch.py 4) look like debug output left in production paths.",
        "Docstrings are generally short, but some large functions carry docstrings that describe only one of several responsibilities.",
    ],
    "character": "The code does not read like unedited generated output: comments are sparse and names are domain-specific. The debt is behavioral rather than cosmetic, mostly defensive exception handling and leftover console output in service paths.",
    "rationale": "Low comment noise and purposeful docstrings keep this above mixed. Silent broad catches and service print statements are the recurring LLM-ish residue, so the score sits in solid-but-uneven territory.",
    "issues": [
        issue(
            "ai_generated_debt",
            "defensive_silent_catches",
            "Defensive broad catches hide failures in service code",
            ["lm_optimizer/services/optimizer.py", "lm_optimizer/api/routes.py"],
            ["optimizer.py contains 41 'except ...: pass' blocks, many around optional enrichment/persistence.",
             "The pattern is copied across modules rather than centralized."],
            "Replace copied catches with one logged best-effort helper and let unexpected exceptions propagate; keep only documented tolerances.",
            impact="subsystem",
            fix="multi_file_refactor",
        ),
        issue(
            "ai_generated_debt",
            "service_print_debug",
            "Print statements remain in service modules",
            ["lm_optimizer/services/optimizer.py", "lm_optimizer/services/community_benchmarks.py", "lm_optimizer/services/deepresearch.py"],
            ["optimizer.py prints during long runs, bypassing structured logging.",
             "community_benchmarks.py and deepresearch.py print progress from service code."],
            "Use logger.info/debug with structured fields and let the CLI render user-facing output.",
            confidence="high",
            impact="module",
            fix="single_edit",
        ),
        issue(
            "ai_generated_debt",
            "docstring_scope_drift",
            "Docstrings on long functions describe only one responsibility",
            ["lm_optimizer/services/reporting.py", "lm_optimizer/services/optimizer.py"],
            ["save_best_report is documented as saving a report but also builds diagnostics, presets and ladder sections.",
             "_test_config documents loading but also benchmarks, scores and cleans up."],
            "Either split the function so the docstring is accurate, or expand the docstring to list all side effects and outputs.",
            confidence="medium",
            impact="local",
            fix="single_edit",
        ),
    ],
    "updates": {
        "add": [
            {"header": "Sparse, why-focused comments", "description": "The 2.5% comment ratio and short docstrings avoid restating code; comments generally explain constraints or intent.", "settled": True, "positive": True},
        ]
    },
}

# --------------------------------------------------------------------------
DATA[14] = {
    "dim": "incomplete_migration",
    "score": 49.0,
    "evidence": [
        "ui/web.py is explicitly marked DEPRECATED and says it will be removed in 2.0, yet it remains in the tree with its own FastAPI app.",
        "optimizer/engine.py says it is kept for backward compatibility and duplicates the adaptive optimizer.",
        "storage/checkpoint.py and benchmark/runner.py belong to the same legacy stack and are still imported by engine.py, ui/web.py and tests.",
        "discovery/inspector.py still imports LMStudioClient/LoadConfig/ModelInfo from api/client.py rather than services/lm_studio.py.",
    ],
    "character": "A full legacy stack coexists with the new one, and the migration is documented but not finished. Active modules still reach into the old client and engine, so the boundary between current and retired code is not real.",
    "rationale": "The new FastAPI app is clearly designated authoritative, which prevents total ambiguity, but deprecated code is still imported and executed by tests. This is a significant drag on maintainability and the clearest example of incomplete migration in the repo.",
    "issues": [
        issue(
            "incomplete_migration",
            "legacy_web_stack",
            "Deprecated ui/web.py and its legacy engine/checkpoint/client dependencies remain active",
            ["lm_optimizer/ui/web.py", "lm_optimizer/optimizer/engine.py", "lm_optimizer/storage/checkpoint.py"],
            ["ui/web.py is marked DEPRECATED but defines a second FastAPI app and 8 routes.",
             "It imports optimizer.engine, api.client, benchmark.runner and storage.checkpoint.",
             "engine.py is explicitly kept for backward compatibility with ui/web.py."],
            "Delete ui/web.py, optimizer/engine.py and storage/checkpoint.py after migrating their three importers; keep a release note for 2.0.",
            impact="codebase",
            fix="multi_file_refactor",
        ),
        issue(
            "incomplete_migration",
            "legacy_client_in_discovery",
            "discovery/inspector.py still uses the legacy api/client instead of the service client",
            ["lm_optimizer/discovery/inspector.py", "lm_optimizer/api/client.py", "lm_optimizer/services/lm_studio.py"],
            ["inspector.py imports LMStudioClient, LoadConfig and ModelInfo from api.client.",
             "The current host client lives in services/lm_studio.py."],
            "Port inspector.py to the service client and delete api/client.py once tests stop importing it.",
            impact="module",
            fix="multi_file_refactor",
        ),
        issue(
            "incomplete_migration",
            "legacy_benchmark_runner",
            "Legacy benchmark/runner.py coexists with services/benchmark.py",
            ["lm_optimizer/benchmark/runner.py", "lm_optimizer/services/benchmark.py"],
            ["runner.py defines BenchmarkRunner/BenchmarkResult and is imported by engine.py and one test.",
             "services/benchmark.py is the active benchmark implementation."],
            "Move the remaining test to the service API and delete benchmark/runner.py with the legacy engine.",
            confidence="medium",
            impact="module",
            fix="multi_file_refactor",
        ),
    ],
    "updates": {
        "add": [
            {"header": "Authoritative app is documented", "description": "web_main.py launches api.main:app and the deprecated module points to it, so the target of the migration is unambiguous.", "settled": True, "positive": True},
        ]
    },
}

# --------------------------------------------------------------------------
DATA[15] = {
    "dim": "package_organization",
    "score": 65.0,
    "evidence": [
        "Root-level hw_monitor.py and vram_matrix.py are scripts with low fan-in that duplicate hardware concerns already under lm_optimizer/hardware and services.",
        "lm_optimizer/services/ is a flat directory with 65 functions and 42 classes spanning unrelated capabilities.",
        "tools/ contains 39 scripts with mixed durability: reusable probes next to one-off speed16k_* and swift_* campaign scripts.",
        "Domain, storage, backends, benchmark and scoring are purpose-named packages, which gives the layout a usable spine.",
    ],
    "character": "The core packages are named by capability and are easy to navigate. The degradation is at the edges: a flat services grab bag, ad-hoc root scripts and a tools directory that mixes durable utilities with campaign leftovers.",
    "rationale": "Domain/backends/storage/benchmark/scoring give the repository a recognizable structure, but the services flatland and root-level script stragglers create ownership ambiguity. This is solid but uneven.",
    "issues": [
        issue(
            "package_organization",
            "root_script_stragglers",
            "Hardware scripts sit at the repository root instead of with the hardware package or tools",
            ["hw_monitor.py", "vram_matrix.py"],
            ["Both root files have low fan-in and import lm_optimizer.services/domain.",
             "The hardware package already owns detection and monitoring."],
            "Move them under tools/ (or lm_optimizer/hardware/) and update entrypoints/README references.",
            impact="local",
            fix="single_edit",
        ),
        issue(
            "package_organization",
            "services_flat_overload",
            "services/ is a flat directory mixing unrelated capabilities",
            ["lm_optimizer/services/optimizer.py", "lm_optimizer/services/reporting.py", "lm_optimizer/services/lmstudio_defaults.py"],
            ["The directory contains orchestration, benchmark execution, reporting, host defaults, sandboxing and recommendation logic.",
             "There are no subpackages to signal ownership."],
            "Split into capability subpackages and keep a small services/__init__ facade for compatibility.",
            impact="codebase",
            fix="architectural_change",
        ),
        issue(
            "package_organization",
            "tools_mixed_durability",
            "tools/ mixes durable utilities with one-off campaign scripts",
            ["tools/speed16k_part2.py", "tools/live_validation.py", "tools/webui_audit.py"],
            ["39 scripts include reusable probes (live_validation, webui_audit) and dated campaign slices (speed16k_part2, speed16k_remaining_rerun).",
             "No README or naming rule distinguishes them."],
            "Move one-off scripts to tools/archive/ with a README, and rename durable tools by action (validate_live.py, audit_webui.py).",
            confidence="medium",
            impact="module",
            fix="multi_file_refactor",
        ),
    ],
    "updates": {
        "add": [
            {"header": "Capability-named core packages", "description": "domain, storage, backends, benchmark and scoring are named by responsibility, so the main layout is self-explanatory.", "settled": True, "positive": True},
        ]
    },
}

# --------------------------------------------------------------------------
DATA[16] = {
    "dim": "initialization_coupling",
    "score": 63.0,
    "evidence": [
        "config is a module-level pydantic-settings singleton imported by 33 modules; logging_config imports it and setup_logging creates log directories at import time.",
        "api/routes.py keeps module-level mutable state (_current_optimizer, _current_run_id) mutated by handlers.",
        "api/main.py performs route re-registration and late imports at module scope to work around include_router.",
        "ui/web.py (legacy) defines a module-level app_state dict and templates at import time.",
    ],
    "character": "Boot order matters more than it should: importing a module can create directories, register routes or capture the config snapshot. Global mutable state in the API layer further couples requests to process history.",
    "rationale": "Centralized pydantic-settings and an explicit lifespan hook are good foundations, but import-time side effects and module-level mutable state make initialization fragile in tests and under reload. This is mixed quality.",
    "issues": [
        issue(
            "initialization_coupling",
            "module_level_mutable_api_state",
            "API routes keep current optimizer/run in module-level globals",
            ["lm_optimizer/api/routes.py"],
            ["_current_optimizer and _current_run_id are assigned inside request handlers and read by later requests.",
             "The scan reports 5 mutations of module-level state in this file."],
            "Move current-run state into app.state or a small RunRegistry created in the lifespan hook and injected via dependency.",
            impact="module",
            fix="multi_file_refactor",
        ),
        issue(
            "initialization_coupling",
            "import_time_logging_side_effect",
            "Logging setup performs filesystem I/O at import time",
            ["lm_optimizer/logging_config.py"],
            ["logging_config imports config and setup_logging() creates config.storage.logs_dir.mkdir(...).",
             "Any module importing logging_config can trigger directory creation before the app starts."],
            "Make logging configuration explicit in the app/CLI entrypoint (lifespan or main) and keep the module import side-effect free.",
            confidence="high",
            impact="module",
            fix="single_edit",
        ),
        issue(
            "initialization_coupling",
            "import_time_route_surgery",
            "api/main.py rewrites the route table at import time",
            ["lm_optimizer/api/main.py"],
            ["Lines 63-106 manually recreate and filter APIRoutes because include_router was reported broken.",
             "Late imports inside the module add hidden initialization order."],
            "Use a supported include_router pattern, move optional routers into a registration function called from the lifespan hook, and assert the final route table in a test.",
            confidence="medium",
            impact="module",
            fix="multi_file_refactor",
        ),
    ],
    "updates": {
        "add": [
            {"header": "Centralized settings", "description": "pydantic-settings provides one typed config object with environment support, avoiding scattered os.environ reads in most modules.", "settled": True, "positive": True},
            {"header": "Explicit lifespan hook", "description": "The FastAPI app uses a lifespan context for startup/shutdown work, giving a clear place for future initialization.", "settled": True, "positive": True},
        ]
    },
}

# --------------------------------------------------------------------------
DATA[17] = {
    "dim": "design_coherence",
    "score": 59.0,
    "evidence": [
        "cli/main.py optimize/auto are 603-line functions that perform parsing, preflight, orchestration and rendering in one body.",
        "services/optimizer.py _test_config is 244 lines and combines load, benchmark, quality, persistence and cleanup.",
        "Two optimization engines and two checkpoint/persistence paths implement overlapping responsibilities.",
        "Many functions accept wide settings dicts instead of a focused context object, so responsibilities leak across layers.",
    ],
    "character": "Design decisions are locally reasonable but globally inconsistent: the active optimizer has a clear phase pipeline, while the CLI and the legacy stack duplicate orchestration. Large functions accumulate multiple responsibilities instead of composing collaborators.",
    "rationale": "Phase enums and focused helper modules show sound design in places, but the 600-line commands, 244-line test config function and duplicate engine are structural, not cosmetic. This is significant drag on coherence.",
    "issues": [
        issue(
            "design_coherence",
            "multi_responsibility_commands",
            "Command functions own several distinct responsibilities",
            ["lm_optimizer/cli/main.py"],
            ["optimize/auto combine argument validation, preflight, host lifecycle, run execution and report rendering.",
             "The same responsibilities are also implemented in the API path."],
            "Extract a shared optimization workflow service and keep CLI commands as thin adapters that parse input and render results.",
            impact="subsystem",
            fix="architectural_change",
        ),
        issue(
            "design_coherence",
            "test_config_multi_responsibility",
            "_test_config combines load, benchmark, quality and persistence",
            ["lm_optimizer/services/optimizer.py"],
            ["The 244-line function loads a model, runs cases, evaluates quality, records results and cleans up in one body.",
             "Failure handling for each stage is interleaved."],
            "Split into load_candidate, measure_candidate, evaluate_candidate and record_candidate steps composed by _test_config.",
            impact="module",
            fix="multi_file_refactor",
        ),
        issue(
            "design_coherence",
            "duplicate_persistence_paths",
            "Two checkpoint/persistence implementations serve the same lifecycle",
            ["lm_optimizer/storage/checkpoint.py", "lm_optimizer/storage/run_checkpoint.py"],
            ["storage/checkpoint.py is the legacy CheckpointManager used by the legacy engine.",
             "storage/run_checkpoint.py is the active checkpoint store used by the adaptive optimizer."],
            "Delete the legacy CheckpointManager with the legacy engine and keep one checkpoint contract.",
            impact="subsystem",
            fix="multi_file_refactor",
        ),
    ],
    "updates": {
        "add": [
            {"header": "Phase pipeline as composition", "description": "AdaptiveOptimizer runs named phases (speed, context speed, quality, recovery, validation) with explicit skip handling, which is a coherent orchestration spine.", "settled": True, "positive": True},
        ]
    },
}

# --------------------------------------------------------------------------
DATA[18] = {
    "dim": "contract_coherence",
    "score": 66.0,
    "evidence": [
        "save_failed_report is annotated -> Path | None but returns None for both 'winner exists' and 'no configurations', so callers cannot distinguish the reasons.",
        "Several public helpers are annotated -> dict while returning different shapes by branch.",
        "Module docstrings sometimes describe only the happy path (e.g. save_failed_report says 'Returns path').",
        "Error contracts are implicit: some functions raise ValueError, others return None/False for the same kind of invalid input.",
    ],
    "character": "Contracts are mostly honest at the dataclass level, but function-level contracts drift at the edges: None signals multiple outcomes, dict returns vary, and docstrings omit failure paths. A developer often has to read the body to know what a call can produce.",
    "rationale": "Typed domain models and explicit to_dict/from_dict helpers provide a reliable core, but ambiguous Optional returns and dict-shaped outputs make boundary contracts unpredictable. Solid but uneven.",
    "issues": [
        issue(
            "contract_coherence",
            "save_failed_report_none_semantics",
            "save_failed_report uses None for two different outcomes",
            ["lm_optimizer/services/reporting.py", "lm_optimizer/cli/main.py", "lm_optimizer/cli/auto_run.py"],
            ["The function returns None when a best config exists and when there are no configurations.",
             "Callers treat None as 'nothing to save' without knowing why."],
            "Return a small result object or raise/return distinct sentinels (e.g. Skipped(reason)), or document the ambiguity and add an explicit has_winner check at call sites.",
            confidence="high",
            impact="module",
            fix="single_edit",
        ),
        issue(
            "contract_coherence",
            "dict_return_shapes",
            "Public helpers annotated -> dict return different key sets by branch",
            ["lm_optimizer/api/routes.py", "lm_optimizer/services/lmstudio_defaults.py"],
            ["Several handlers and default helpers return dict with optional keys added conditionally.",
             "Callers use .get(...) because the annotation does not promise a shape."],
            "Return Pydantic models or TypedDicts with required/optional fields, and keep raw dicts only at serialization boundaries.",
            confidence="medium",
            impact="module",
            fix="multi_file_refactor",
        ),
        issue(
            "contract_coherence",
            "docstring_error_paths",
            "Docstrings describe the happy path but omit raised errors",
            ["lm_optimizer/services/reporting.py", "lm_optimizer/services/lm_studio.py"],
            ["save_failed_report says 'Returns path' but can return None.",
             "Client methods raise on transport errors without a documented Raises section."],
            "Add Raises/Returns sections for public functions and align annotations with every return path.",
            confidence="medium",
            impact="local",
            fix="single_edit",
        ),
    ],
    "updates": {
        "add": [
            {"header": "Round-trip dataclass serialization", "description": "Core domain dataclasses expose to_dict/from_dict pairs and are exercised by round-trip tests, giving persistence a reliable contract.", "settled": True, "positive": True},
        ]
    },
}

# --------------------------------------------------------------------------
DATA[19] = {
    "dim": "logic_clarity",
    "score": 69.0,
    "evidence": [
        "Control flow is generally direct in helpers, with early returns used for invalid input.",
        "The largest bodies (603-line commands, 244-line _test_config, 531-line report builder) interleave unrelated branches and side effects.",
        "Some retry/fallback paths repeat the same operation with slightly different guards, making it hard to see the single success condition.",
        "No identical if/else branches or code-after-return were found in the sampled modules.",
    ],
    "character": "Small functions are easy to trace, but the long orchestration bodies require holding several concurrent states (loaded model, current config, retry budget, report data). The logic is not wrong, but it is not always locally obvious what the success condition is.",
    "rationale": "Direct helpers and guard clauses keep the score above mixed, but repeated retry/fallback branches inside monoliths obscure intent. This is solid but uneven.",
    "issues": [
        issue(
            "logic_clarity",
            "retry_fallback_branching",
            "Retry and fallback branches repeat load/benchmark logic with slightly different guards",
            ["lm_optimizer/services/lm_studio.py", "lm_optimizer/services/benchmark.py"],
            ["LM Studio load fallback checks response, then polls loaded instances, then re-raises with a different message.",
             "Benchmark reasoning fallback runs the same case twice with a conditional keep."],
            "Extract a single attempt function returning an outcome and drive retries from one loop with an explicit retry policy.",
            confidence="medium",
            impact="module",
            fix="multi_file_refactor",
        ),
        issue(
            "logic_clarity",
            "long_success_condition",
            "Long functions make the success condition hard to locate",
            ["lm_optimizer/cli/main.py", "lm_optimizer/services/reporting.py"],
            ["The command bodies and report builder have several early returns and nested conditionals spread over hundreds of lines.",
             "A reader must scan the whole body to know when a run is considered successful."],
            "Extract a small is_successful(run) predicate and use it at each decision point; keep rendering separate from decision logic.",
            confidence="medium",
            impact="module",
            fix="multi_file_refactor",
        ),
        issue(
            "logic_clarity",
            "async_without_await",
            "Some async functions perform no awaits",
            ["lm_optimizer/api/routes.py", "lm_optimizer/api/main.py"],
            ["Several async handlers only call synchronous repository/template helpers.",
             "They could be plain def handlers, which would let FastAPI run them in a threadpool."],
            "Convert purely synchronous handlers to def, or add a real await (e.g. asyncio.to_thread) for blocking work.",
            confidence="medium",
            impact="local",
            fix="single_edit",
        ),
    ],
    "updates": {
        "add": [
            {"header": "Guard-clause style", "description": "CLI and API helpers commonly validate inputs and return/raise early, keeping the happy path visible in short functions.", "settled": True, "positive": True},
        ]
    },
}

# --------------------------------------------------------------------------
DATA[20] = {
    "dim": "type_safety",
    "score": 59.0,
    "evidence": [
        "693 parameters and 264 returns in production code have no annotation; 109 functions are annotated -> dict and 47 -> Any.",
        "77 dict[str, Any] annotations remain, concentrated in defaults/duel/hostguard modules.",
        "20 type: ignore comments exist, 12 of them in scoring/normalization.py without explanatory codes.",
        "Enum types exist for phases/stages/status but are bypassed with raw string comparisons in several places.",
    ],
    "character": "Type annotations are trustworthy in the domain dataclasses and Pydantic schemas, but large parts of the service and CLI surface are untyped or typed as dict/Any. A developer cannot rely on annotations to describe runtime behavior across boundaries.",
    "rationale": "Typed core entities and Pydantic request models are a real foundation, but the untyped majority of parameters, dict-returning APIs and enum bypass make annotations only partially reliable. This is significant drag rather than mixed.",
    "issues": [
        issue(
            "type_safety",
            "untyped_service_surface",
            "Most service parameters and returns lack annotations",
            ["lm_optimizer/services/optimizer.py", "lm_optimizer/services/benchmark.py", "lm_optimizer/cli/auto_run.py"],
            ["The AST census finds 693 unannotated parameters and 264 unannotated returns.",
             "Public service methods accept advanced settings and config fragments as bare dicts."],
            "Annotate public entrypoints first (prepare_run, execute, run_cases, auto_run) with concrete types and enable mypy/pyright on those modules to prevent regression.",
            impact="codebase",
            fix="multi_file_refactor",
        ),
        issue(
            "type_safety",
            "dict_any_annotations",
            "dict[str, Any] is used where a concrete shape is known",
            ["lm_optimizer/services/lmstudio_defaults.py", "lm_optimizer/services/duel.py", "lm_optimizer/services/hostguard.py"],
            ["lmstudio_defaults.py has 23 dict[str, Any] annotations for a JSON document with known keys.",
             "Key strings are repeated across merge/apply/diff functions."],
            "Define TypedDicts (or dataclasses) for the LM Studio defaults document, duel payload and host guard state; keep Any only for genuinely dynamic JSON.",
            impact="module",
            fix="multi_file_refactor",
        ),
        issue(
            "type_safety",
            "type_ignore_without_codes",
            "type: ignore comments lack error codes and explanations",
            ["lm_optimizer/scoring/normalization.py", "lm_optimizer/services/metrics_providers.py"],
            ["12 of 20 ignore comments are in normalization.py.",
             "Most use bare '# type: ignore' without the suppressed error code."],
            "Use '# type: ignore[code]  # reason' and fix the underlying narrowing issue where possible.",
            confidence="high",
            impact="local",
            fix="single_edit",
        ),
        issue(
            "type_safety",
            "enum_bypass",
            "Raw string literals bypass phase/stage/status enums",
            ["lm_optimizer/services/optimizer.py", "lm_optimizer/cli/main.py"],
            ["The enum bypass census reports 30 comparisons against raw strings.",
             "Skip-phase handling compares strings such as 'quality' instead of OptimizationPhase members in places."],
            "Normalize input once into enum members (parse_phase_skips) and compare enums internally; keep strings only at CLI/JSON boundaries.",
            confidence="medium",
            impact="module",
            fix="multi_file_refactor",
        ),
    ],
    "updates": {
        "add": [
            {"header": "Typed domain core", "description": "Domain dataclasses and Pydantic schemas type the main entities (runs, configs, metrics, requests), giving the persistence and HTTP layers a reliable core.", "settled": True, "positive": True},
        ]
    },
}


for idx, entry in DATA.items():
    dim = entry["dim"]
    payload = {
        "batch": dim,
        "batch_index": idx,
        "assessments": {dim: entry["score"]},
        "dimension_notes": {
            dim: {
                "evidence": entry["evidence"],
                "impact_scope": "codebase" if entry["score"] < 62 else "subsystem",
                "fix_scope": "multi_file_refactor",
                "confidence": "high" if entry["score"] < 65 else "medium",
                "issues_preventing_higher_score": entry["rationale"],
            }
        },
        "dimension_judgment": {
            dim: {
                "dimension_character": entry["character"],
                "score_rationale": entry["rationale"],
            }
        },
        "issues": entry["issues"],
        "context_updates": {dim: entry["updates"]},
    }
    path = RUN / f"batch-{idx}.raw.txt"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    print(f"wrote {path} ({dim}, score {entry['score']})")

print("done")
