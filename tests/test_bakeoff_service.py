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


def test_bakeoff_identity_follows_the_value_actually_sent():
    from lm_optimizer.services import sandbox_history as sh

    def settings(thinking, effort):
        return bakeoff.task_settings(
            thinking=thinking,
            reasoning_effort=effort,
            context=8192,
            max_output_tokens=2048,
            kv_ram=False,
            safe=False,
        )

    # `--thinking --reasoning-effort off` sends reasoning=off, like --no-thinking.
    assert sh.fingerprint("m", "t", "p", settings(True, "off")) == sh.fingerprint(
        "m", "t", "p", settings(False, "on")
    )
    # `--no-thinking --reasoning-effort high` still sends off.
    assert sh.fingerprint("m", "t", "p", settings(False, "high")) == sh.fingerprint(
        "m", "t", "p", settings(False, "on")
    )
    # A real effort level is its own test.
    assert sh.fingerprint("m", "t", "p", settings(True, "high")) != sh.fingerprint(
        "m", "t", "p", settings(True, "on")
    )
