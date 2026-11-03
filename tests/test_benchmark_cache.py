"""Benchmark case cache: hit avoids a second chat, failures are not cached."""

import os
import tempfile
from pathlib import Path

import pytest

from lm_optimizer.domain.models import BenchmarkCase, BenchmarkMetrics
from lm_optimizer.services import benchmark_cache
from lm_optimizer.services.benchmark_cache import get_cached, store_cached


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("LM_OPTIMIZER_BENCHMARK_CACHE", str(tmp_path))
    return tmp_path


def _case():
    return BenchmarkCase(
        name="short_instruction",
        category="instruction",
        prompt="Say hi.",
        max_tokens=64,
        temperature=0.7,
    )


def _config():
    from lm_optimizer.domain.models import LoadConfiguration

    return LoadConfiguration(context_length=2048, flash_attention=True)


def _metrics():
    return BenchmarkMetrics(
        test_name="short_instruction",
        category="instruction",
        success=True,
        generation_tok_s=42.0,
        output_text="hi",
    )


def test_miss_returns_none(cache_dir):
    assert get_cached("m", _case(), 2048, "off", _config()) is None


def test_store_then_get_returns_equivalent_metrics(cache_dir):
    case = _case()
    cfg = _config()
    store_cached("m", case, 2048, "off", cfg, _metrics())

    hit = get_cached("m", case, 2048, "off", cfg)
    assert hit is not None
    assert hit.success is True
    assert hit.generation_tok_s == 42.0
    assert hit.output_text == "hi"


def test_different_context_is_a_miss(cache_dir):
    case = _case()
    cfg = _config()
    store_cached("m", case, 2048, "off", cfg, _metrics())

    assert get_cached("m", case, 4096, "off", cfg) is None


def test_different_reasoning_is_a_miss(cache_dir):
    case = _case()
    cfg = _config()
    store_cached("m", case, 2048, "off", cfg, _metrics())

    assert get_cached("m", case, 2048, "on", cfg) is None


def test_corrupt_entry_returns_none(cache_dir):
    case = _case()
    cfg = _config()
    path = list(cache_dir.glob("*.json"))[0] if False else None
    # write garbage under the expected key by storing then corrupting
    store_cached("m", case, 2048, "off", cfg, _metrics())
    for p in cache_dir.glob("*.json"):
        p.write_text("{not json", encoding="utf-8")
    assert get_cached("m", case, 2048, "off", cfg) is None
