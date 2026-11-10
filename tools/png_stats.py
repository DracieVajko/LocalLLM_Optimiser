"""Measure whether a rendered screenshot actually contains a scene.

Thin command-line wrapper around ``lm_optimizer.services.png_stats``; the
sandbox uses the same classifier for its ``renders_content`` check.

    python tools/png_stats.py results/compare/visuals/*.png
    python tools/png_stats.py shot.png --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lm_optimizer.services.png_stats import measure_png  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", help="PNG files to measure")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    for name in args.images:
        path = Path(name)
        try:
            stats = measure_png(path)
        except (OSError, ValueError) as exc:
            print(f"{path.name:<53} ERROR {exc}")
            continue
        if args.json:
            print(
                json.dumps(
                    {
                        "file": path.name,
                        "w": stats.width,
                        "h": stats.height,
                        "mean": round(stats.mean, 1),
                        "sd": round(stats.sd, 1),
                        "dark_pct": round(stats.dark_pct, 1),
                        "tones": stats.tones,
                        "verdict": stats.verdict,
                    }
                )
            )
        else:
            print(f"{path.name[:52]:<53} {stats.detail()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
