"""WP-3: coding_task must grade the code, not the words around it.

The hidden tests run the model's function for real.  Correct code that ends in
``return result`` or starts with ``from __future__ import annotations`` must
pass; an O(n^2) implementation that *says* "O(n)" in its docstring must fail
the performance cases.
"""

from __future__ import annotations

import time

from lm_optimizer.benchmark.suite import BENCHMARK_SUITE
from lm_optimizer.services.code_runner import (
    check_code_structure,
    run_find_duplicates,
)
from lm_optimizer.services.quality import QualityEvaluator

CORRECT_SET = '''
def find_duplicates(nums):
    seen = set()
    dupes = set()
    for n in nums:
        if n in seen:
            dupes.add(n)
        else:
            seen.add(n)
    return sorted(dupes)
'''

CORRECT_COUNTER = '''
from collections import Counter

def find_duplicates(nums):
    return sorted(n for n, count in Counter(nums).items() if count > 1)
'''

CORRECT_FUTURE = '''
from __future__ import annotations


def find_duplicates(nums: list[int]) -> list[int]:
    """Return duplicate integers in ascending order."""
    seen: set[int] = set()
    dupes: set[int] = set()
    for n in nums:
        if n in seen:
            dupes.add(n)
        else:
            seen.add(n)
    return sorted(dupes)
'''

RETURN_EMPTY = '''
def find_duplicates(nums):
    return []
'''

QUADRATIC = '''
def find_duplicates(nums):
    """O(n) time linear, O(1) space."""
    return sorted({x for x in nums if nums.count(x) > 1})
'''

INFINITE_LOOP = '''
def find_duplicates(nums):
    while True:
        pass
'''

OS_SYSTEM = '''
import os

def find_duplicates(nums):
    os.system("echo hidden-runner")
    return []
'''

RETURN_RESULT = '''
def find_duplicates(nums):
    seen = set()
    result = []
    for n in nums:
        if n in seen and n not in result:
            result.append(n)
        seen.add(n)
    return result
'''


def test_correct_set_passes():
    ok, detail = run_find_duplicates(CORRECT_SET)
    assert ok, detail


def test_correct_counter_passes():
    ok, detail = run_find_duplicates(CORRECT_COUNTER)
    assert ok, detail


def test_future_import_passes():
    ok, detail = run_find_duplicates(CORRECT_FUTURE)
    assert ok, detail


def test_code_ending_in_return_result_passes():
    ok, detail = run_find_duplicates(RETURN_RESULT)
    assert ok, detail


def test_return_empty_fails():
    ok, detail = run_find_duplicates(RETURN_EMPTY)
    assert not ok
    assert "hidden case" in detail.lower()


def test_quadratic_implementation_fails_performance():
    started = time.perf_counter()
    ok, detail = run_find_duplicates(QUADRATIC, perf_timeout_s=1.0)
    elapsed = time.perf_counter() - started
    assert not ok
    assert "performance" in detail.lower()
    # Must be bounded by the performance budget, not the 10 s correctness timeout.
    assert elapsed < 8.0


def test_infinite_loop_times_out():
    ok, detail = run_find_duplicates(INFINITE_LOOP, timeout_s=1.0)
    assert not ok
    assert "timed out" in detail.lower()


def test_os_system_call_does_not_hang_the_suite():
    started = time.perf_counter()
    ok, detail = run_find_duplicates(OS_SYSTEM, timeout_s=5.0)
    elapsed = time.perf_counter() - started
    assert not ok
    assert elapsed < 4.0


def test_structure_accepts_imports_docstring_and_one_function():
    parses, clean, detail = check_code_structure(CORRECT_FUTURE)
    assert parses
    assert clean, detail


def test_structure_rejects_syntax_error():
    parses, clean, detail = check_code_structure("def find_duplicates(:\n    pass")
    assert not parses
    assert not clean


def test_structure_rejects_extra_module_statements():
    code = CORRECT_SET + "\nclass Extra:\n    pass\n"
    parses, clean, detail = check_code_structure(code)
    assert parses
    assert not clean
    assert "Extra" in detail or "class" in detail.lower()


def test_quality_scores_correct_code_without_complexity_words():
    ev = QualityEvaluator()
    score = ev.evaluate("m", "coding_task", CORRECT_SET)
    assert score.coding_correctness == 1.0
    assert not score.critical_checks_failed
    assert ev.passes_threshold(score), score.details


def test_quality_rejects_quadratic_code_with_o_n_docstring():
    ev = QualityEvaluator()
    score = ev.evaluate("m", "coding_task", QUADRATIC)
    assert score.coding_correctness == 0.0
    assert score.critical_checks_failed
    assert not ev.passes_threshold(score)


def test_quality_rejects_syntax_error():
    ev = QualityEvaluator()
    score = ev.evaluate("m", "coding_task", "def find_duplicates(:\n    pass")
    assert score.critical_checks_failed
    assert not ev.passes_threshold(score)


def test_coding_prompt_allows_extra_memory():
    prompt = next(p for p in BENCHMARK_SUITE if p.name == "coding_task")
    assert "O(1) extra space" not in prompt.prompt
    assert "extra memory is allowed" in prompt.prompt


def test_suite_declares_no_stop_sequences():
    # LM Studio rejects `stop`; a `}` stop would cut a nested JSON object.
    offenders = {p.name: p.stop_sequences for p in BENCHMARK_SUITE if p.stop_sequences}
    assert offenders == {}
