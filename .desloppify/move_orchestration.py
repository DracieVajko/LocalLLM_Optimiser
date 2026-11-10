"""Move the orchestration services into a capability subpackage."""

import pathlib
import subprocess

ROOT = pathlib.Path("lm_optimizer/services")
DEST = ROOT / "orchestration"
DEST.mkdir(exist_ok=True)

MODULES = ["optimizer.py", "optimization_workflow.py", "run_summary.py", "selection.py", "recovery.py"]
for name in MODULES:
    src = ROOT / name
    dst = DEST / name
    if src.exists():
        subprocess.run(["git", "mv", str(src), str(dst)], check=True)
        print(f"moved {src} -> {dst}")

(DEST / "__init__.py").write_text(
    '"""Run orchestration: optimizer, workflow, selection, recovery and summaries."""\n',
    encoding="utf-8",
)
(ROOT / "__init__.py").write_text(
    '"""Capability services for the optimizer."""\n',
    encoding="utf-8",
)

replacements = {
    "lm_optimizer.services.orchestration.optimizer": "lm_optimizer.services.orchestration.optimizer",
    "lm_optimizer.services.orchestration.optimization_workflow": "lm_optimizer.services.orchestration.optimization_workflow",
    "lm_optimizer.services.orchestration.run_summary": "lm_optimizer.services.orchestration.run_summary",
    "lm_optimizer.services.orchestration.selection": "lm_optimizer.services.orchestration.selection",
    "lm_optimizer.services.orchestration.recovery": "lm_optimizer.services.orchestration.recovery",
}

changed = 0
for path in pathlib.Path(".").rglob("*.py"):
    if ".venv" in path.parts or "node_modules" in path.parts:
        continue
    text = path.read_text(encoding="utf-8", errors="ignore")
    new = text
    for old, new_name in replacements.items():
        new = new.replace(old, new_name)
    if new != text:
        path.write_text(new, encoding="utf-8")
        changed += 1
print(f"updated {changed} files")
