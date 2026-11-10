"""Move host lifecycle services into a capability subpackage."""

import pathlib
import subprocess

ROOT = pathlib.Path("lm_optimizer/services")
DEST = ROOT / "host"
DEST.mkdir(exist_ok=True)

MODULES = [
    "lm_studio.py",
    "hostguard.py",
    "gpu_monitor.py",
    "hardware.py",
    "foreign_watchdog.py",
    "lms_cli.py",
    "metrics_providers.py",
]
for name in MODULES:
    src = ROOT / name
    dst = DEST / name
    if src.exists():
        subprocess.run(["git", "mv", str(src), str(dst)], check=True)
        print(f"moved {src} -> {dst}")

(DEST / "__init__.py").write_text(
    '"""Host lifecycle: LM Studio/Ollama clients, guards, hardware and metrics."""\n',
    encoding="utf-8",
)

replacements = {
    f"lm_optimizer.services.{name.removesuffix('.py')}": (
        f"lm_optimizer.services.host.{name.removesuffix('.py')}"
    )
    for name in MODULES
}

changed = 0
for path in pathlib.Path(".").rglob("*.py"):
    if ".venv" in path.parts:
        continue
    text = path.read_text(encoding="utf-8", errors="ignore")
    new = text
    for old, new_name in replacements.items():
        new = new.replace(old, new_name)
    # Package-style imports: from lm_optimizer.services.host import lm_studio as ...
    for name in MODULES:
        module = name.removesuffix(".py")
        new = new.replace(
            f"from lm_optimizer.services import {module}",
            f"from lm_optimizer.services.host import {module}",
        )
    if new != text:
        path.write_text(new, encoding="utf-8")
        changed += 1
print(f"updated {changed} files")
