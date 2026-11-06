"""Measured capacity discovery for a (model, host) pair.

Replaces the fixed min_context/max_context grid with a cost-driven geometric
ladder that probes load, speed and recall at increasing context sizes.
Results are persisted per (model_id, size_bytes, host_fingerprint, gpu_ratio)
so a re-run starts where the previous one stopped.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CapacityProbe:
    ctx: int
    tok_s: float = 0.0
    ttft_ms: float = 0.0
    recall_ok: bool = False
    vram_gb: float = 0.0
    load_ok: bool = False
    prompt_tokens: int = 0
    oom: bool = False


@dataclass
class CapacityResult:
    model_id: str = ""
    size_bytes: int = 0
    host_fingerprint: str = ""
    gpu_ratio: float = 1.0
    curve: list[dict[str, Any]] = field(default_factory=list)
    ctx_load_max: int = 0
    ctx_usable: int = 0
    ctx_speed: int = 0
    measured_at: str = ""
    probes: int = 0


def _cache_dir() -> Path:
    return Path("data") / "capability"


def _cache_path(model_id: str, size_bytes: int, host_fp: str, gpu_ratio: float) -> Path:
    key = f"{model_id}:{size_bytes}:{host_fp}:{gpu_ratio}"
    h = hashlib.sha256(key.encode()).hexdigest()[:16]
    return _cache_dir() / f"{h}.json"


def load_cached(model_id: str, size_bytes: int, host_fp: str, gpu_ratio: float) -> CapacityResult | None:
    path = _cache_path(model_id, size_bytes, host_fp, gpu_ratio)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return CapacityResult(**data)
    except Exception:
        return None


def save_cached(result: CapacityResult) -> None:
    try:
        d = _cache_dir()
        d.mkdir(parents=True, exist_ok=True)
        path = _cache_path(result.model_id, result.size_bytes, result.host_fingerprint, result.gpu_ratio)
        path.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# Standard context ladder (geometric)
CONTEXT_LADDER = [2048, 4096, 8192, 12288, 16384, 24576, 32768, 65536, 131072, 262144]


def build_ladder(model_context_limit: int, ctx_cap: int | None = None) -> list[int]:
    """Build the context ladder bounded by model limit and optional cap."""
    cap = min(model_context_limit or 131072, ctx_cap or 131072)
    return [c for c in CONTEXT_LADDER if c <= cap]


def run_capacity_discovery(
    model_id: str,
    size_bytes: int,
    host_fp: str,
    gpu_ratio: float,
    model_context_limit: int,
    ctx_cap: int | None,
    min_tok_s: float,
    continue_ratio: float,
    probe_fn,  # callable(ctx) -> CapacityProbe
    load_fn,   # callable(ctx) -> bool (load ok)
) -> CapacityResult:
    """Run the full capacity discovery ladder.

    Returns a CapacityResult with the measured curve and derived ceilings.
    """
    result = CapacityResult(
        model_id=model_id,
        size_bytes=size_bytes,
        host_fingerprint=host_fp,
        gpu_ratio=gpu_ratio,
    )

    # Check cache first
    cached = load_cached(model_id, size_bytes, host_fp, gpu_ratio)
    if cached is not None:
        return cached

    ladder = build_ladder(model_context_limit, ctx_cap)

    # 0a. Load ceiling — try from the top down
    ctx_load_max = 0
    for ctx in reversed(ladder):
        if load_fn(ctx):
            ctx_load_max = ctx
            break
    result.ctx_load_max = ctx_load_max

    if ctx_load_max == 0:
        # Cannot load even the smallest context
        result.measured_at = __import__("datetime").datetime.now().isoformat()
        save_cached(result)
        return result

    # 0b. Usable ceiling — probe each step
    peak_tok_s = 0.0
    ctx_usable = 0
    usable_ladder = [c for c in ladder if c <= ctx_load_max]

    for ctx in usable_ladder:
        probe = probe_fn(ctx)
        result.curve.append({
            "ctx": probe.ctx,
            "tok_s": probe.tok_s,
            "ttft_ms": probe.ttft_ms,
            "recall_ok": probe.recall_ok,
            "vram_gb": probe.vram_gb,
            "prompt_tokens": probe.prompt_tokens,
            "load_ok": probe.load_ok,
        })
        result.probes += 1

        if not probe.load_ok or not probe.recall_ok:
            break
        if probe.tok_s < min_tok_s:
            break
        if peak_tok_s > 0 and probe.tok_s < continue_ratio * peak_tok_s:
            break
        ctx_usable = ctx
        peak_tok_s = max(peak_tok_s, probe.tok_s)

    result.ctx_usable = ctx_usable

    # 0c. ctx_speed = largest ctx where tok_s >= 0.8 * peak
    if peak_tok_s > 0:
        threshold = 0.8 * peak_tok_s
        for entry in reversed(result.curve):
            if entry["tok_s"] >= threshold:
                result.ctx_speed = entry["ctx"]
                break

    result.measured_at = __import__("datetime").datetime.now().isoformat()
    save_cached(result)
    return result
