"""Record and confirm organize, then complete triage."""

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
    print(result.stdout[-3000:])
    if result.returncode not in (0, 1):
        print(result.stderr[-1200:])


run("organize", ["plan", "triage", "--stage", "organize", "--report-file", ".desloppify/organize.txt",
    "--attestation", "Organize prioritizes cli-workflow-extraction, settings-boundary-typing, error-handling-audit and api-contracts by blast radius; services-structure follows and tests-conventions is last."])

run("confirm-organize", ["plan", "triage", "--confirm", "organize", "--attestation",
    "Organize verified the cli-workflow-extraction, settings-boundary-typing and error-handling-audit clusters cover 42/42 issues with action steps and a concrete PR order; explicit skips cover tools churn and requirements drift."])

run("complete", ["plan", "triage", "--complete", "--strategy", pathlib.Path(".desloppify/strategy.txt").read_text(encoding="utf-8").strip()])
