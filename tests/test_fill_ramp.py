"""Tests for the fill-ramp helpers (context explorer Phase 2/3)."""

from __future__ import annotations

from lm_optimizer.services.fill_ramp import (
    fill_ramp_ratios,
    max_usable_fill,
    ramp_stopped_reason,
)


def test_fill_ramp_ratios_default():
    ratios = fill_ramp_ratios()
    assert ratios[0] == 0.0
    assert ratios[-1] == 1.0
    assert len(ratios) == 11  # 0.0..1.0 in 0.1 steps
    assert ratios == [round(i * 0.1, 4) for i in range(11)]


def test_fill_ramp_ratios_custom_step():
    ratios = fill_ramp_ratios(step=0.25)
    assert ratios == [0.0, 0.25, 0.5, 0.75, 1.0]


def test_fill_ramp_ratios_max_ratio():
    ratios = fill_ramp_ratios(step=0.2, max_ratio=0.8)
    assert ratios[-1] == 0.8
    assert 1.0 not in ratios


def test_fill_ramp_ratios_invalid_step():
    ratios = fill_ramp_ratios(step=0)
    assert ratios[0] == 0.0
    assert ratios[-1] == 1.0


def test_max_usable_fill():
    results = [(0.0, True), (0.5, True), (0.9, False), (1.0, False)]
    assert max_usable_fill(results) == 0.5


def test_max_usable_fill_none():
    assert max_usable_fill([(0.5, False), (1.0, False)]) is None


def test_max_usable_fill_empty():
    assert max_usable_fill([]) is None


def test_ramp_stopped_reason_complete():
    assert ramp_stopped_reason(1.0, True) == "complete"


def test_ramp_stopped_reason_oom():
    assert ramp_stopped_reason(0.5, False, "CUDA out of memory") == "oom"


def test_ramp_stopped_reason_http500():
    assert ramp_stopped_reason(0.5, False, "Server error 500") == "oom"


def test_ramp_stopped_reason_timeout():
    assert ramp_stopped_reason(0.5, False, "timed out") == "timeout"


def test_ramp_stopped_reason_garbage():
    assert ramp_stopped_reason(0.5, False, "") == "garbage"
