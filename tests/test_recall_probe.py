"""Unit tests for the deterministic context-recall probe (WP C2)."""

from __future__ import annotations

from lm_optimizer.services.recall_probe import (
    FILLER_PARAGRAPHS,
    DISTRACTORS,
    NEEDLE,
    NEEDLE_KEY,
    build_recall_prompt,
    grade_answer,
    normalise_answer,
    estimate_cost_s,
    RecallProbeSpec,
)


class TestPromptConstruction:
    def test_prompt_contains_needle_once(self):
        spec = RecallProbeSpec(target_tokens=8192)
        prompt = build_recall_prompt(spec)
        assert prompt.count(NEEDLE) == 1
        assert NEEDLE_KEY not in normalise_answer(prompt.replace(NEEDLE, ""))
        for d in DISTRACTORS:
            assert d in prompt

    def test_filler_not_degenerate(self):
        spec = RecallProbeSpec(target_tokens=8192)
        prompt = build_recall_prompt(spec)
        # At least 3 of 4 paragraphs used
        used = sum(1 for p in FILLER_PARAGRAPHS if p in prompt)
        assert used >= 3
        # No consecutive duplicate paragraphs
        for i in range(len(FILLER_PARAGRAPHS) - 1):
            assert FILLER_PARAGRAPHS[i] != FILLER_PARAGRAPHS[i + 1]

    def test_prompt_length_target(self):
        for target in [2048, 8192, 16384]:
            spec = RecallProbeSpec(target_tokens=target)
            prompt = build_recall_prompt(spec)
            target_chars = int(target * 0.85 * 3.2)
            assert len(prompt) >= 0.9 * target_chars, (
                f"target={target}: {len(prompt)} < {0.9 * target_chars}"
            )

    def test_chars_per_token_override(self):
        spec = RecallProbeSpec(target_tokens=4096, chars_per_token=4.0)
        prompt = build_recall_prompt(spec)
        assert len(prompt) > 0


class TestGrading:
    def test_grade_pass(self):
        for ans in ["CODE-7TANGO-4423", "**CODE-7TANGO-4423**", "7tango4423", "code-7tango-4423"]:
            status, norm = grade_answer(ans)
            assert status == "pass", f"{ans!r} -> {status}"

    def test_grade_hallucinated(self):
        status, norm = grade_answer("CODE-4DELTA-0004")
        assert status == "fail_hallucinated"

    def test_grade_not_found(self):
        for ans in ["I cannot find that in the document.", "", "unknown", "not stated"]:
            status, _ = grade_answer(ans)
            assert status == "fail_not_found", f"{ans!r} -> {status}"

    def test_grade_ambiguous(self):
        status, _ = grade_answer("CODE-7TANGO-4423 and CODE-4DELTA-0004")
        assert status == "fail_ambiguous"


class TestCostModel:
    def test_estimate_cost(self):
        est = estimate_cost_s(8192, 0.85, 19.0)
        assert est > 0
        # ~7000 tokens / 19 tok/s = 368s + 30s load + 5s = ~403s
        assert 300 < est < 600

    def test_cost_cap(self):
        # estimate should exceed cap
        est = estimate_cost_s(65536, 0.85, 20.0)
        assert est > 900.0


class TestTruncationGate:
    def test_normalise_answer(self):
        assert normalise_answer("Code-7Tango-4423!") == "CODE7TANGO4423"
        assert normalise_answer("") == ""

    def test_needle_key_not_in_filler(self):
        spec = RecallProbeSpec(target_tokens=8192)
        prompt = build_recall_prompt(spec)
        # Remove the needle line and check NEEDLE_KEY not in rest
        without_needle = prompt.replace(NEEDLE, "")
        assert NEEDLE_KEY not in normalise_answer(without_needle)


class TestRecallProbeSpec:
    def test_defaults(self):
        spec = RecallProbeSpec(target_tokens=4096)
        assert spec.fill_ratio == 0.85
        assert spec.depth == 0.5
        assert spec.max_tokens == 24
        assert spec.temperature == 0.0
        assert spec.max_probe_cost_s == 900.0
