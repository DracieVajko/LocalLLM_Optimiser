"""Backend comparison service.

Runs benchmarks across all available backends (LM Studio, Ollama, llama.cpp)
and selects the best backend by empirical evidence: generation_tok_s,
TTFT, quality, and stability.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lm_optimizer.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class BackendResult:
    """Benchmark result for a single backend."""

    backend: str
    model_id: str
    generation_tok_s: float = 0.0
    ttft_ms: float = 0.0
    quality_score: float = 0.0
    stability_score: float = 1.0
    vram_gb: float = 0.0
    load_time_ms: float = 0.0
    samples: int = 0
    passed: bool = False
    error: str | None = None

    @property
    def composite_score(self) -> float:
        """Composite score: weighted combination of speed, quality, stability."""
        if not self.passed:
            return 0.0
        # Speed score: normalized against a reference of 10 tok/s
        speed_score = min(1.0, self.generation_tok_s / 10.0)
        # Quality score (0-1)
        quality_score = self.quality_score
        # Stability score (0-1)
        stability_score = self.stability_score
        # Weighted: speed 40%, quality 40%, stability 20%
        return 0.4 * speed_score + 0.4 * quality_score + 0.2 * stability_score


@dataclass
class BackendComparison:
    """Comparison results across all backends."""

    model_id: str
    results: list[BackendResult] = field(default_factory=list)

    @property
    def best_backend(self) -> BackendResult | None:
        """Return the backend with the highest composite score."""
        if not self.results:
            return None
        return max(self.results, key=lambda r: r.composite_score)

    @property
    def best_backend_name(self) -> str | None:
        best = self.best_backend
        return best.backend if best else None


class BackendComparator:
    """Compare backends for a given model and recommend the best one."""

    def __init__(self):
        self.results: dict[str, list[BackendResult]] = {}

    def add_result(self, result: BackendResult) -> None:
        """Add a benchmark result for a backend."""
        key = result.model_id
        if key not in self.results:
            self.results[key] = []
        self.results[key].append(result)
        logger.info(
            "Backend result added",
            backend=result.backend,
            model=result.model_id,
            tok_s=result.generation_tok_s,
            composite=result.composite_score,
        )

    def compare(self, model_id: str) -> BackendComparison:
        """Compare all backends for a model."""
        results = self.results.get(model_id, [])
        return BackendComparison(model_id=model_id, results=results)

    def recommend(self, model_id: str) -> BackendResult | None:
        """Recommend the best backend for a model."""
        comparison = self.compare(model_id)
        return comparison.best_backend

    def get_all_backends(self) -> list[str]:
        """Return all backends that have results."""
        return list(self.results.keys())


# Singleton instance
_comparator: BackendComparator | None = None


def get_comparator() -> BackendComparator:
    """Get the global backend comparator instance."""
    global _comparator
    if _comparator is None:
        _comparator = BackendComparator()
    return _comparator


def record_backend_result(
    backend: str,
    model_id: str,
    generation_tok_s: float,
    ttft_ms: float = 0.0,
    quality_score: float = 0.0,
    stability_score: float = 1.0,
    vram_gb: float = 0.0,
    load_time_ms: float = 0.0,
    samples: int = 1,
    passed: bool = True,
    error: str | None = None,
) -> BackendResult:
    """Record a benchmark result for a backend."""
    result = BackendResult(
        backend=backend,
        model_id=model_id,
        generation_tok_s=generation_tok_s,
        ttft_ms=ttft_ms,
        quality_score=quality_score,
        stability_score=stability_score,
        vram_gb=vram_gb,
        load_time_ms=load_time_ms,
        samples=samples,
        passed=passed,
        error=error,
    )
    get_comparator().add_result(result)
    return result


def recommend_backend(model_id: str) -> str | None:
    """Recommend the best backend for a model."""
    result = get_comparator().recommend(model_id)
    return result.backend if result else None


def compare_backends(model_id: str) -> BackendComparison:
    """Compare all backends for a model."""
    return get_comparator().compare(model_id)
