"""Correctness / quality evaluation service.

Uses deterministic heuristics; see docs/OPTIMIZATION_METHOD.md for
what the score actually measures and display guidance.
"""

import json
import re
from dataclasses import dataclass

from lm_optimizer.config import config
from lm_optimizer.domain.models import BenchmarkMetrics, QualityScore
from lm_optimizer.logging_config import get_logger
from lm_optimizer.services.benchmark import BENCHMARK_SUITE, BenchmarkCase

logger = get_logger(__name__)

# Calibrated pass/fail floor. A long-context answer that is correct but not
# perfect lands at 0.85-0.95, so a 0.97+ profile threshold rejected every
# model. The floor is what the run is judged against; the profile threshold is
# kept for ranking/reporting.
QUALITY_GATE_FLOOR = 0.90


_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}


def _word_to_number(text: str) -> int | None:
    """Best-effort conversion of English number words to an int."""
    text = text.lower().replace("-", " ")
    tokens = text.split()
    total = 0
    found = False
    for tok in tokens:
        if tok in _ONES:
            total += _ONES[tok]
            found = True
        elif tok in _TENS:
            total += _TENS[tok]
            found = True
    if not found:
        return None
    return total


def _checks_from_scores(scores: dict) -> tuple[int, int]:
    total = len(scores)
    passed = sum(1 for v in scores.values() if v >= 0.9)
    return passed, total


# Closers that complete a thought (accepted as proper endings after markdown
# closers like *, `, # are stripped). Mid-sentence cutoffs still fail.
_END_PUNCT = (".", "!", "?", ")", '"', "'", "]", "}")
_MD_CLOSERS = "*`#_~"


def _strip_markdown_closers(text: str) -> str:
    """Remove trailing markdown closers so punctuation underneath can be judged."""
    return text.strip().rstrip(_MD_CLOSERS)


def _ends_properly(text: str) -> bool:
    """Proper ending: real closing punctuation, not a mid-sentence cutoff."""
    stripped = _strip_markdown_closers(text)
    return bool(stripped) and stripped[-1] in _END_PUNCT


def _strip_fences(output: str) -> str:
    """Remove one pair of ``` code fences (the server rejects `stop`, so models
    fence code by default; judge the code inside, not the wrapper)."""
    s = output.strip()
    if s.startswith("```"):
        lines = s.split("\n", 1)
        s = lines[1] if len(lines) > 1 else ""
        if s.rstrip().endswith("```"):
            s = s.rstrip()
            s = s[: -len("```")].rstrip()
    return s


def _words_for_repetition(text: str) -> list[str]:
    """Content words for repetition detection (markup like ** does not count)."""
    return re.sub(r"[*`#_~>|]", " ", text).split()


def _extract_json_object(text: str) -> str | None:
    """Extract the first balanced {...} object (string-aware brace matching).

    Reasoning models often think aloud before the JSON. Strict parsing stays
    first; this is only the penalized fallback, never the primary path.
    """
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _think_tags_balanced(text: str) -> bool:
    """False when closing </think> tags outnumber opening <think> tags."""
    opens = len(re.findall(r"<think(?:\s[^>]*)?>", text, re.IGNORECASE))
    closes = len(re.findall(r"</think\s*>", text, re.IGNORECASE))
    return closes <= opens


@dataclass
class QualityConfig:
    """Correctness / quality evaluation configuration (heuristic checks)."""

    minimum_score: float = 0.97  # target quality (aspiration for ranking)
    hard_gate_threshold: float = 0.90  # hard pass/fail floor


