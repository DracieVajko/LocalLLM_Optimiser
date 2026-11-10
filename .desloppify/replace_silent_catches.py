"""Replace silent `except Exception: pass` blocks with log_best_effort calls."""

import ast
import pathlib
import re

ROOT = pathlib.Path("lm_optimizer")
PATTERN = re.compile(r"^(\s*)except Exception:\n(\s+)pass\s*$", re.MULTILINE)
REPLACEMENT = (
    r'\1except Exception as exc:\n'
    r'\2log_best_effort("best-effort operation failed", exc)'
)
IMPORT_LINE = "from lm_optimizer.services.best_effort import log_best_effort\n"


def import_insert_index(text: str) -> int:
    """Return the 1-based line after the module import block."""
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


def main() -> None:
    changed_files = 0
    changed_blocks = 0
    for path in sorted(ROOT.rglob("*.py")):
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        new_text, count = PATTERN.subn(REPLACEMENT, text)
        if not count:
            continue
        if "log_best_effort" not in new_text:
            lines = new_text.splitlines(keepends=True)
            index = import_insert_index(new_text)
            lines.insert(index, IMPORT_LINE)
            new_text = "".join(lines)
        path.write_text(new_text, encoding="utf-8")
        changed_files += 1
        changed_blocks += count
        print(f"{path}: {count}")
    print(f"files={changed_files} blocks={changed_blocks}")


if __name__ == "__main__":
    main()
