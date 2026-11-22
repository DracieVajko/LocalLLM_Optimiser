"""Execute generated Python code against hidden behavioural tests.

The optimizer's coding benchmark must not reward code that merely *mentions*
the right words (a function returning ``[]`` used to pass the static checks).
This module extracts a function from the model output and runs real assertions
in an isolated subprocess with a hard timeout.

The model code is written to ``solution.py`` and loaded by a separate
``runner.py`` with ``importlib``.  That keeps ``from __future__ import
annotations``, module docstrings and real imports legal, which the old
paste-into-a-script approach turned into a SyntaxError.

This is crash/hang isolation, **not a security sandbox**: the model code runs
with the user's rights.  See ``docs/OPTIMIZATION_METHOD.md``.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

#: Behavioural cases: (input, expected output).
_HIDDEN_CASES: list[tuple[list[int], list[int]]] = [
    ([1, 2, 3, 1, 2, 4], [1, 2]),
    ([-1, 0, -1, 2, 0], [-1, 0]),
    ([], []),
    ([5, 5, 5], [5]),
    ([7], []),
    ([3, 1, 2], []),
]

#: Performance cases: 200k values.  An O(n^2) implementation cannot finish.
_PERF_N = 200_000


def _hidden_cases() -> list[tuple[list[int], list[int]]]:
    return list(_HIDDEN_CASES)


@dataclass(frozen=True)
class CodeStructure:
    """What the model's module looks like before anything is executed."""

    parses: bool
    has_function: bool
    clean_module: bool
    detail: str


def code_structure(code: str) -> CodeStructure:
    """Parse ``code`` and describe its module-level shape.

    ``clean_module`` means the module body is only imports, a docstring and
    the single ``find_duplicates`` function.  A syntax error is reported as
    ``parses=False``; it is never treated as a truncation heuristic.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return CodeStructure(
            parses=False,
            has_function=False,
            clean_module=False,
            detail=f"SyntaxError: {exc.msg} (line {exc.lineno})",
        )

    has_function = False
    extra: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            continue  # module docstring
        if isinstance(node, ast.FunctionDef) and node.name == "find_duplicates":
            has_function = True
            continue
        extra.append(type(node).__name__)

    if not has_function:
        detail = "find_duplicates is not defined at module level"
    elif extra:
        detail = "unexpected module-level statement(s): " + ", ".join(extra[:3])
    else:
        detail = "module body is imports, docstring and find_duplicates only"
    return CodeStructure(
        parses=True,
        has_function=has_function,
        clean_module=has_function and not extra,
        detail=detail,
    )


def check_code_structure(code: str) -> tuple[bool, bool, str]:
    """Return ``(parses, clean_module, detail)`` for the model's code."""
    structure = code_structure(code)
    return structure.parses, structure.clean_module, structure.detail


_RUNNER = '''\
"""Generated runner: load solution.py and exercise find_duplicates."""
import importlib.util
import json
import sys
import time

solution_path = sys.argv[1]
phase = sys.argv[2]

spec = importlib.util.spec_from_file_location("solution", solution_path)
module = importlib.util.module_from_spec(spec)
sys.modules["solution"] = module
spec.loader.exec_module(module)
func = getattr(module, "find_duplicates", None)
if not callable(func):
    print(json.dumps({"error": "find_duplicates is not defined"}))
    raise SystemExit(0)

HIDDEN = [
    ([1, 2, 3, 1, 2, 4], [1, 2]),
    ([-1, 0, -1, 2, 0], [-1, 0]),
    ([], []),
    ([5, 5, 5], [5]),
    ([7], []),
    ([3, 1, 2], []),
]

PERF = [
    ("all-distinct", list(range(PERF_N)), []),
    ("all-equal", [7] * PERF_N, [7]),
]

if phase == "correctness":
    failures = []
    for values, expected in HIDDEN:
        try:
            got = func(list(values))
        except Exception as exc:
            failures.append({"input": values, "error": repr(exc)})
            continue
        if got != expected:
            failures.append({"input": values, "expected": expected, "got": got})
    print(json.dumps({"failures": failures}))
else:
    budget = float(sys.argv[3])
    failures = []
    for name, values, expected in PERF:
        started = time.perf_counter()
        try:
            got = func(list(values))
        except Exception as exc:
            failures.append({"case": name, "error": repr(exc)})
            continue
        elapsed = time.perf_counter() - started
        if elapsed > budget:
            failures.append(
                {"case": name, "performance_s": round(elapsed, 3), "budget_s": budget}
            )
        elif got != expected:
            failures.append({"case": name, "expected": expected, "got": got})
    print(json.dumps({"failures": failures}))
'''


