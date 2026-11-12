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


def test_kv_cache_quantization_is_part_of_the_test_identity():
    from lm_optimizer.services import sandbox_history as sh

    def settings(kv_quant):
        return bakeoff.task_settings(
            thinking=False,
            reasoning_effort="on",
            context=4096,
            max_output_tokens=2048,
            kv_ram=False,
            safe=True,
            kv_quant=kv_quant,
        )

    keys = {
        sh.fingerprint("m", "t", "p", settings(value))
        for value in (None, "q4", "q5", "q8")
    }
    assert len(keys) == 4
    assert settings("q8")["kv_quant"] == "q8"
    assert settings("F16")["kv_quant"] is None


def test_attempt_rows_merge_generation_and_scoring():
    """The bakeoff row's attempts must carry attempt/passed/score, not just
    generation timing - the UI renders them and 0/None reads as a lost run."""
    from lm_optimizer.services.bakeoff import _merge_attempt_details

    gen = [{"gen_s": 10.0, "tokens": 120, "tok_s": 12.0}]
    scored = [
        {
            "attempt": 0,
            "passed": True,
            "score": 0.85,
            "error": "",
            "duration_s": 12.5,
            "failing_checks": [],
        }
    ]

    merged = _merge_attempt_details(gen, scored)

    assert merged[0]["attempt"] == 0
    assert merged[0]["passed"] is True
    assert merged[0]["score"] == 0.85
    assert merged[0]["duration_s"] == 12.5
    assert merged[0]["gen_s"] == 10.0  # generation metrics preserved
    assert merged[0]["tokens"] == 120


def test_merge_keeps_generation_rows_without_scoring():
    from lm_optimizer.services.bakeoff import _merge_attempt_details

    assert _merge_attempt_details([{"gen_s": 1.0}], []) == [{"gen_s": 1.0}]
