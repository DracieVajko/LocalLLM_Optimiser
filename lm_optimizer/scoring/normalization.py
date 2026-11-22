"""Hardware-agnostic metric normalization for optimization scoring.

This module implements run-relative and hardware/model-relative normalization
to avoid hardcoded assumptions such as 50 tok/s, 1000 prompt tok/s, 2000ms TTFT,
32768 context, or 6GB VRAM.

Design principles:
- Speeds (generation, prompt) are normalized against observed feasible
  configurations in the current run, not against fixed global maxima.
- Context is workload-relative: ``min(1.0, ctx / workload_target_ctx)``.
  Exceeding the target is never rewarded; it costs speed and memory.
- Memory is hardware-relative: a configuration that fits with headroom
  scores 1.0.  A missing measurement is ``None`` (excluded), never a
  neutral 0.5.
- TTFT is estimated (not directly measured); normalization is inverted
  (lower estimated TTFT is better) and handled run-relative.
- Zero-range handling: if max==min, return 1.0 (no differentiation).
- All normalized scores are clamped to [0, 1].
- A composite score exists only when quality was measured.  Missing
  components are excluded and their weight is redistributed over the
  measured ones; the exclusion is stated in :func:`composite_report`.
"""

from __future__ import annotations

from dataclasses import dataclass

EPSILON = 1e-9
# Headroom threshold: configurations leaving >=15% of total VRAM/RAM free
# are considered to have comfortable headroom and score 1.0 for memory.
# Below this, score degrades linearly to 0 at 0% headroom.
MEMORY_HEADROOM_THRESHOLD = 0.15

#: Workload-relative context targets.  Interactive chat does not need a
#: 32k window; long-document work does.  Exceeding the target is capped.
WORKLOAD_CONTEXT_TARGETS: dict[str, int] = {
    "interactive": 8192,
    "throughput": 8192,
    "long_doc": 32768,
    "long-document": 32768,
    "long_context": 32768,
    "research": 32768,
}
DEFAULT_CONTEXT_TARGET = 8192


def _clamp01(v: float) -> float:
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def workload_target_context(workload_type: str | None) -> int:
    """Context length the workload actually needs, in tokens."""
    key = str(workload_type or "interactive").strip().lower().replace(" ", "_")
    return WORKLOAD_CONTEXT_TARGETS.get(key, DEFAULT_CONTEXT_TARGET)


def normalize_higher_better(value: float, min_val: float, max_val: float) -> float:
    """Normalize where higher value is better, run-relative.

    Returns 0 for min_val, 1 for max_val. If range is zero, returns 1.0
    (no differentiation - all candidates equal on this metric).
    Clamped to [0, 1].
    """
    rng = max_val - min_val
    if abs(rng) < EPSILON:
        return 1.0
    return _clamp01((value - min_val) / rng)


def normalize_lower_better(value: float, min_val: float, max_val: float) -> float:
    """Normalize where lower value is better (e.g. TTFT).

    Returns 1 for min_val (best), 0 for max_val (worst). Zero-range -> 1.0.
    Clamped to [0, 1].
    """
    rng = max_val - min_val
    if abs(rng) < EPSILON:
        return 1.0
    return _clamp01((max_val - value) / rng)


def normalize_context(
    context_length: int, workload_target_ctx: int | None = None
) -> float:
    """Normalize context against what the workload needs.

    ``min(1.0, ctx / target)``: a 32k window on an 8k interactive workload
    scores 1.0, not 4.0.  Never rewards exceeding the target.
    """
    target = int(workload_target_ctx or DEFAULT_CONTEXT_TARGET)
    if target <= 0:
        target = DEFAULT_CONTEXT_TARGET
    if context_length <= 0:
        return 0.0
    return _clamp01(context_length / target)


def compute_memory_score(
    peak_vram_gb: float | None,
    peak_ram_gb: float | None,
    hardware_total_vram_gb: float | None,
    hardware_total_ram_gb: float | None,
    observed_vrams: list[float] | None = None,
    observed_rams: list[float] | None = None,
) -> float | None:
    """Hardware-relative memory scoring.

    Returns ``None`` when the used memory cannot be measured: a missing
    measurement is excluded from the composite, never scored as neutral 0.5.

    - If total memory is known, score by headroom:
        headroom_ratio = (total - used) / total
        headroom >= MEMORY_HEADROOM_THRESHOLD -> 1.0
        0 <= headroom < threshold -> headroom / threshold
        used > total -> 0.0 (OOM)
    - GPU VRAM takes precedence if the hardware has a GPU; otherwise RAM.
    - Without hardware totals, fall back to run-relative (less is better)
      only when there is an observed range.
    """
    has_gpu = hardware_total_vram_gb is not None and hardware_total_vram_gb > 0
    if has_gpu:
        if peak_vram_gb is None:
            return None
        total = hardware_total_vram_gb
        used = peak_vram_gb
        if used > total:
            return 0.0
        ratio = (total - used) / total
        if ratio >= MEMORY_HEADROOM_THRESHOLD:
            return 1.0
        return _clamp01(ratio / MEMORY_HEADROOM_THRESHOLD)

    if hardware_total_ram_gb and hardware_total_ram_gb > 0:
        if peak_ram_gb is None:
            return None
        total = hardware_total_ram_gb
        used = peak_ram_gb
        if used > total:
            return 0.0
        ratio = (total - used) / total
        if ratio >= MEMORY_HEADROOM_THRESHOLD:
            return 1.0
        return _clamp01(ratio / MEMORY_HEADROOM_THRESHOLD)

    # Fallback: run-relative (no hardware info).
    if observed_vrams and len(observed_vrams) > 1 and peak_vram_gb is not None:
        return normalize_lower_better(peak_vram_gb, min(observed_vrams), max(observed_vrams))
    if observed_rams and len(observed_rams) > 1 and peak_ram_gb is not None:
        return normalize_lower_better(peak_ram_gb, min(observed_rams), max(observed_rams))
    return None


