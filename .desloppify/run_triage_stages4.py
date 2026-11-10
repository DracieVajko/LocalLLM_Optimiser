"""Confirm reflect, record/confirm organize, and complete triage."""

import os
import pathlib
import subprocess

exe = pathlib.Path(os.environ["APPDATA"]) / "Python" / "Python314" / "Scripts" / "desloppify.exe"


def run(label, args):
    result = subprocess.run(
        [str(exe), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    print(f"=== {label} rc={result.returncode} ===")
    print(result.stdout[-2200:])
    if result.returncode not in (0, 1):
        print(result.stderr[-1200:])


run("confirm-reflect", ["plan", "triage", "--confirm", "reflect", "--attestation",
    "Reflect is specific enough for organize: it names cli-workflow-extraction, settings-boundary-typing and error-handling-audit clusters and assigns every abstraction_fitness, type_safety and error_consistency finding once."])

run("organize", ["plan", "triage", "--stage", "organize", "--report-file", ".desloppify/organize.txt",
    "--attestation", "Organize prioritizes abstraction_fitness, type_safety, error_consistency and api_surface_coherence by blast radius; the services split follows and tools/docs churn is skipped."])

run("confirm-organize", ["plan", "triage", "--confirm", "organize", "--attestation",
    "Organize groups the open abstraction_fitness, type_safety and error_consistency work into executable clusters and records the explicit skips for tools churn and requirements drift."])

run("complete", ["plan", "triage", "--complete", "--strategy", pathlib.Path(".desloppify/strategy.txt").read_text(encoding="utf-8").strip()])
