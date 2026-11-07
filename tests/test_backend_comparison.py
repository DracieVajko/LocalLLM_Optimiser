"""Tests for backend comparison service."""

from __future__ import annotations

from lm_optimizer.services.backend_comparison import (
    BackendComparator,
    BackendResult,
    BackendComparison,
    record_backend_result,
    recommend_backend,
    compare_backends,
)


def test_backend_result_composite_score():
    """Composite score calculation."""
    r = BackendResult(
        backend="lmstudio",
        model_id="test-model",
        generation_tok_s=10.0,
        quality_score=0.9,
        stability_score=1.0,
        passed=True,
    )
    # speed_score = min(1.0, 10/10) = 1.0
    # composite = 0.4*1.0 + 0.4*0.9 + 0.2*1.0 = 0.4 + 0.36 + 0.2 = 0.96
    assert abs(r.composite_score - 0.96) < 0.01


def test_backend_result_failed_has_zero_score():
    """Failed backend has zero composite score."""
    r = BackendResult(
        backend="lmstudio",
        model_id="test-model",
        generation_tok_s=10.0,
        quality_score=0.9,
        stability_score=1.0,
        passed=False,
    )
    assert r.composite_score == 0.0


def test_best_backend_selection():
    """Best backend is the one with highest composite score."""
    comp = BackendComparator()
    comp.add_result(BackendResult(
        backend="lmstudio", model_id="m", generation_tok_s=5.0,
        quality_score=0.9, stability_score=1.0, passed=True,
    ))
    comp.add_result(BackendResult(
        backend="ollama", model_id="m", generation_tok_s=8.0,
        quality_score=0.8, stability_score=1.0, passed=True,
    ))
    comp.add_result(BackendResult(
        backend="llamacpp", model_id="m", generation_tok_s=3.0,
        quality_score=0.95, stability_score=1.0, passed=True,
    ))
    comparison = comp.compare("m")
    best = comparison.best_backend
    assert best is not None
    assert best.backend == "ollama"  # best composite score


def test_recommend_backend():
    """recommend_backend returns the best backend name."""
    record_backend_result(
        backend="lmstudio", model_id="m", generation_tok_s=5.0,
        quality_score=0.9, stability_score=1.0, passed=True,
    )
    record_backend_result(
        backend="ollama", model_id="m", generation_tok_s=10.0,
        quality_score=0.9, stability_score=1.0, passed=True,
    )
    best = recommend_backend("m")
    assert best == "ollama"


def test_record_backend_result_singleton():
    """record_backend_result uses global comparator."""
    result = record_backend_result(
        backend="llamacpp",
        model_id="test-model",
        generation_tok_s=7.0,
        quality_score=0.85,
        passed=True,
    )
    assert result.backend == "llamacpp"
    assert result.model_id == "test-model"
    assert result.composite_score > 0


def test_compare_returns_empty_for_unknown_model():
    """Comparing unknown model returns empty results."""
    comparison = compare_backends("unknown-model")
    assert comparison.results == []
    assert comparison.best_backend is None