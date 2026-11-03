"""Typed advanced-settings boundary and benchmark service factory."""

from unittest.mock import MagicMock

import pytest

from lm_optimizer.services.advanced_settings import AdvancedSettings
from lm_optimizer.services.benchmark import BenchmarkConfig, build_benchmark_service


def test_defaults_are_exposed_without_mutating_the_mapping():
    settings = AdvancedSettings()

    assert settings.style == "balanced"
    assert settings.workload_type == "interactive"
    assert settings.warmup_runs == 1
    assert settings.max_tokens_scale == 1.0
    assert settings.skip_phases == []
    assert settings.to_dict() == {}


def test_values_are_normalized_and_clamped():
    settings = AdvancedSettings(
        {
            "style": "PRECISE",
            "warmup_runs": 99,
            "max_tokens_scale": 0.01,
            "min_speed": -5,
            "skip_phases": [" quality ", "", "speed"],
        }
    )

    assert settings.style == "precise"
    assert settings.warmup_runs == 5
    assert settings.max_tokens_scale == 0.25
    assert settings.min_speed == 0.0
    assert settings.skip_phases == ["quality", "speed"]


def test_coerce_returns_the_same_instance():
    settings = AdvancedSettings({"style": "creative"})

    assert AdvancedSettings.coerce(settings) is settings
    assert AdvancedSettings.coerce(None).style == "balanced"


def test_invalid_mapping_type_is_rejected():
    with pytest.raises(TypeError):
        AdvancedSettings(["not", "a", "mapping"])  # type: ignore[arg-type]


def test_factory_applies_settings_to_service():
    client = MagicMock()
    settings = AdvancedSettings(
        {
            "style": "precise",
            "warmup_runs": 3,
            "max_tokens_scale": 0.5,
            "speed_only": True,
            "include_categories": ["instruction"],
            "test_names": ["short_instruction"],
        }
    )

    service = build_benchmark_service(client, settings)

    assert service.style == "precise"
    assert service.config.warmup_repetitions == 3
    assert service.config.max_tokens_scale == 0.5
    assert service.speed_only is True
    assert service.include_categories == {"instruction"}
    assert service.test_names == ["short_instruction"]


def test_factory_respects_explicit_benchmark_config_when_key_absent():
    client = MagicMock()
    config = BenchmarkConfig(repetitions=7, warmup_repetitions=0, max_tokens_scale=0.8)

    service = build_benchmark_service(client, AdvancedSettings(), benchmark_config=config)

    assert service.config.repetitions == 7
    assert service.config.warmup_repetitions == 0
    assert service.config.max_tokens_scale == 0.8
