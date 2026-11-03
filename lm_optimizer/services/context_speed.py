"""Context-speed ladder run at the end of every speed phase.

The fastest configuration found by the speed phase is re-loaded at doubling
contexts (2k, 4k, 8k, 16k, 32k, 64k, 128k, 256k, ...) and a short speed probe
records generation tok/s at each rung. The ladder stops at the first rung that
cannot load (OOM or backend refusal), so the model's practical ceiling is
measured with real loads, never estimated.

The optional maximum-context search (Phase B) is separate: it keeps escalating
until the user's minimum tok/s or an OOM boundary, then refines the boundary.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

ProbeFn = Callable[[int], Awaitable[dict[str, Any]]]
RungFn = Callable[[dict[str, Any], list[dict[str, Any]]], Awaitable[None]]

#: Standard doubling ladder requested for every optimized model.
STANDARD_CONTEXT_LADDER: tuple[int, ...] = (
    2048,
    4096,
    8192,
    16384,
    32768,
    65536,
    131072,
    262144,
)


_RETRYABLE_ERROR_PREFIXES = (
    "AttributeError:",
    "TypeError:",
    "KeyError:",
    "NameError:",
    "ImportError:",
)


def _is_retryable_failure(entry: dict[str, Any]) -> bool:
    """Internal probe errors are retried; load/OOM failures are boundaries."""
    if entry.get("retryable"):
        return True
    if entry.get("ok"):
        return False
    return str(entry.get("error") or "").startswith(_RETRYABLE_ERROR_PREFIXES)


def plan_context_speed_ladder(
    model_limit: int | None,
    contexts: tuple[int, ...] | list[int] | None = None,
) -> list[int]:
    """Rungs at or below the model's advertised context limit.

    A tiny model (limit < 2048) still gets its own limit as the only rung, so
    the phase never silently reports "no data" for a valid model.
    """
    try:
        limit = int(model_limit or 0)
    except (TypeError, ValueError):
        limit = 0
    rungs = [int(c) for c in (contexts or STANDARD_CONTEXT_LADDER) if c > 0]
    if limit > 0:
        kept = [c for c in rungs if c <= limit]
        if not kept:
            return [limit]
        return kept
    return rungs


async def measure_context_speed(
    probe: ProbeFn,
    contexts: list[int],
    *,
    completed: dict[int, dict[str, Any]] | None = None,
    on_rung: RungFn | None = None,
) -> dict[str, Any]:
    """Measure ``probe(ctx)`` across the ladder, stopping at the first failure.

    ``completed`` lets a resumed run reuse rungs already measured and continue
    from the next one. A recorded load failure terminates the ladder (larger
    contexts cannot load if a smaller one already failed); internal probe
    errors are marked retryable and re-measured on resume.
    ``on_rung`` is awaited after every new rung for incremental persistence.
    """
    done = {int(k): v for k, v in (completed or {}).items() if isinstance(v, dict)}
    results: list[dict[str, Any]] = []
    stopped = False
    for ctx in contexts:
        ctx = int(ctx)
        existing = done.get(ctx)
        if existing is not None and not _is_retryable_failure(existing):
            results.append(dict(existing))
            if not existing.get("ok"):
                stopped = True
                break
            continue
        try:
            res = await probe(ctx)
        except Exception as e:  # a probe crash must not kill the run
            res = {
                "ok": False,
                "tok_s": 0.0,
                "error": f"{type(e).__name__}: {e}"[:160],
                # Internal failures are retried on resume; OOM/load
                # refusals are real boundaries and stay terminal.
                "retryable": True,
            }
        entry = {"ctx": ctx, **res}
        results.append(entry)
        if on_rung is not None:
            await on_rung(entry, results)
        if not entry.get("ok"):
            stopped = True
            break

    passing = [r for r in results if r.get("ok") and float(r.get("tok_s") or 0) > 0]
    fastest = max(passing, key=lambda r: float(r["tok_s"])) if passing else None
    return {
        "ladder": [int(c) for c in contexts],
        "results": results,
        "last_passing_context": passing[-1]["ctx"] if passing else None,
        "failed_context": next((r["ctx"] for r in results if not r.get("ok")), None),
        "max_speed_context": fastest["ctx"] if fastest else None,
        "max_speed_tok_s": round(float(fastest["tok_s"]), 3) if fastest else None,
        # Complete only when the ladder ended by failure or reached its last
        # rung; an interrupted run leaves this False and resumes.
        "complete": bool(stopped or (contexts and results and results[-1]["ctx"] == int(contexts[-1]))),
    }


def format_context_speed(report: dict[str, Any] | None) -> list[str]:
    """One-line-per-rung summary for CLI/report output."""
    if not isinstance(report, dict) or not report.get("results"):
        return ["Context speed: no measurements"]
    lines = ["Context speed (winner config):"]
    for r in report["results"]:
        if r.get("ok"):
            lines.append(f"  {r['ctx']:>7}  {float(r.get('tok_s') or 0):7.2f} tok/s")
        else:
            err = str(r.get("error") or "load failed")[:70]
            lines.append(f"  {r['ctx']:>7}  FAIL  {err}")
    return lines
