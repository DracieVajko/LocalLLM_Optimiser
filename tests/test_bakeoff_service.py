"""Bake-off service tests: generic model resolution."""

from __future__ import annotations

import pytest

from lm_optimizer.services import bakeoff


def test_all_models_come_from_the_backend(monkeypatch):
    monkeypatch.setattr(
        bakeoff, "_backend_models", lambda: ["model-a", "model-b"]
    )
    assert bakeoff._resolve_models("all") == ["model-a", "model-b"]
    assert bakeoff._resolve_models("*") == ["model-a", "model-b"]


def test_empty_backend_raises_instead_of_hardcoding(monkeypatch):
    monkeypatch.setattr(bakeoff, "_backend_models", lambda: [])
    with pytest.raises(RuntimeError, match="No models"):
        bakeoff._resolve_models("all")


def test_aliases_and_full_ids_both_work():
    assert bakeoff._resolve_models("e4b") == [bakeoff.CANDIDATES["e4b"]]
    assert bakeoff._resolve_models("vendor/any-model") == ["vendor/any-model"]
