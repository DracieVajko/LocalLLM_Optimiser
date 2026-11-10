"""Screenshot an HTML file through Chrome CDP.

The implementation lives in ``lm_optimizer.services.html_shot`` so the sandbox
and the comparison tool share it; this module is the command-line entry point.

    python tools/html_shot.py page.html --out page.png --wait 5
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lm_optimizer.services.html_shot import (  # noqa: E402
    ScreenshotError,
    capture,
    find_browser,
    main,
)

__all__ = ["ScreenshotError", "capture", "find_browser", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
