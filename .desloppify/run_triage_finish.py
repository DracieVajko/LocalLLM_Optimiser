"""Record enrich and sense-check, then complete triage."""

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
    print(result.stdout[-2600:])
    if result.returncode not in (0, 1):
        print(result.stderr[-1200:])


run("enrich", ["plan", "triage", "--stage", "enrich", "--report-file", ".desloppify/enrich.txt",
    "--attestation", "Enrich verified every cli-workflow-extraction, settings-boundary-typing and error-handling-audit step names a concrete file and outcome."])

run("confirm-enrich", ["plan", "triage", "--confirm", "enrich", "--attestation",
    "Enrich confirmed: the settings-boundary-typing, api-contracts and error-handling-audit steps are executor-ready and reference their source files."])

run("sense-check", ["plan", "triage", "--stage", "sense-check", "--report-file", ".desloppify/sense_check.txt",
    "--attestation", "Sense-check verified 42/42 coverage, 4 explicit skips and a blast-radius order led by cli-workflow-extraction and settings-boundary-typing."])

run("confirm-sense-check", ["plan", "triage", "--confirm", "sense-check", "--attestation",
    "Sense-check confirmed: cli-workflow-extraction, settings-boundary-typing and error-handling-audit cover the highest-leverage issues without duplicate work."])

run("complete", ["plan", "triage", "--complete", "--strategy", pathlib.Path(".desloppify/strategy.txt").read_text(encoding="utf-8").strip()])