def _minimal_env(tmpdir: str) -> dict[str, str]:
    """A small environment: no proxies, no user profile paths."""
    env = {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "TEMP": tmpdir,
        "TMP": tmpdir,
    }
    # Windows needs SYSTEMROOT for the CRT/socket stack.
    system_root = os.environ.get("SYSTEMROOT")
    if system_root:
        env["SYSTEMROOT"] = system_root
    return env


def _cpu_limit(seconds: float):
    """POSIX CPU-time limit; Windows relies on the subprocess timeout."""
    if os.name != "posix":
        return None

    def _apply() -> None:
        try:
            import resource

            limit = max(1, int(seconds) + 1)
            resource.setrlimit(resource.RLIMIT_CPU, (limit, limit + 1))
        except Exception:  # noqa: BLE001 - best effort, never break the runner
            pass

    return _apply


def _run_phase(
    *,
    tmpdir: Path,
    phase: str,
    timeout_s: float,
    perf_budget_s: float | None = None,
) -> tuple[bool, str]:
    command = [sys.executable, "-I", str(tmpdir / "runner.py"), str(tmpdir / "solution.py"), phase]
    if perf_budget_s is not None:
        command.append(str(perf_budget_s))
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=tmpdir,
            env=_minimal_env(str(tmpdir)),
            preexec_fn=_cpu_limit(timeout_s),
        )
    except subprocess.TimeoutExpired:
        if phase == "performance":
            return False, f"performance cases exceeded {perf_budget_s:.1f}s"
        return False, f"timed out after {timeout_s:.0f}s"
    except Exception as exc:  # noqa: BLE001
        return False, f"runner error: {exc}"

    if result.returncode != 0:
        tail = (result.stderr or "").strip().splitlines()[-1:] or ["non-zero exit"]
        return False, f"execution failed: {tail[0][:160]}"
    try:
        payload = json.loads((result.stdout or "{}").strip() or "{}")
    except json.JSONDecodeError:
        return False, "runner produced no parseable result"
    if payload.get("error"):
        return False, str(payload["error"])
    failures = payload.get("failures") or []
    if failures:
        first = failures[0]
        if phase == "performance":
            return False, f"performance case failed: {first}"
        return False, f"{len(failures)} hidden case(s) failed; first={first}"
    return True, ""


def run_find_duplicates(
    code: str,
    *,
    timeout_s: float = 10.0,
    perf_timeout_s: float = 2.0,
) -> tuple[bool, str]:
    """Execute ``find_duplicates`` from ``code`` against hidden cases.

    Returns ``(passed, detail)``.  Correctness cases run first; only a correct
    function is asked to satisfy the 200k-element performance cases within
    ``perf_timeout_s``.  An O(n^2) implementation fails the performance phase.
    """
    with tempfile.TemporaryDirectory(prefix="lmopt-code-") as raw_tmp:
        tmpdir = Path(raw_tmp)
        (tmpdir / "solution.py").write_text(code, encoding="utf-8")
        (tmpdir / "runner.py").write_text(
            _RUNNER.replace("PERF_N", str(_PERF_N)), encoding="utf-8"
        )

        ok, detail = _run_phase(
            tmpdir=tmpdir, phase="correctness", timeout_s=timeout_s
        )
        if not ok:
            return False, detail

        ok, detail = _run_phase(
            tmpdir=tmpdir,
            phase="performance",
            timeout_s=perf_timeout_s + 1.0,
            perf_budget_s=perf_timeout_s,
        )
        if not ok:
            return False, detail

    return (
        True,
        f"{len(_HIDDEN_CASES)} hidden case(s) passed; "
        f"2 performance case(s) within {perf_timeout_s:.1f}s",
    )
