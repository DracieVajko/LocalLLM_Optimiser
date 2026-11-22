"""WP-4: normalisation and the composite score.

Edge cases that used to fail open: ``stability_score = 0.0`` became ``1.0``
through ``or 1.0``; missing quality became ``1.0``; missing memory became a
neutral ``0.5``.  A missing measurement must be excluded, not rewarded.
"""

from __future__ import annotations

import pytest

from lm_optimizer.domain.models import (
    BenchmarkMetrics,
    ConfigurationResult,
    ConfigurationStatus,
    GPUInfo,
    HardwareInfo,
    LoadConfiguration,
    QualityScore,
)
from lm_optimizer.scoring.normalization import (
    NormalizationBounds,
    composite_report,
    compute_memory_score,
    normalize_context,
    score_result_breakdown,
    weighted_score,
    workload_target_context,
)


def _metrics(gen=30.0, prompt=500.0, ttft=100.0):
    return [
        BenchmarkMetrics(
            test_name="short_instruction",
            category="instruction",
            success=True,
            estimated_ttft_ms=ttft,
            prompt_tok_s=prompt,
            generation_tok_s=gen,
            output_text="ok",
        )
    ]


def _quality(overall=0.98):
    return QualityScore(
        overall=overall,
        task_completion=1.0,
        factual_consistency=1.0,
        format_compliance=1.0,
        coding_correctness=1.0,
        no_truncation=1.0,
        no_malformed=1.0,
        confident=True,
        checks_passed=6,
        checks_total=6,
    )


def make_result(
    *,
    gen=30.0,
    prompt=500.0,
    ttft=100.0,
    ctx=8192,
    vram=4.0,
    ram=None,
    quality=0.98,
    stability=0.9,
):
    return ConfigurationResult(
        config=LoadConfiguration(context_length=ctx),
        context_length=ctx,
        status=ConfigurationStatus.PASSED,
        metrics=_metrics(gen, prompt, ttft),
        quality_score=None if quality is None else _quality(quality),
        stability_score=stability,
        peak_vram_gb=vram,
        peak_ram_gb=ram,
    )


def _hardware(vram=6.0, ram=32.0):
    return HardwareInfo(
        os="Windows",
        cpu_name="TestCPU",
        cpu_cores_physical=8,
        cpu_cores_logical=16,
        total_ram_gb=ram,
        gpu_count=1 if vram is not None else 0,
        gpus=(
            [GPUInfo(index=0, name="GPU", vram_gb=vram, vendor="NVIDIA")]
            if vram is not None
            else []
        ),
    )


def _bounds(results):
    gens = [r.get_avg_generation_tok_s() for r in results]
    prompts = [r.get_avg_prompt_tok_s() for r in results]
    ttfts = [r.get_avg_estimated_ttft_ms() for r in results]
    return NormalizationBounds(
        min_gen=min(gens),
        max_gen=max(gens),
        min_prompt=min(prompts),
        max_prompt=max(prompts),
        min_estimated_ttft=min(ttfts),
        max_estimated_ttft=max(ttfts),
    )


WEIGHTS = {
    "generation_speed": 0.35,
    "prompt_speed": 0.10,
    "ttft": 0.10,
    "quality": 0.30,
    "stability": 0.10,
    "context": 0.05,
    "memory_efficiency": 0.00,
}


def test_stability_zero_is_not_rewritten_to_one():
    r = make_result(stability=0.0)
    breakdown = score_result_breakdown(r, _bounds([r]), _hardware(), 8192, WEIGHTS)
    assert breakdown["stability"] == 0.0


def test_missing_quality_makes_the_composite_none():
    r = make_result(quality=None)
    breakdown = score_result_breakdown(r, _bounds([r]), _hardware(), 8192, WEIGHTS)
    assert breakdown["quality"] is None
    assert weighted_score(breakdown, WEIGHTS) is None
    report = composite_report(r, breakdown, WEIGHTS, n_configs=1)
    assert report["quality_not_measured"] is True
    assert report["score"] is None


def test_missing_memory_is_excluded_and_weight_redistributed():
    # Hardware RAM is known but no process/RAM measurement exists.
    r = make_result(ram=None)
    breakdown = score_result_breakdown(r, _bounds([r]), _hardware(vram=None), 8192, WEIGHTS)
    assert breakdown["memory_efficiency"] is None
    # Quality is measured, so the composite still exists; the missing
    # component's weight is redistributed over the measured ones.
    score = weighted_score(breakdown, WEIGHTS)
    assert score is not None
    assert 0.0 <= score <= 1.0
    report = composite_report(r, breakdown, WEIGHTS, n_configs=1)
    assert "memory_efficiency" in report["excluded"]


def test_compute_memory_score_returns_none_without_measurement():
    assert compute_memory_score(None, None, 6.0, 32.0) is None
    assert compute_memory_score(None, None, None, 16.0) is None


def test_single_config_is_not_comparable_three_are():
    r = make_result()
    breakdown = score_result_breakdown(r, _bounds([r]), _hardware(), 8192, WEIGHTS)
    assert composite_report(r, breakdown, WEIGHTS, n_configs=1)["comparable"] is False
    assert composite_report(r, breakdown, WEIGHTS, n_configs=3)["comparable"] is True


def test_context_never_rewards_exceeding_the_workload_target():
    assert workload_target_context("interactive") == 8192
    assert workload_target_context("long_doc") == 32768
    assert normalize_context(4096, 8192) == pytest.approx(0.5)
    assert normalize_context(8192, 8192) == 1.0
    assert normalize_context(16384, 8192) == 1.0


def test_composite_is_monotone_in_generation_speed_and_quality():
    slow = make_result(gen=10.0, quality=0.90)
    fast = make_result(gen=20.0, quality=0.90)
    bounds = _bounds([slow, fast])
    b_slow = score_result_breakdown(slow, bounds, _hardware(), 8192, WEIGHTS)
    b_fast = score_result_breakdown(fast, bounds, _hardware(), 8192, WEIGHTS)
    assert weighted_score(b_fast, WEIGHTS) >= weighted_score(b_slow, WEIGHTS)

    low = make_result(quality=0.90)
    high = make_result(quality=1.00)
    bounds = _bounds([low, high])
    b_low = score_result_breakdown(low, bounds, _hardware(), 8192, WEIGHTS)
    b_high = score_result_breakdown(high, bounds, _hardware(), 8192, WEIGHTS)
    assert weighted_score(b_high, WEIGHTS) >= weighted_score(b_low, WEIGHTS)
