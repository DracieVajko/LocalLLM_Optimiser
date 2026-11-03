"""Per-model depth questions (no yes/no chains)."""

import pytest

from lm_optimizer.services.test_selection import (
    ask_min_context_speed,
    ask_model_depth,
    merge_skip_phases,
    parse_depth_choice,
    parse_min_speed,
)


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("1", "quick"),
        ("q", "quick"),
        ("2", "standard"),
        ("3", "full"),
        ("f", "full"),
        ("4", "benchmark"),
        ("b", "benchmark"),
        ("5", None),
        ("skip", None),
    ],
)
def test_choice_aliases(answer, expected):
    assert parse_depth_choice(answer, "standard") == expected


def test_empty_answer_keeps_default():
    assert parse_depth_choice("", "full") == "full"
    assert parse_depth_choice(None, "quick") == "quick"


def test_unknown_choice_is_rejected():
    with pytest.raises(ValueError):
        parse_depth_choice("turbo", "standard")


def test_default_skip_skips_the_model():
    assert parse_depth_choice("", "skip") is None


def test_min_speed_parses_numbers_and_rejects_negatives():
    assert parse_min_speed("2.5", 1.0) == 2.5
    assert parse_min_speed("", 1.0) == 1.0
    with pytest.raises(ValueError):
        parse_min_speed("fast", 1.0)
    with pytest.raises(ValueError):
        parse_min_speed("-1", 1.0)


def test_merge_skip_phases_unions_and_deduplicates():
    assert merge_skip_phases("context", "quality,context") == "context,quality"
    assert merge_skip_phases(None, None) is None
    assert merge_skip_phases(None, "quality") == "quality"


def test_ask_model_depth_prints_one_menu_and_returns_the_choice():
    printed = []
    level = ask_model_depth(
        "qwen/qwen3-coder-30b",
        "standard",
        input_fn=lambda _prompt: "3",
        print_fn=printed.append,
    )
    assert level == "full"
    text = "\n".join(printed)
    assert "qwen/qwen3-coder-30b" in text
    assert "quick" in text and "benchmark" in text and "skip" in text


def test_ask_model_depth_reasks_after_bad_input():
    answers = iter(["nonsense", "2"])

    def fake_input(_prompt):
        return next(answers)

    level = ask_model_depth("m", "standard", input_fn=fake_input, print_fn=lambda _l: None)
    assert level == "standard"


def test_ask_model_depth_eof_uses_default():
    def eof(_prompt):
        raise EOFError

    assert ask_model_depth("m", "quick", input_fn=eof, print_fn=lambda _l: None) == "quick"


def test_ask_min_context_speed_defaults_on_empty_or_eof():
    assert ask_min_context_speed(input_fn=lambda _p: "", print_fn=lambda _l: None) == 1.0

    def eof(_prompt):
        raise EOFError

    assert ask_min_context_speed(input_fn=eof, print_fn=lambda _l: None) == 1.0
