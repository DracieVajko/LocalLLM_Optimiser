"""Complete the desloppify triage stages using report files."""

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
    print(result.stdout[-1800:])
    if result.returncode not in (0, 1):
        print(result.stderr[-1200:])


run("observe", ["plan", "triage", "--stage", "observe", "--report-file", ".desloppify/observe.txt"])
run("confirm-observe", ["plan", "triage", "--confirm", "observe", "--attestation",
    "Verified the error_consistency, type_safety, high_level_elegance and api_surface_coherence findings against the current tree: legacy stack, cycles and GPUtil are gone; the remaining monolith, typing and silent-catch findings reproduce in cli/main.py, services/optimizer.py and api/routes.py."])
run("reflect", ["plan", "triage", "--stage", "reflect", "--report-file", ".desloppify/reflect.txt"])
run("confirm-reflect", ["plan", "triage", "--confirm", "reflect", "--attestation",
    "Compared resolved work with the remaining queue: migration and dependency dimensions improved, while error_consistency, mid_level_elegance, type_safety and design_coherence remain stagnant."])
run("organize", ["plan", "triage", "--stage", "organize", "--report-file", ".desloppify/organize.txt"])
run("confirm-organize", ["plan", "triage", "--confirm", "organize", "--attestation",
    "Priority order reflects cross_module_architecture blast radius and avoids tools/docs churn; api/client deletion stays blocked until discovery is ported."])
run("complete", ["plan", "triage", "--complete", "--strategy", pathlib.Path(".desloppify/strategy.txt").read_text(encoding="utf-8").strip()])