@dataclass
class NormalizationBounds:
    """Observed min/max bounds for run-relative metrics within a run."""

    min_gen: float = 0.0
    max_gen: float = 0.0
    min_prompt: float = 0.0
    max_prompt: float = 0.0
    min_estimated_ttft: float = 0.0
    max_estimated_ttft: float = 0.0
    max_observed_context: int = 0
    observed_vrams: list[float] | None = None
    observed_rams: list[float] | None = None

    def __post_init__(self):
        if self.observed_vrams is None:
            self.observed_vrams = []
        if self.observed_rams is None:
            self.observed_rams = []


def _metric(result, *names: str) -> float:
    """Read the first available numeric metric (method or attribute)."""
    for name in names:
        if not hasattr(result, name):
            continue
        try:
            value = getattr(result, name)
            value = value() if callable(value) else value
            return float(value)
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def compute_bounds(
    results: list, hardware=None, model_max_context: int | None = None
) -> NormalizationBounds:
    """Compute run-relative bounds from a list of ConfigurationResult objects.

    Only passed/feasible configurations are considered.  ``hardware`` and
    ``model_max_context`` are accepted for call-site compatibility; memory is
    scored hardware-relative in :func:`score_result_breakdown`.
    """
    feasible = [
        r
        for r in results
        if getattr(r, "status", None) in ("passed", "PASSED")
        or getattr(r, "passed", False) is True
    ]
    if not feasible:
        feasible = [r for r in results if getattr(r, "metrics", None)]

    gen_vals: list[float] = []
    prompt_vals: list[float] = []
    ttft_vals: list[float] = []
    vram_vals: list[float] = []
    ram_vals: list[float] = []
    max_ctx = 0

    for r in feasible:
        g = _metric(r, "get_avg_generation_tok_s")
        p = _metric(r, "get_avg_prompt_tok_s")
        t = _metric(r, "get_avg_estimated_ttft_ms", "get_avg_ttft_ms")
        if g > 0:
            gen_vals.append(g)
        if p > 0:
            prompt_vals.append(p)
        if t > 0:
            ttft_vals.append(t)

        vram = getattr(r, "peak_vram_gb", None)
        if vram is not None and vram > 0:
            vram_vals.append(float(vram))
        ram = getattr(r, "peak_ram_gb", None)
        if ram is not None and ram > 0:
            ram_vals.append(float(ram))

        try:
            ctx = int(getattr(r, "context_length", 0) or 0)
        except (TypeError, ValueError):
            ctx = 0
        max_ctx = max(max_ctx, ctx)

    return NormalizationBounds(
        min_gen=min(gen_vals) if gen_vals else 0.0,
        max_gen=max(gen_vals) if gen_vals else 0.0,
        min_prompt=min(prompt_vals) if prompt_vals else 0.0,
        max_prompt=max(prompt_vals) if prompt_vals else 0.0,
        min_estimated_ttft=min(ttft_vals) if ttft_vals else 0.0,
        max_estimated_ttft=max(ttft_vals) if ttft_vals else 0.0,
        max_observed_context=max_ctx,
        observed_vrams=vram_vals,
        observed_rams=ram_vals,
    )


def _quality_value(result) -> float | None:
    qs = getattr(result, "quality_score", None)
    if qs is None:
        return None
    if hasattr(qs, "overall"):
        try:
            value = qs.overall
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None
    if isinstance(qs, (int, float)):
        return float(qs)
    return None


