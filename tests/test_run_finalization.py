"""Tests for run finalization (R2-2)."""

from __future__ import annotations

from lm_optimizer.domain.run import ConfigurationResult


def test_configuration_result_has_duration_ms():
    """duration_ms field exists and defaults to 0.0."""
    r = ConfigurationResult()
    assert hasattr(r, "duration_ms")
    assert r.duration_ms == 0.0


def test_configuration_result_has_validation_repetitions():
    """validation_repetitions_effective field exists."""
    r = ConfigurationResult()
    assert hasattr(r, "validation_repetitions_effective")
    assert r.validation_repetitions_effective == 1


def test_configuration_result_has_generation():
    """generation field exists for phase timings."""
    r = ConfigurationResult()
    assert hasattr(r, "generation")
