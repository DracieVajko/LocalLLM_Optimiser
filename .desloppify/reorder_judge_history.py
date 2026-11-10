"""Move /judge/history above /judge/{judge_id} so static path wins."""

import pathlib

path = pathlib.Path("lm_optimizer/api/routes.py")
lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

history_start = next(
    i for i, line in enumerate(lines) if line.startswith('@router.get("/judge/history"')
)
next_route = next(
    i for i in range(history_start + 1, len(lines)) if lines[i].startswith("@router.")
)
judge_param_start = next(
    i for i, line in enumerate(lines) if line.startswith('@router.get("/judge/{judge_id}"')
)

block = lines[history_start:next_route]
del lines[history_start:next_route]
# Recompute the target after deletion.
target = next(
    i for i, line in enumerate(lines) if line.startswith('@router.get("/judge/{judge_id}"')
)
lines[target:target] = block
path.write_text("".join(lines), encoding="utf-8")
print(f"moved history block {history_start}-{next_route} before {target}")