class QualityEvaluator:
    """Evaluates output quality against reference expectations."""

    def __init__(self, quality_config: QualityConfig | None = None):
        self.config = quality_config or QualityConfig(
            minimum_score=config.optimization.minimum_quality_score
        )
        self.reference_outputs: dict[str, dict[str, str]] = {}

    def set_reference_outputs(self, model_id: str, outputs: dict[str, str]) -> None:
        """Set reference outputs for a model (from baseline config)."""
        self.reference_outputs[model_id] = outputs

    def evaluate(self, model_id: str, test_name: str, output: str) -> QualityScore:
        """Evaluate a single test output."""
        prompt_def = self._get_prompt_def(test_name)
        if not prompt_def:
            # Never award unearned quality: an unknown test has no criteria,
            # so it cannot contribute a passing score to the aggregate.
            return QualityScore(
                overall=0.0,
                task_completion=0.0,
                factual_consistency=0.0,
                format_compliance=0.0,
                coding_correctness=0.0,
                no_truncation=0.0,
                no_malformed=0.0,
                confident=False,
                details={"reason": "Unknown test: no criteria"},
                checks_passed=0,
                checks_total=0,
            )

        if prompt_def.category == "format":
            return self._evaluate_format(output, prompt_def)
        if prompt_def.category == "coding":
            return self._evaluate_coding(output, prompt_def)
        if prompt_def.category in ("instruction", "reasoning", "context"):
            return self._evaluate_general(output, prompt_def)
        return self._evaluate_general(output, prompt_def)

    def _get_prompt_def(self, test_name: str) -> BenchmarkCase | None:
        """Get benchmark prompt definition.

        Reasoning sweeps create variants named ``<base>_<level>`` (e.g.
        ``medium_reasoning_xhigh``). They share the base prompt's criteria, so
        the level suffix is stripped before lookup; otherwise every reasoning
        output would be "unknown" and silently unscored.
        """
        for p in BENCHMARK_SUITE:
            if p.name == test_name:
                return p
        for suffix in ("_off", "_low", "_medium", "_high", "_xhigh"):
            if test_name.endswith(suffix):
                base = test_name[: -len(suffix)]
                for p in BENCHMARK_SUITE:
                    if p.name == base:
                        return p
        return None

    def _evaluate_format(self, output: str, prompt_def: BenchmarkCase) -> QualityScore:
        """Evaluate structured output (JSON, fences stripped)."""
        details = {}
        scores = {}
        doc = _strip_fences(output)
        if doc != output.strip():
            details["fences_stripped"] = True

        try:
            parsed = json.loads(doc.strip())
            scores["format_compliance"] = 1.0
            details["json_valid"] = True
            details["thinking_outside_json"] = False
        except json.JSONDecodeError as e:
            # Penalized fallback: the model thought aloud before the JSON
            # (reasoning trace outside the object). Extractable structure
            # still counts, but format is halved and the event is flagged
            # for the UI warning — never silently treated as clean.
            fallback = _extract_json_object(doc)
            if fallback is not None:
                try:
                    parsed = json.loads(fallback)
                except json.JSONDecodeError:
                    parsed = None
            else:
                parsed = None
            if parsed is None:
                scores["format_compliance"] = 0.0
                details["json_valid"] = False
                details["json_error"] = str(e)
                # Explicit failed result (0/6), never null checks: invalid output
                # is evidence, not missing evidence. overall 0.0 preserves the
                # failure signal in aggregates.
                return QualityScore(
                    overall=0.0,
                    task_completion=0.0,
                    factual_consistency=1.0,
                    format_compliance=0.0,
                    coding_correctness=1.0,
                    no_truncation=1.0,
                    no_malformed=0.0,
                    confident=True,
                    details=details,
                    checks_passed=0,
                    checks_total=6,
                )
            scores["format_compliance"] = 0.5
            details["json_valid"] = True
            details["thinking_outside_json"] = True

        required = ["name", "age", "skills", "address"]
        missing = [f for f in required if f not in parsed]
        scores["task_completion"] = (
            1.0 if not missing else max(0.0, 1.0 - len(missing) / len(required))
        )
        details["missing_fields"] = missing

        type_ok = True
        if "age" in parsed and not isinstance(parsed["age"], int):
            type_ok = False
        if "skills" in parsed and not isinstance(parsed["skills"], list):
            type_ok = False
        if "address" in parsed and not isinstance(parsed["address"], dict):
            type_ok = False
        scores["factual_consistency"] = 1.0 if type_ok else 0.5
        details["types_correct"] = type_ok

        scores["no_truncation"] = 1.0 if doc.strip().endswith("}") else 0.5
        scores["no_malformed"] = 1.0
        scores["coding_correctness"] = 1.0

        overall = sum(scores.values()) / len(scores)
        passed, total = _checks_from_scores(scores)
        details["checks"] = f"{passed}/{total}"
        return QualityScore(
            overall=overall,
            confident=True,
            details=details,
            checks_passed=passed,
            checks_total=total,
            **scores,
        )

    def _evaluate_coding(self, output: str, prompt_def: BenchmarkCase) -> QualityScore:
        """Evaluate code output (fences stripped: judge the code, not the wrapper).

        Static keyword hunts (``"O(n)"``, ``"sorted"``) are gone: they passed
        an O(n^2) function that merely said "O(n)" in its docstring.  Syntax
        is checked with ``ast.parse`` and the algorithm is run for real.
        """
        details = {}
        scores = {}
        code = _strip_fences(output)
        if code != output.strip():
            details["fences_stripped"] = True

        from lm_optimizer.services.code_runner import code_structure, run_find_duplicates

        structure = code_structure(code)
        details["syntax"] = structure.detail
        details["parses"] = structure.parses
        details["has_function_def"] = structure.has_function

        scores["task_completion"] = 1.0 if structure.has_function else 0.0

        # Hidden behavioural + performance tests: static checks cannot tell a
        # correct algorithm from ``return []`` or O(n^2). Run the function.
        if structure.has_function and structure.parses:
            behaviour_ok, behaviour_detail = run_find_duplicates(code)
        else:
            behaviour_ok, behaviour_detail = False, structure.detail
        details["hidden_tests"] = behaviour_detail
        scores["coding_correctness"] = 1.0 if behaviour_ok else 0.0

        # No factual claim to grade; code correctness carries the weight.
        scores["factual_consistency"] = 1.0
        details["factual_consistency"] = "not_applicable"

        # AST shape: imports, docstring and the single function only.
        scores["format_compliance"] = 1.0 if structure.clean_module else 0.7
        details["clean_output"] = structure.clean_module

        scores["no_truncation"] = 1.0 if structure.parses else 0.0
        scores["no_malformed"] = 1.0 if structure.parses else 0.0

        # A wrong algorithm or unparseable code is a hard failure.
        critical = (not behaviour_ok) or (not structure.parses)

        overall = sum(scores.values()) / len(scores)
        passed, total = _checks_from_scores(scores)
        details["checks"] = f"{passed}/{total}"
        return QualityScore(
            overall=overall,
            confident=True,
            details=details,
            checks_passed=passed,
            checks_total=total,
            critical_checks_failed=critical,
            **scores,
        )

    def _evaluate_general(self, output: str, prompt_def: BenchmarkCase) -> QualityScore:
        """Evaluate general text output."""
        details = {}
        scores = {}

        min_tokens = getattr(prompt_def, "min_tokens", prompt_def.max_tokens // 4)
        # Strip a leading <think>...</think> block before any extraction.
        cleaned_output = re.sub(
            r"^\s*<think>.*?</think>\s*", "", output, count=1, flags=re.DOTALL | re.IGNORECASE
        )
        output_tokens = len(cleaned_output.split())
        # task_completion: non-empty, not truncated, length >= 0.25 * min_tokens.
        # Length can never lower a correct answer below the gate.
        ends_ok = _ends_properly(cleaned_output)
        length_ok = output_tokens >= max(1, int(0.25 * min_tokens))
        scores["task_completion"] = 1.0 if (cleaned_output.strip() and length_ok) else (0.5 if cleaned_output.strip() else 0.0)
        details["output_tokens"] = output_tokens
        details["length_ok"] = length_ok

        if prompt_def.category == "reasoning":
            expected = getattr(prompt_def, "expected_answer", None)
            # Extract final answer = last integer in the last sentence/line that
            # contains answer|therefore|next number|is.
            answer_correct = False
            if expected is not None:
                # Split into sentences/lines.
                lines = re.split(r"(?<=[.!?])\s+|\n", cleaned_output)
                candidate_lines = [
                    ln for ln in lines
                    if re.search(r"answer|therefore|next number|\bis\b", ln, re.IGNORECASE)
                ]
                if candidate_lines:
                    last_line = candidate_lines[-1]
                    nums = re.findall(r"-?\d+", last_line)
                    if nums:
                        try:
                            answer_correct = int(nums[-1]) == int(expected)
                        except (ValueError, TypeError):
                            answer_correct = False
                    else:
                        # Try word numbers.
                        word_val = _word_to_number(last_line)
                        if word_val is not None:
                            answer_correct = word_val == int(expected)
                # Reject when a different final integer is stated after the expected.
                # (already handled: we only look at the last candidate line)
            scores["factual_consistency"] = 1.0 if answer_correct else 0.0
            details["answer_correct"] = answer_correct
            details["expected_answer"] = expected
        elif prompt_def.category == "context":
            keywords = ["solar", "wind", "hydro", "geothermal", "biomass"]
            found = sum(1 for kw in keywords if kw in output.lower())
            scores["factual_consistency"] = min(1.0, found / len(keywords) * 1.5)
            details["keywords_found"] = found
        else:
            scores["factual_consistency"] = 1.0

        scores["format_compliance"] = 1.0
        scores["coding_correctness"] = 1.0

        ends_properly = _ends_properly(output)
        scores["no_truncation"] = 1.0 if ends_properly else 0.5
        details["ends_properly"] = ends_properly

        has_repetition = self._detect_repetition(output)
        scores["no_malformed"] = 0.0 if has_repetition else 1.0
        details["has_repetition"] = has_repetition
        if not _think_tags_balanced(output):
            # Stray </think> without an opener: reasoning leaked as markup.
            scores["no_malformed"] = min(scores["no_malformed"], 0.5)
            details["unbalanced_think_tags"] = True

        overall = sum(scores.values()) / len(scores)
        passed, total = _checks_from_scores(scores)
        details["checks"] = f"{passed}/{total}"
        confident = prompt_def.category in ("instruction", "reasoning", "context")
        # For reasoning tasks, a wrong final answer is a critical failure.
        critical = False
        if prompt_def.category == "reasoning":
            expected = getattr(prompt_def, "expected_answer", None)
            if expected is not None and not details.get("answer_correct", False):
                critical = True
        # Also use the base: task_completion 0 or factual_consistency 0
        if scores.get("task_completion", 1.0) <= 0.0 or scores.get("factual_consistency", 1.0) <= 0.0:
            critical = True
        return QualityScore(
            overall=overall,
            confident=confident,
            details=details,
            checks_passed=passed,
            checks_total=total,
            critical_checks_failed=critical,
            **scores,
        )

    def _detect_repetition(self, text: str, threshold: float = 0.3) -> bool:
        """Detect excessive repetition in output (markup does not count)."""
        words = _words_for_repetition(text)
        if len(words) < 10:
            return False

        for n in [2, 3, 4]:
            ngrams = [tuple(words[i : i + n]) for i in range(len(words) - n + 1)]
            if not ngrams:
                continue
            unique = set(ngrams)
            if len(unique) / len(ngrams) < (1 - threshold):
                return True
        return False

    def evaluate_all(
        self, model_id: str, metrics: list[BenchmarkMetrics]
    ) -> dict[str, QualityScore]:
        """Evaluate all benchmark metrics."""
        results = {}
        for m in metrics:
            if m.success and m.output_text:
                results[m.test_name] = self.evaluate(model_id, m.test_name, m.output_text)
        return results

    def aggregate_quality(self, scores: dict[str, QualityScore]) -> QualityScore:
        """Aggregate quality scores across tests."""
        if not scores:
            return QualityScore(
                overall=0.0,
                task_completion=0.0,
                factual_consistency=0.0,
                format_compliance=0.0,
                coding_correctness=0.0,
                no_truncation=0.0,
                no_malformed=0.0,
                confident=False,
                details={"reason": "No results measured (NOT_MEASURED)"},
                checks_passed=0,
                checks_total=0,
                critical_checks_failed=True,
            )

        confident_scores = [s for s in scores.values() if s.confident]
        if not confident_scores:
            confident_scores = list(scores.values())

        avg = lambda attr: sum(getattr(s, attr) for s in confident_scores) / len(confident_scores)

        total_passed = sum(s.checks_passed or 0 for s in confident_scores)
        total_checks = sum(s.checks_total or 0 for s in confident_scores)

        return QualityScore(
            overall=avg("overall"),
            task_completion=avg("task_completion"),
            factual_consistency=avg("factual_consistency"),
            format_compliance=avg("format_compliance"),
            coding_correctness=avg("coding_correctness"),
            no_truncation=avg("no_truncation"),
            no_malformed=avg("no_malformed"),
            confident=all(s.confident for s in confident_scores),
            details={"per_test": {k: v.overall for k, v in scores.items()}},
            checks_passed=total_passed,
            checks_total=total_checks,
            critical_checks_failed=any(
                getattr(s, "critical_checks_failed", False) for s in scores.values()
            ),
        )

    def passes_threshold(self, quality: QualityScore) -> bool:
        """Two-part gate: no critical check failed AND aggregate >= 0.90.

        The profile threshold stays as an aspiration for ranking, but it no
        longer rejects a run on its own: a single non-critical miss (one weak
        dimension) must not flip the verdict, while an empty answer, invalid
        schema or broken code still fails hard.
        """
        if getattr(quality, "critical_checks_failed", False):
            return False
        threshold = min(self.config.minimum_score, self.config.hard_gate_threshold)
        return quality.overall >= threshold
