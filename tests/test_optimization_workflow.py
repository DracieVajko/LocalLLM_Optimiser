"""Shared optimization workflow composition and delegation."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from lm_optimizer.domain.models import (
    HardwareInfo,
    ModelIdentity,
    OptimizationProfile,
    OptimizationRun,
    RunStatus,
)
from lm_optimizer.services import optimization_workflow


def _run() -> OptimizationRun:
    return OptimizationRun(
        model=ModelIdentity(id="m", name="m"),
        profile=OptimizationProfile.BALANCED,
        status=RunStatus.RUNNING,
    )


def test_run_workflow_builds_config_and_delegates(monkeypatch):
    captured = {}
    run = _run()

    class FakeOptimizer:
        async def optimize(self, model, hardware, profile, **kwargs):
            captured.update(
                model=model,
                hardware=hardware,
                profile=profile,
                kwargs=kwargs,
            )
            return run

    def fake_build(client, settings, **kwargs):
        captured["settings"] = settings
        captured["build_kwargs"] = kwargs
        return FakeOptimizer()

    monkeypatch.setattr(optimization_workflow, "build_optimizer", fake_build)

    model = ModelIdentity(id="m", name="m")
    hardware = HardwareInfo(
        os="Windows",
        cpu_name="cpu",
        cpu_cores_physical=1,
        cpu_cores_logical=2,
        total_ram_gb=8.0,
        gpu_count=0,
    )
    result = asyncio.run(
        optimization_workflow.run_optimization_workflow(
            MagicMock(),
            model,
            hardware,
            "balanced",
            quality_threshold=0.9,
            repetitions=4,
            style="precise",
            settings={"warmup_runs": 2, "skip_phases": ["quality"]},
            max_tokens_scale=0.75,
            gpu_via_cli=True,
            progress_cb=None,
        )
    )

    assert result is run
    assert captured["settings"].warmup_runs == 2
    config = captured["build_kwargs"]["benchmark_config"]
    assert config.repetitions == 4
    assert config.warmup_repetitions == 2
    assert config.max_tokens_scale == 0.75
    assert captured["build_kwargs"]["quality_threshold"] == 0.9
    assert captured["profile"] == OptimizationProfile.BALANCED
    assert captured["kwargs"]["advanced_settings"].skip_phases == ["quality"]


def test_build_optimizer_composes_services():
    client = MagicMock()
    client.capabilities = MagicMock()
    optimizer = optimization_workflow.build_optimizer(
        client, {"style": "precise"}, quality_threshold=0.8
    )

    assert optimizer.benchmark.style == "precise"
    assert optimizer.quality.config.minimum_score == 0.8
    assert optimizer.client is client
