"""Invoke desloppify triage with the strategist briefing as one argument."""

import os
import pathlib
import subprocess
import sys

exe = pathlib.Path(os.environ["APPDATA"]) / "Python" / "Python314" / "Scripts" / "desloppify.exe"
report = pathlib.Path(".desloppify/strategize.json").read_text(encoding="utf-8")
result = subprocess.run(
    [str(exe), "plan", "triage", "--stage", "strategize", "--report", report],
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
)
print("returncode:", result.returncode)
print(result.stdout[-6000:])
print("--- stderr ---")
print(result.stderr[-3000:])
sys.exit(result.returncode)
