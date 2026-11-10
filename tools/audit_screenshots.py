"""Audit every stored screenshot: find blank, flat and white frames."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lm_optimizer.services.png_stats import measure_png  # noqa: E402

patterns = [
    "results/compare/visuals/*.png",
    "results/bakeoff/**/preview.png",
    "results/bakeoff/**/frames/frame_0001.png",
    "results/webui_*.png",
]

files: list[Path] = []
for pattern in patterns:
    files.extend(ROOT.glob(pattern))

rows = []
for path in sorted(set(files)):
    try:
        stats = measure_png(path)
    except Exception as exc:  # noqa: BLE001
        rows.append((path, None, f"ERROR {exc}"))
        continue
    rows.append((path, stats, stats.verdict))

print(f"{len(rows)} image(s)\n")
print(f"{'verdict':8} {'mean':>7} {'sd':>7} {'dark':>6} {'tones':>6}  file")
for path, stats, verdict in rows:
    if stats is None:
        print(f"{'ERROR':8} {'':>7} {'':>7} {'':>6} {'':>6}  {path.relative_to(ROOT)}")
        continue
    flag = ""
    if stats.mean >= 250 and stats.sd < 3:
        flag = "  <-- PURE WHITE"
    elif verdict in ("blank", "flat"):
        flag = "  <-- " + verdict.upper()
    print(
        f"{verdict:8} {stats.mean:7.1f} {stats.sd:7.1f} {stats.dark_pct:5.0f}% "
        f"{stats.tones:6}  {path.relative_to(ROOT)}{flag}"
    )
