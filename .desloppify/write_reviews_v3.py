"""Write the post-workflow review scores (run 20261103_151531)."""

import json
from pathlib import Path

SRC = Path(".desloppify/subagents/runs/20261103_135748/results")
DST = Path(".desloppify/subagents/runs/20261103_151531/results")
DST.mkdir(parents=True, exist_ok=True)

UPDATES = {
    1: {
        "score": 69.0,
        "dim": "cross_module_architecture",
        "append": [
            "The CLI, API and auto-run now compose through services/optimization_workflow.py, reducing boundary duplication.",
        ],
        "character": "Dependency direction is materially cleaner after removing the legacy stack and both cycles, and the shared workflow service removes one more cross-module duplication. The remaining drag is hub/package scale, not direction.",
        "rationale": "Removing the legacy stack, cycles and duplicated service wiring improves boundary integrity. The 112-importer domain hub, flat services package and legacy discovery client keep it from strong.",
        "drop": set(),
    },
    2: {
        "score": 69.0,
        "dim": "high_level_elegance",
        "append": [
            "One optimization workflow service now owns service composition for CLI, API and auto-run; the Typer bodies are thinner but still large.",
        ],
        "character": "Ownership is clearer: one engine, one web app and one workflow composition point. The remaining concentration is the 5.7k-LOC CLI module and the flat services package.",
        "rationale": "The shared workflow service and legacy removal fix the biggest ownership ambiguity. The CLI monolith and flat services ownership still prevent a strong score.",
        "drop": set(),
    },
    6: {
        "score": 68.0,
        "dim": "abstraction_fitness",
        "append": [
            "AdvancedSettings and build_optimizer/build_benchmark_service now provide one earned boundary instead of per-layer dict defaults.",
        ],
        "character": "Most abstractions are direct helpers, and the new settings/workflow boundaries are earned. API conversion wrappers and a few dict-shaped payloads still add navigation without policy.",
        "rationale": "The typed settings and shared optimizer composition remove the worst implicit parameter bag. Remaining conversion wrappers and dynamic payload dicts keep it solid but uneven.",
        "drop": {"advanced_settings_bag"},
    },
    8: {
        "score": 70.0,
        "dim": "low_level_elegance",
        "append": [
            "The shared workflow extraction removed ~30 lines of duplicated wiring; the 531-line report builder and 244-line _test_config remain.",
        ],
        "character": "Helpers are direct and the orchestration wiring is now shared. The report builder and _test_config still interleave several side effects in one body.",
        "rationale": "Extracting the workflow service and logging tolerated failures improves local reasoning. The report monolith and long command bodies remain the main drag.",
        "drop": set(),
    },
    9: {
        "score": 67.0,
        "dim": "mid_level_elegance",
        "append": [
            "CLI/API/auto-run now pass AdvancedSettings through one factory instead of rebuilding BenchmarkService with drifting argument lists.",
        ],
        "character": "Integration seams are more explicit: one typed settings object and one optimizer factory cross the CLI/API boundary. API response enrichment still happens in more than one place.",
        "rationale": "The typed handoff and factory remove the duplicated service wiring that previously drifted. Ad-hoc API response mapping keeps it solid but uneven.",
        "drop": {"advanced_settings_bag", "implicit_settings_handoff", "duplicated_service_wiring"},
    },
    13: {
        "score": 73.0,
        "dim": "ai_generated_debt",
        "append": [
            "128 silent except/pass blocks now log through best_effort.log_best_effort with exc_info.",
        ],
        "character": "The code reads as purposeful rather than generated: comments are sparse, service print output is gone and tolerated failures are now visible at debug level.",
        "rationale": "Removing the 128 silent catches and keeping comments why-focused addresses the main LLM-ish residue. Remaining docstring scope drift keeps it from strong.",
        "drop": {"defensive_silent_catches"},
    },
    17: {
        "score": 68.0,
        "dim": "design_coherence",
        "append": [
            "One workflow service now owns optimizer composition; the duplicate legacy engine/checkpoint paths are gone.",
        ],
        "character": "Design is more coherent at the architecture level: one engine, one checkpoint store and one composition point. The 603-line commands and 244-line _test_config still mix responsibilities.",
        "rationale": "Removing duplicate persistence and sharing the workflow composition resolves the biggest incoherence. The monolith command bodies and _test_config remain structural drags.",
        "drop": set(),
    },
    18: {
        "score": 70.0,
        "dim": "contract_coherence",
        "append": [
            "The failed-report None semantics and the client/benchmark/repository error contracts are now documented.",
        ],
        "character": "Contracts are honest in the typed domain core and the main None/error ambiguities are documented. Dict-shaped API returns still make some callers use .get().",
        "rationale": "Documenting the failed-report outcomes and layer error contracts resolves the clearest contract lies. Remaining dict return shapes keep it solid but uneven.",
        "drop": {"save_failed_report_none_semantics"},
    },
    4: {
        "score": 72.0,
        "dim": "error_consistency",
        "append": [
            "128 silent broad catches now log operation, error and traceback at debug level; the layer error contracts are documented.",
        ],
        "character": "Tolerated failures are still contained, but they are no longer invisible. The layer contract is documented, so a developer can predict which calls raise and which return outcomes.",
        "rationale": "Replacing 128 silent catches with logged best-effort calls and documenting the layer contract is a substantial improvement. Ad-hoc API error translation remains the main inconsistency.",
        "drop": {"silent_pass_concentration", "defensive_silent_catches", "mixed_failure_contracts"},
    },
    20: {
        "score": 64.0,
        "dim": "type_safety",
        "append": [
            "AdvancedSettings, DefaultsDocument TypedDicts and annotated optimizer/benchmark entrypoints replace several dict/Any interfaces.",
        ],
        "character": "The typed domain core now extends to the advanced-settings boundary and the LM Studio defaults document. Much of the service surface is still untyped, so annotations are not yet universally trustworthy.",
        "rationale": "The typed settings boundary, defaults TypedDicts and annotated entrypoints are real gains. The remaining untyped service surface keeps this as significant drag.",
        "drop": {"dict_any_annotations", "dict_any_defaults", "enum_bypass", "type_ignore_without_codes"},
    },
}

for idx, update in UPDATES.items():
    source = SRC / f"batch-{idx}.raw.txt"
    payload = json.loads(source.read_text(encoding="utf-8"))
    dim = update["dim"]
    payload["assessments"][dim] = update["score"]
    notes = payload["dimension_notes"][dim]
    notes["evidence"] = list(notes.get("evidence", [])) + update["append"]
    notes["issues_preventing_higher_score"] = update["rationale"]
    judgment = payload["dimension_judgment"][dim]
    judgment["dimension_character"] = update["character"]
    judgment["score_rationale"] = update["rationale"]
    payload["issues"] = [
        issue for issue in payload.get("issues", [])
        if issue.get("identifier") not in update["drop"]
    ]
    (DST / f"batch-{idx}.raw.txt").write_text(
        json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    print(f"wrote batch-{idx} {dim} {update['score']} issues={len(payload['issues'])}")
