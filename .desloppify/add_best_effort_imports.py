"""Add the log_best_effort import where the rewrite introduced calls."""

import ast
import pathlib

IMPORT_LINE = "from lm_optimizer.services.best_effort import log_best_effort\n"
IMPORT_MARKER = "from lm_optimizer.services.best_effort import log_best_effort"


def import_insert_index(text: str) -> int:
    tree = ast.parse(text)
    last = 0
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            last = node.end_lineno or last
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        else:
            break
    return last


count = 0
for path in sorted(pathlib.Path("lm_optimizer").rglob("*.py")):
    if "tests" in path.parts:
        continue
    text = path.read_text(encoding="utf-8")
    if "log_best_effort(" not in text or IMPORT_MARKER in text:
        continue
    lines = text.splitlines(keepends=True)
    lines.insert(import_insert_index(text), IMPORT_LINE)
    path.write_text("".join(lines), encoding="utf-8")
    count += 1
    print(path)
print(f"files={count}")