def score_result_breakdown(
    result,
    bounds: NormalizationBounds,
    hardware,
    model_max_context: int | None = None,
    weights: dict[str, float] | None = None,
    *,
    workload_type: str = "interactive",
) -> dict[str, float | None]:
    """Compute normalized breakdown for a single result.

    Returns keys matching profile weights: generation_speed, prompt_speed,
    ttft, quality, stability, context, memory_efficiency.  A value is ``None``
    when the underlying measurement is missing (never a neutral default).
    """
    gen = _metric(result, "get_avg_generation_tok_s")
    norm_gen = normalize_higher_better(gen, bounds.min_gen, bounds.max_gen)

    prompt = _metric(result, "get_avg_prompt_tok_s")
    norm_prompt = normalize_higher_better(prompt, bounds.min_prompt, bounds.max_prompt)

    ttft = _metric(result, "get_avg_estimated_ttft_ms", "get_avg_ttft_ms")
    norm_ttft = normalize_lower_better(
        ttft, bounds.min_estimated_ttft, bounds.max_estimated_ttft
    )

    quality = _quality_value(result)
    norm_quality = None if quality is None else _clamp01(quality)

    stability_raw = getattr(result, "stability_score", None)
    if stability_raw is None:
        norm_stability = None
    else:
        try:
            norm_stability = _clamp01(float(stability_raw))
        except (TypeError, ValueError):
            norm_stability = None

    ctx_len = int(getattr(result, "context_length", 0) or 0)
    norm_ctx = normalize_context(ctx_len, workload_target_context(workload_type))

    hw_vram = None
    hw_ram = None
    if hardware is not None:
        if hasattr(hardware, "gpus") and hardware.gpus:
            try:
                hw_vram = (
                    sum(g.vram_gb for g in hardware.gpus)
                    if len(hardware.gpus) > 1
                    else hardware.gpus[0].vram_gb
                )
            except (TypeError, ValueError):
                hw_vram = None
        elif hasattr(hardware, "gpu") and hardware.gpu:
            hw_vram = getattr(hardware.gpu, "vram_gb", None)
        if hasattr(hardware, "total_ram_gb"):
            hw_ram = hardware.total_ram_gb
        elif hasattr(hardware, "memory") and hasattr(hardware.memory, "total_gb"):
            hw_ram = hardware.memory.total_gb

    norm_mem = compute_memory_score(
        getattr(result, "peak_vram_gb", None),
        getattr(result, "peak_ram_gb", None),
        hw_vram,
        hw_ram,
        bounds.observed_vrams,
        bounds.observed_rams,
    )

    return {
        "generation_speed": norm_gen,
        "prompt_speed": norm_prompt,
        "ttft": norm_ttft,
        "quality": norm_quality,
        "stability": norm_stability,
        "context": norm_ctx,
        "memory_efficiency": norm_mem,
    }


_WEIGHT_ALIASES = {
    "generation_speed": ["generation_speed"],
    "prompt_speed": ["prompt_speed", "prompt_processing"],
    "ttft": ["ttft"],
    "quality": ["quality"],
    "stability": ["stability"],
    "context": ["context", "context_capacity"],
    "memory_efficiency": ["memory_efficiency"],
}


def weighted_score(
    breakdown: dict[str, float | None], weights: dict[str, float]
) -> float | None:
    """Weighted composite; ``None`` when quality was not measured.

    Missing components (``None``) are excluded and their weight is
    redistributed proportionally over the measured components.  Normalised
    scores are only comparable within one run; see :func:`composite_report`.
    """
    if breakdown.get("quality") is None:
        return None

    total = 0.0
    total_weight = 0.0
    for target_key, aliases in _WEIGHT_ALIASES.items():
        w = 0.0
        for alias in aliases:
            if alias in weights:
                w = weights[alias]
                break
        if w <= 0:
            continue
        value = breakdown.get(target_key)
        if value is None:
            continue
        total += w * float(value)
        total_weight += w

    if total_weight <= 0:
        return None
    return _clamp01(total / total_weight)


def composite_report(
    result,
    breakdown: dict[str, float | None],
    weights: dict[str, float],
    *,
    n_configs: int = 0,
) -> dict:
    """Explain a composite: score, comparability, exclusions and absolutes.

    ``comparable`` is false for a single-config or <3-config run: min-max
    normalisation inside one run cannot rank across models.  ``absolute``
    carries the measured values behind every normalised number.
    """
    excluded = sorted(key for key, value in breakdown.items() if value is None)
    quality = _quality_value(result)
    stability_raw = getattr(result, "stability_score", None)
    return {
        "score": weighted_score(breakdown, weights),
        "comparable": n_configs >= 3,
        "n_configs": n_configs,
        "quality_not_measured": quality is None,
        "excluded": excluded,
        "normalized": dict(breakdown),
        "absolute": {
            "generation_tok_s": round(_metric(result, "get_avg_generation_tok_s"), 2),
            "prompt_tok_s": round(_metric(result, "get_avg_prompt_tok_s"), 2),
            "ttft_ms": round(
                _metric(result, "get_avg_estimated_ttft_ms", "get_avg_ttft_ms"), 1
            ),
            "quality": quality,
            "stability": stability_raw,
            "context_length": int(getattr(result, "context_length", 0) or 0),
            "peak_vram_gb": getattr(result, "peak_vram_gb", None),
            "peak_ram_gb": getattr(result, "peak_ram_gb", None),
        },
    }
