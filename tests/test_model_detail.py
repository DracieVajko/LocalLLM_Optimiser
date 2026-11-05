"""Per-model depth selection for `auto --model-detail`."""

import pytest

from lm_optimizer.cli.auto_run import (
    auto_depth_plan,
    detail_overrides,
    parse_model_detail,
    resolve_model_detail,
)


def test_bare_level_is_a_global_default():
    rules = parse_model_detail("quick")
    assert rules == [("*", "quick")]
    assert resolve_model_detail("anything", rules) == "quick"


def test_specific_pattern_beats_global_default():
    rules = parse_model_detail("*=standard,qwen=benchmark")
    assert resolve_model_detail("qwen/qwen3.6-35b-a3b", rules) == "benchmark"
    assert resolve_model_detail("prism-ml/bonsai-27b", rules) == "standard"


def test_last_matching_specific_rule_wins():
    rules = parse_model_detail("qwen=quick,qwen3=full")
    assert resolve_model_detail("qwen3-coder-30b", rules) == "full"


def test_matching_is_case_insensitive():
    rules = parse_model_detail("MIXTRAL=full")
    assert resolve_model_detail("Dolphin-2.5-Mixtral-8x7B", rules) == "full"


def test_unknown_level_is_rejected():
    with pytest.raises(ValueError, match="unknown detail level"):
        parse_model_detail("qwen=turbo")


def test_rule_without_equals_is_rejected():
    with pytest.raises(ValueError, match="missing '='"):
        parse_model_detail("qwenturbo")


def test_empty_spec_means_no_rules():
    assert parse_model_detail(None) == []
    assert parse_model_detail("   ") == []


def test_quick_uses_minimal_repetitions():
    out = detail_overrides("quick", repetitions=5, validation=7)
    assert out == {
        "repetitions": 1,
        "validation": 2,
        "optimize_context": False,
        "skip_phases": None,
    }


def test_standard_keeps_caller_flags():
    out = detail_overrides("standard", repetitions=3, validation=5)
    assert out["repetitions"] == 3
    assert out["validation"] == 5
    assert out["skip_phases"] is None


def test_full_raises_depth_but_never_lowers_it():
    out = detail_overrides("full", repetitions=1, validation=2)
    assert out["repetitions"] == 3
    assert out["validation"] == 5
    assert out["optimize_context"] is True

    out = detail_overrides("full", repetitions=9, validation=11)
    assert out["repetitions"] == 9
    assert out["validation"] == 11


def test_benchmark_skips_quality_gates():
    out = detail_overrides("benchmark", repetitions=3, validation=5)
    assert out["repetitions"] == 1
    assert out["validation"] == 1
    skipped = set(out["skip_phases"].split(","))
    assert {"quality", "recovery", "validation", "context"} <= skipped


# --- unattended `auto` pipeline knobs ---------------------------------------

def test_auto_quick_skips_the_exploratory_matrix():
    plan = auto_depth_plan("quick", repetitions=3)
    assert plan["repetitions"] == 1
    assert plan["matrix"] is False
    assert plan["optimize_context"] is False
    assert plan["skip_phases"] == []


def test_auto_standard_keeps_caller_matrix_and_skips():
    plan = auto_depth_plan(
        "standard", repetitions=2, skip_phases=["context"], skip_matrix=False
    )
    assert plan["repetitions"] == 2
    assert plan["matrix"] is True
    assert plan["skip_phases"] == ["context"]


def test_auto_full_raises_depth_and_enables_context():
    plan = auto_depth_plan("full", repetitions=1)
    assert plan["repetitions"] == 3
    assert plan["matrix"] is True
    assert plan["optimize_context"] is True


def test_auto_benchmark_merges_user_skips_with_gate_skips():
    plan = auto_depth_plan("benchmark", repetitions=5, skip_phases=["context"])
    assert plan["repetitions"] == 1
    assert plan["matrix"] is True
    assert plan["skip_phases"] == ["context", "quality", "recovery", "validation"]


def test_auto_respects_global_skip_matrix():
    plan = auto_depth_plan("full", repetitions=3, skip_matrix=True)
    assert plan["matrix"] is False


def test_auto_command_exposes_model_detail_option():
    import inspect

    from lm_optimizer.cli.main import app, auto
    from typer.testing import CliRunner

    # 1. The option is registered on the function with the exact name --model-detail.
    sig = inspect.signature(auto)
    assert "model_detail" in sig.parameters
    param = sig.parameters["model_detail"]
    assert "--model-detail" in param.default.param_decls, (
        f"Expected --model-detail in param_decls, got {param.default.param_decls!r}"
    )

    # 2. `auto --help` exposes the option. Rich may truncate long option names
    #    in narrow terminals (e.g. "--model-det…"), so accept either the full
    #    name or any line that clearly refers to this option.
    result = CliRunner().invoke(app, ["auto", "--help"])
    assert result.exit_code == 0
    lines = result.output.splitlines()
    found = any(
        "--model-detail" in line or ("model" in line.lower() and "det" in line.lower())
        for line in lines
    )
    assert found, f"--model-detail not found in help output:\n{result.output}"


def test_auto_model_detail_accepts_valid_value():
    """--model-detail actually reaches the application logic."""
    from typer.testing import CliRunner

    from lm_optimizer.cli.main import app

    # dry-run so no model is actually loaded; --model-detail should be parsed
    # and accepted without error.
    result = CliRunner().invoke(
        app,
        [
            "auto",
            "--model-detail",
            "qwen=quick",
            "--dry-run",
            "--non-interactive",
            "--yes",
        ],
    )
    assert result.exit_code == 0, result.output
