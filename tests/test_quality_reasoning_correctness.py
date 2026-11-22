"""WP-2: reasoning correctness — grade the answer, not the length."""

from __future__ import annotations

from lm_optimizer.benchmark.suite import BENCHMARK_SUITE, BenchmarkPrompt
from lm_optimizer.services.quality import QualityEvaluator


def _reasoning_prompt():
    return next(p for p in BENCHMARK_SUITE if p.name == "medium_reasoning")


def test_wrong_answer_long_passes_no_longer():
    ev = QualityEvaluator()
    prompt = _reasoning_prompt()
    output = "80 " + ("pattern difference add sequence " * 20)
    score = ev.evaluate("m", "medium_reasoning", output)
    # Wrong answer must not pass.
    assert score.factual_consistency == 0.0
    assert not ev.passes_threshold(score)


def test_correct_answer_short_passes():
    ev = QualityEvaluator()
    output = "The next number is 72."
    score = ev.evaluate("m", "medium_reasoning", output)
    assert score.factual_consistency == 1.0
    assert ev.passes_threshold(score)


def test_buried_72_final_80_fails():
    ev = QualityEvaluator()
    output = "The sequence has 72 in it, but the next number is 80."
    score = ev.evaluate("m", "medium_reasoning", output)
    assert score.factual_consistency == 0.0


def test_answer_colon_passes():
    ev = QualityEvaluator()
    output = "Answer: 72"
    score = ev.evaluate("m", "medium_reasoning", output)
    assert score.factual_consistency == 1.0


def test_seventy_two_passes():
    ev = QualityEvaluator()
    # "seventy-two" is words; the extractor looks for digits. Accept either.
    output = "The next number is seventy-two (72)."
    score = ev.evaluate("m", "medium_reasoning", output)
    assert score.factual_consistency == 1.0


def test_think_tags_stripped():
    ev = QualityEvaluator()
    output = "<think>let me think</think>\nThe next number is 72."
    score = ev.evaluate("m", "medium_reasoning", output)
    assert score.factual_consistency == 1.0


def test_task_completion_not_word_count():
    ev = QualityEvaluator()
    # Short but complete answer.
    output = "The next number is 72."
    score = ev.evaluate("m", "medium_reasoning", output)
    assert score.task_completion >= 0.5
