"""Run the remaining desloppify triage stages with concise reports."""

import os
import pathlib
import subprocess

exe = pathlib.Path(os.environ["APPDATA"]) / "Python" / "Python314" / "Scripts" / "desloppify.exe"

stages = [
    (
        "observe",
        "Root causes: (1) cli/main.py and services/optimizer.py concentrate parsing, orchestration, reporting and cleanup; "
        "(2) advanced settings cross CLI/API -> optimizer -> benchmark as an untyped dict with defaults re-applied per layer; "
        "(3) 152 broad except/pass blocks hide failures in orchestration and API paths; "
        "(4) 50 of 62 API routes return untyped dicts instead of response models. "
        "Migration and dependency findings are largely resolved (legacy stack, cycles and GPUtil removed), so do not rework those.",
    ),
    (
        "reflect",
        "Completed: legacy web/engine/checkpoint/runner removal, both import cycles, GPUtil removal, service print cleanup, "
        "requirements alignment and audit logging. Momentum: incomplete_migration, dependency_health, test_strategy, naming_quality. "
        "Stagnant: error_consistency (63), mid_level_elegance (61), type_safety (61), design_coherence (65). "
        "Prefer structural extraction over cosmetic renames; avoid tools/ and documentation churn.",
    ),
    (
        "organize",
        "Priority order: (1) extract the shared optimization workflow from cli/main.py into a service; "
        "(2) introduce a typed AdvancedSettings boundary; (3) replace copied silent catches with one logged best-effort helper; "
        "(4) add response models to the untyped API handlers; (5) split services/ by capability. "
        "Keep api/client deletion blocked until discovery/inspector.py is ported to services/lm_studio.py.",
    ),
]

for stage, report in stages:
    result = subprocess.run(
        [str(exe), "plan", "triage", "--stage", stage, "--report", report],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    print(f"=== {stage} rc={result.returncode} ===")
    print(result.stdout[-2500:])
    if result.returncode not in (0, 1):
        print(result.stderr[-1500:])
        break

strategy = (
    "Execute in blast-radius order: CLI workflow extraction, typed AdvancedSettings, silent-catch audit, "
    "API response models, then the services package split. Keep the green 1,494-test suite as the gate and "
    "avoid tools/ or docs churn that does not change the scored surface."
)
result = subprocess.run(
    [str(exe), "plan", "triage", "--complete", "--strategy", strategy],
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
)
print(f"=== complete rc={result.returncode} ===")
print(result.stdout[-3000:])
print(result.stderr[-1500:])
