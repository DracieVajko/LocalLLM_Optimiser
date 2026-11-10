"""Record reflect/organize and complete triage using report files."""

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
    print(result.stdout[-2500:])
    if result.returncode not in (0, 1):
        print(result.stderr[-1500:])


run("reflect", ["plan", "triage", "--stage", "reflect", "--report-file", ".desloppify/reflect.txt",
    "--attestation", "Reflect confirms the recurring patterns: monolith orchestration in high_level_elegance, untyped settings in mid_level_elegance and type_safety, and silent catches in error_consistency; the ledger assigns every open review issue to one cluster or an explicit skip."])

run("organize", ["plan", "triage", "--stage", "organize", "--report-file", ".desloppify/organize.txt",
    "--attestation", "Organize prioritizes cli-workflow-extraction, settings-boundary-typing, error-handling-audit and api-contracts by blast radius; the services split follows and tools/docs churn is skipped."])

run("complete", ["plan", "triage", "--complete", "--strategy", pathlib.Path(".desloppify/strategy.txt").read_text(encoding="utf-8").strip()])
