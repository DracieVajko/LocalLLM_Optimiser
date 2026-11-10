"""Rich console view for an optimization run result.

Extracted from ``cli/main.py`` so the command module owns parsing/wiring and
the presentation lives in one focused module.
"""

import pathlib

main = pathlib.Path("lm_optimizer/cli/main.py")
lines = main.read_text(encoding="utf-8").splitlines(keepends=True)
start = next(i for i, line in enumerate(lines) if line.startswith("def _display_optimization_result("))
end = next(
    i for i in range(start + 1, len(lines))
    if lines[i].startswith("def ") and not lines[i].startswith("def _display_optimization_result(")
)
body = "".join(lines[start:end]).replace(
    "def _display_optimization_result(", "def display_optimization_result(", 1
)

header = '''"""Rich console view for an optimization run result."""

from __future__ import annotations

from datetime import datetime

from rich.console import Console
from rich.json import JSON
from rich.panel import Panel
from rich.table import Table

from lm_optimizer.config import config
from lm_optimizer.logging_config import get_logger

console = Console()
logger = get_logger(__name__)


'''
pathlib.Path("lm_optimizer/cli/result_view.py").write_text(header + body, encoding="utf-8")

del lines[start:end]
main.write_text("".join(lines), encoding="utf-8")
print(f"moved lines {start+1}-{end} to cli/result_view.py")
