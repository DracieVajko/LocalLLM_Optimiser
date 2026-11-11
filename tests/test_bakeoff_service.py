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


def test_bakeoff_settings_match_an_equivalent_cli_run():
    from lm_optimizer.services import sandbox_history as sh

    bakeoff_settings = bakeoff.task_settings(
        thinking=False,
        reasoning_effort="on",
        context=8192,
        max_output_tokens=2048,
        kv_ram=False,
        safe=False,
    )
    cli_settings = sh.settings_from_reasoning(
        "off", context_length=8192, max_output_tokens=2048
    )
    assert sh.fingerprint("m", "email_write", "p", bakeoff_settings) == sh.fingerprint(
        "m", "email_write", "p", cli_settings
    )


def test_bakeoff_thinking_or_context_changes_the_test_identity():
    from lm_optimizer.services import sandbox_history as sh

    base = bakeoff.task_settings(
        thinking=False,
        reasoning_effort="on",
        context=8192,
        max_output_tokens=2048,
        kv_ram=False,
        safe=False,
    )
    thinking = bakeoff.task_settings(
        thinking=True,
        reasoning_effort="on",
        context=8192,
        max_output_tokens=2048,
        kv_ram=False,
        safe=False,
    )
    small = bakeoff.task_settings(
        thinking=False,
        reasoning_effort="on",
        context=4096,
        max_output_tokens=2048,
        kv_ram=False,
        safe=False,
    )
    keys = {
        sh.fingerprint("m", "t", "p", settings) for settings in (base, thinking, small)
    }
    assert len(keys) == 3
