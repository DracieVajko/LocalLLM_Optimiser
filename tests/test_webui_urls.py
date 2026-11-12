"""Preview URLs must target the /api file-serving endpoint.

The page routes live at ``/sandbox`` and ``/history``; the API that serves the
artifacts lives at ``/api/sandbox/files``. A frontend URL missing the ``/api``
prefix gets a 404/400 and the preview iframe stays empty (the "click and
nothing happens" regression).
"""

from __future__ import annotations

from pathlib import Path

JS_DIR = Path(__file__).resolve().parents[1] / "lm_optimizer" / "ui" / "static" / "js"


def test_every_sandbox_files_url_uses_the_api_prefix():
    offenders = []
    for path in sorted(JS_DIR.glob("*.js")):
        text = path.read_text(encoding="utf-8")
        start = 0
        while True:
            index = text.find("sandbox/files", start)
            if index == -1:
                break
            if text[max(0, index - 4) : index] != "api/":
                line = text[:index].count("\n") + 1
                offenders.append(f"{path.name}:{line}")
            start = index + 1
    assert offenders == []
