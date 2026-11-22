"""Fill-ramp helpers for the Context Explorer (spec 8.4 / 8.5).

A single context size is not "usable" just because it allocates: the
model must also answer correctly when the window is *filled*.  The fill
ramp tests increasing fill ratios (0% -> 100%) at a fixed context size
and reports the highest ratio that still passes (speed + retrieval).

This module is pure (no I/O) so it can be unit tested offline.
"""

from __future__ import annotations

from typing import Iterable


def fill_ramp_ratios(step: float = 0.1, max_ratio: float = 1.0) -> list[float]:
    """Return the increasing fill ratios to probe for a fill ramp.

    Always starts at 0.0 (allocation-only) and ends at `max_ratio`
    (default 1.0 = 100% fill).  `step` controls the granularity; values
    are clamped to [0, 1] and de-duplicated while preserving order.
    """
    if step <= 0:
        step = 0.1
    if max_ratio <= 0:
        max_ratio = 1.0
    max_ratio = min(1.0, max_ratio)
    out: list[float] = []
    r = 0.0
    guard = 0
    while r < max_ratio - 1e-9 and guard < 1000:
        guard += 1
        out.append(round(r, 4))
        r += step
    if not out or out[-1] < max_ratio - 1e-9:
        out.append(round(max_ratio, 4))
    # de-dupe preserving order
    seen: set[float] = set()
    uniq: list[float] = []
    for v in out:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq


def max_usable_fill(results: Iterable[tuple[float, bool]]) -> float | None:
    """Given (fill_ratio, passed) pairs, return the highest passing ratio.

    Returns None when nothing passed.  Pairs need not be sorted; the
    function scans all of them.
    """
    best: float | None = None
    for ratio, passed in results:
        if passed and (best is None or ratio > best):
            best = ratio
    return best


def ramp_stopped_reason(
    last_ratio: float,
    last_passed: bool,
    error: str = "",
) -> str:
    """Classify why a fill ramp stopped.

    Returns one of: 'complete' (reached 100% and passed), 'oom', 'timeout',
    'crash', 'fail', 'garbage' (passed=false without a transport error).
    """
    if last_passed and last_ratio >= 1.0 - 1e-9:
        return "complete"
    text = (error or "").lower()
    if "oom" in text or "out of memory" in text:
        return "oom"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "crash" in text or "segfault" in text or "terminated" in text:
        return "crash"
    if "500" in text:
        return "oom"  # server OOM surfaces as 500
    if not last_passed:
        return "garbage" if not error else "fail"
    return "complete"
