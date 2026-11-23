"""Build a reproducible WebUI + backend test package ZIP.

The first package shipped only the UI; every pytest import failed because the
backend modules were missing. This builder includes the real package, the test
suite, the project metadata and a fresh test-results file.
"""
from __future__ import annotations

import os
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(os.path.dirname(ROOT), "LM_Studio_Optimizer_Full_TestPackage.zip")

INCLUDE_DIRS = ["lm_optimizer", "tests", "benchmarks", "docs", "tools"]
INCLUDE_FILES = [
    "README.md",
    "CHANGELOG.md",
    "pyproject.toml",
    "conftest.py",
    "pytest.ini",
    "requirements.txt",
    "start.bat",
    "setup.py",
]

SKIP_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "data", "results", "logs"}
SKIP_EXT = {".pyc", ".pyo", ".log"}


def _walk(path: str):
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if os.path.splitext(name)[1].lower() in SKIP_EXT:
                continue
            yield os.path.join(root, name)


def main() -> int:
    # 1) Fresh test results, captured as text inside the archive.
    results = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "lm_optimizer/tests", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    test_text = (results.stdout or "") + (results.stderr or "")
    print(test_text[-500:])

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in INCLUDE_FILES:
            path = os.path.join(ROOT, name)
            if os.path.exists(path):
                zf.write(path, name)
        for rel in INCLUDE_DIRS:
            base = os.path.join(ROOT, rel)
            if not os.path.isdir(base):
                continue
            for path in _walk(base):
                arc = os.path.relpath(path, ROOT).replace(os.sep, "/")
                zf.write(path, arc)
        zf.writestr("test_results/pytest.txt", test_text)
        zf.writestr(
            "README_PACKAGE.md",
            "# LM Studio Optimizer — full test package\n\n"
            "This archive ships the real backend (`lm_optimizer/`), the test suite\n"
            "(`tests/`, `lm_optimizer/tests/`), `pyproject.toml`, `conftest.py` and\n"
            "`test_results/pytest.txt` (the exact run captured when the ZIP was built).\n\n"
            "## Reproduce\n\n"
            "```bash\n"
            "python -m pip install -e .\n"
            "python -m pytest tests lm_optimizer/tests -q\n"
            "```\n\n"
            "The WebUI lives in `lm_optimizer/ui/` and is served by the FastAPI app;\n"
            "it is not a standalone `file://` page (templates use root-relative\n"
            "`/static/...` URLs and call `/api/...`).\n",
        )

    size = os.path.getsize(OUT)
    print(f"created {OUT} ({size / 1024 / 1024:.1f} MB)")
    return 0 if results.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
