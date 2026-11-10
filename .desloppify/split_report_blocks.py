"""Replace the inline tested/failed/tried report blocks with helper calls."""

import pathlib

path = pathlib.Path("lm_optimizer/services/reporting.py")
lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

start = next(
    i for i, line in enumerate(lines)
    if line.strip() == 'lines += ["## Tested configurations (passed)", ""]'
)
control = next(
    i for i, line in enumerate(lines)
    if "## Control channels (per parameter, registry-driven)" in line
)
replacement = [
    "    lines += _tested_configs_rows(configs, ordered, pareto, tested, best)\n",
    "\n",
    "    lines += _failed_configs_rows(failed)\n",
    "\n",
    "    lines += _tried_values_rows(configs, best, bc)\n",
    "\n",
]
lines[start:control] = replacement
path.write_text("".join(lines), encoding="utf-8")
print(f"replaced lines {start+1}-{control} with helper calls")
