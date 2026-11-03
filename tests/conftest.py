"""Shared pytest fixtures for the top-level test tree."""

import pytest


@pytest.fixture(autouse=True)
def _isolated_benchmark_cache(tmp_path, monkeypatch):
    """Give every test its own benchmark memo so cases cannot leak across tests."""
    monkeypatch.setenv(
        "LM_OPTIMIZER_BENCHMARK_CACHE", str(tmp_path / "benchmark_cache")
    )
