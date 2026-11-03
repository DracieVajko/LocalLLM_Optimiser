"""Shared optimization workflow used by the CLI, API and auto-run.

The CLI, FastAPI routes and auto-run previously each built the benchmark
service, quality evaluator, search generator and optimizer by hand. This
module owns that composition so the flag list and defaults cannot drift.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lm_optimizer.domain.models import (
    HardwareInfo,
    ModelIdentity,
    OptimizationProfile,
    OptimizationRun,
)
from lm_optimizer.services.advanced_settings import AdvancedSettings
from lm_optimizer.services.benchmark import BenchmarkConfig, build_benchmark_service
from lm_optimizer.services.optimizer import AdaptiveOptimizer
from lm_optimizer.services.quality import QualityConfig, QualityEvaluator
from lm_optimizer.services.search_space import SearchSpaceGenerator


def build_optimizer(
    client: Any,
    settings: AdvancedSettings | Mapping[str, Any] | None = None,
    *,
    style: str | None = None,
    quality_threshold: float = 0.97,
    benchmark_config: BenchmarkConfig | None = None,
    gpu_via_cli: bool | None = None,
) -> AdaptiveOptimizer:
    """Compose the benchmark/quality/search services into an optimizer."""
    values = AdvancedSettings.coerce(settings)
    benchmark_service = build_benchmark_service(
        client,
        values,
        benchmark_config=benchmark_config,
        style=style,
        gpu_via_cli=gpu_via_cli,
    )
    quality_evaluator = QualityEvaluator(QualityConfig(minimum_score=quality_threshold))
    search_generator = SearchSpaceGenerator(client)
    return AdaptiveOptimizer(
        client, benchmark_service, quality_evaluator, search_generator
    )


async def run_optimization_workflow(
    client: Any,
    model: ModelIdentity,
    hardware: HardwareInfo,
    profile_name: str,
    *,
    quality_threshold: float = 0.97,
    repetitions: int = 3,
    style: str = "balanced",
    settings: AdvancedSettings | Mapping[str, Any] | None = None,
    max_tokens_scale: float = 1.0,
    gpu_via_cli: bool | None = None,
    progress_cb=None,
) -> OptimizationRun:
    """Prepare and execute one run with the shared service composition."""
    values = AdvancedSettings.coerce(settings)
    config_obj = BenchmarkConfig(
        repetitions=max(1, int(repetitions)),
        warmup_repetitions=values.warmup_runs,
        max_tokens_scale=max_tokens_scale,
    )
    optimizer = build_optimizer(
        client,
        values,
        style=style,
        quality_threshold=quality_threshold,
        benchmark_config=config_obj,
        gpu_via_cli=gpu_via_cli,
    )
    return await optimizer.optimize(
        model,
        hardware,
        OptimizationProfile(profile_name),
        quality_threshold=quality_threshold,
        advanced_settings=values,
        style=style,
        progress_cb=progress_cb,
    )


__all__ = ["build_optimizer", "run_optimization_workflow"]
