"""Deterministic quality-score model."""

from dataclasses import dataclass, field

@dataclass
class QualityScore:
    """Correctness / quality assessment result.

    This is NOT an objective model quality percentage. It represents
    deterministic heuristic checks (JSON validation, keyword presence,
    code structure, truncation, repetition). Display as
    'Correctness Score' or 'X / Y checks passed', not as precise
    '99.1% quality'. See docs/OPTIMIZATION_METHOD.md.
    """

    overall: float
    task_completion: float
    factual_consistency: float
    format_compliance: float
    coding_correctness: float
    no_truncation: float
    no_malformed: float
    confident: bool = True
    details: dict = field(default_factory=dict)
    checks_passed: int | None = None
    checks_total: int | None = None

    def as_checks_str(self) -> str:
        """Human-readable checks summary."""
        total = self.checks_total
        passed = self.checks_passed
        if total and passed is not None:
            return f"{passed} / {total} checks passed"
        # Fallback: derive from overall (6 dimensions)
        # Count how many dimensions scored >= 0.9 as passed
        dims = [
            self.task_completion,
            self.factual_consistency,
            self.format_compliance,
            self.coding_correctness,
            self.no_truncation,
            self.no_malformed,
        ]
        passed = sum(1 for d in dims if d >= 0.9)
        return f"{passed} / {len(dims)} checks passed"
