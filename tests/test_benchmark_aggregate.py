"""Aggregate metrics preserve the underlying failed-test error."""

from unittest.mock import MagicMock

from lm_optimizer.domain.models import BenchmarkMetrics, LoadConfiguration
from lm_optimizer.services.benchmark import BenchmarkService


def test_all_runs_failed_preserves_first_error():
    service = BenchmarkService(MagicMock())
    metrics = [
        BenchmarkMetrics(
            test_name="short_instruction",
            category="instruction",
            success=False,
            error="Server error '500 Internal Server Error'",
        ),
        BenchmarkMetrics(
            test_name="short_instruction",
            category="instruction",
            success=False,
            error="Server error '500 Internal Server Error'",
        ),
    ]

    result = service._aggregate_results(
        "cfg-1",
        "model",
        LoadConfiguration(context_length=2048),
        LoadConfiguration(context_length=2048),
        2048,
        metrics,
        0.0,
    )

    assert result.status == "failed"
    assert len(result.metrics) == 1
    assert result.metrics[0].success is False
    assert "500 Internal Server Error" in (result.metrics[0].error or "")
