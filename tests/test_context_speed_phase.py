"""Phase integration: every speed run ends with a context-speed ladder."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from lm_optimizer.domain.models import (
    BenchmarkMetrics,
    ConfigurationResult,
    ConfigurationStatus,
    ModelIdentity,
    OptimizationProfile,
    OptimizationRun,
)
from lm_optimizer.services.optimizer import AdaptiveOptimizer, OptimizationState


def _run(context_limit=32768):
    return OptimizationRun(
        model=ModelIdentity(id="m", name="m", context_limit=context_limit),
        profile=OptimizationProfile.BALANCED,
    )


def _winner(tok_s=40.0):
    return ConfigurationResult(
        config=MagicMock(to_dict=lambda: {"context_length": 2048}),
        context_length=2048,
        status=ConfigurationStatus.PASSED,
        metrics=[
            BenchmarkMetrics(
                test_name="speed_probe",
                category="speed",
                success=True,
                generation_tok_s=tok_s,
            )
        ],
    )


def _optimizer(run, monkeypatch):
    state = OptimizationState(run=run, search_space=MagicMock())
    opt = AdaptiveOptimizer.__new__(AdaptiveOptimizer)
    opt.state = state
    opt.client = MagicMock()
    opt._log_event = lambda *a, **k: None
    opt._checkpoint = lambda *a, **k: None
    opt._broadcast = AsyncMock()
    opt._pause_point = AsyncMock()
    opt._sync_phase_params = lambda: None
    monkeypatch.setattr(
        "lm_optimizer.services.optimizer.run_repo.save", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "lm_optimizer.services.optimizer.config_repo.save", lambda *a, **k: None
    )
    return opt


class _FakeBenchmark:
    def __init__(self):
        self.contexts = []

    async def run_speed_probe(self, model_id, cfg, context_length, **kwargs):
        self.contexts.append(context_length)
        tok_s = 100.0 if context_length <= 8192 else 5.0
        return ConfigurationResult(
            config=cfg,
            context_length=context_length,
            status=ConfigurationStatus.PASSED,
            metrics=[
                BenchmarkMetrics(
                    test_name="speed_probe",
                    category="speed",
                    success=True,
                    generation_tok_s=tok_s,
                    estimated_ttft_ms=50.0,
                )
            ],
        )


@pytest.mark.asyncio
async def test_phase_measures_the_doubling_ladder_on_the_speed_winner(monkeypatch):
    run = _run()
    opt = _optimizer(run, monkeypatch)
    benchmark = _FakeBenchmark()
    opt.benchmark = benchmark
    winner = _winner()

    report = await opt._phase_context_speed({"winner": winner})

    assert benchmark.contexts == [2048, 4096, 8192, 16384, 32768]
    assert report["last_passing_context"] == 32768
    assert report["complete"] is True
    assert winner.generation["context_speed"] is report
    assert opt.state.context_speed is report
    assert run.phase == "context_speed"
    assert run.stage.value == "context_speed"


@pytest.mark.asyncio
async def test_phase_stops_at_the_first_load_failure(monkeypatch):
    run = _run(context_limit=65536)
    opt = _optimizer(run, monkeypatch)
    winner = _winner()

    class _FailsAt16k(_FakeBenchmark):
        async def run_speed_probe(self, model_id, cfg, context_length, **kwargs):
            self.contexts.append(context_length)
            if context_length >= 16384:
                return ConfigurationResult(
                    config=cfg,
                    context_length=context_length,
                    status=ConfigurationStatus.FAILED,
                    error="CUDA out of memory",
                )
            return ConfigurationResult(
                config=cfg,
                context_length=context_length,
                status=ConfigurationStatus.PASSED,
                metrics=[
                    BenchmarkMetrics(
                        test_name="speed_probe",
                        category="speed",
                        success=True,
                        generation_tok_s=10.0,
                    )
                ],
            )

    benchmark = _FailsAt16k()
    opt.benchmark = benchmark

    report = await opt._phase_context_speed({"winner": winner})

    assert benchmark.contexts == [2048, 4096, 8192, 16384]
    assert report["last_passing_context"] == 8192
    assert report["failed_context"] == 16384
    assert "out of memory" in report["results"][-1]["error"]


@pytest.mark.asyncio
async def test_phase_falls_back_to_fastest_speed_probe_without_a_winner(monkeypatch):
    run = _run()
    opt = _optimizer(run, monkeypatch)
    opt.benchmark = _FakeBenchmark()
    slow, fast = _winner(10.0), _winner(99.0)
    slow.generation = {"phase": "speed"}
    fast.generation = {"phase": "speed"}
    opt.state.tested_configs = [slow, fast]

    report = await opt._phase_context_speed({"winner": None})

    assert report["winner_config_id"] == str(fast.id)


@pytest.mark.asyncio
async def test_phase_is_a_noop_without_any_passing_speed_config(monkeypatch):
    run = _run()
    opt = _optimizer(run, monkeypatch)
    opt.benchmark = _FakeBenchmark()

    assert await opt._phase_context_speed({"winner": None}) is None


def test_both_execution_paths_call_the_context_speed_phase():
    """Fresh runs and resumed runs must measure the same ladder."""
    import inspect

    from lm_optimizer.services.optimizer import AdaptiveOptimizer

    fresh = inspect.getsource(AdaptiveOptimizer._run_phase_ab)
    resumed = inspect.getsource(AdaptiveOptimizer._resume_phase_pipeline)
    assert "_phase_context_speed" in fresh
    assert "_phase_context_speed" in resumed
    assert "_maybe_run_context_strategies" in resumed


def test_context_speed_is_a_named_skip_phase():
    from lm_optimizer.services.optimizer import (
        PHASE_SKIP_NAMES,
        compose_granular_skips,
        parse_phase_skips,
    )

    assert "context_speed" in PHASE_SKIP_NAMES
    assert parse_phase_skips("context_speed") == {"context_speed"}
    # Granular modes only skip the optional Phase B; the ladder still runs.
    assert "context_speed" not in compose_granular_skips({"speed_only": True})
