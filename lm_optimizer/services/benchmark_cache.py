"""On-disk memo for identical benchmark cases.

A run never repeats a case that was already measured for the same model,
configuration, context and reasoning value. The cache key includes the
benchmark suite version and the model id, so a suite or model change
invalidates stale entries automatically.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from lm_optimizer.benchmark.suite_version import BENCHMARK_SUITE_VERSION
from lm_optimizer.domain.models import BenchmarkMetrics
from lm_optimizer.logging_config import get_logger

logger = get_logger(__name__)

_CACHE_ENV = "LM_OPTIMIZER_BENCHMARK_CACHE"
_DEFAULT_ROOT = Path("data") / "benchmark_cache"


def cache_root() -> Path:
    env = os.environ.get(_CACHE_ENV)
    if env:
        return Path(env).expanduser().resolve()
    return _DEFAULT_ROOT


def _key(model_id: str, case: Any, context_length: int, reasoning: str | None, config: Any) -> str:
    payload = {
        "suite_version": BENCHMARK_SUITE_VERSION,
        "model_id": model_id,
        "case": getattr(case, "name", str(case)),
        "prompt": getattr(case, "prompt", ""),
        "category": getattr(case, "category", ""),
        "max_tokens": getattr(case, "max_tokens", None),
        "temperature": getattr(case, "temperature", None),
        "top_p": getattr(case, "top_p", None),
        "top_k": getattr(case, "top_k", None),
        "context_length": int(context_length),
        "reasoning": reasoning,
        "config": config.to_dict() if hasattr(config, "to_dict") else {},
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_cached(model_id: str, case: Any, context_length: int, reasoning: str | None, config: Any) -> BenchmarkMetrics | None:
    path = cache_root() / f"{_key(model_id, case, context_length, reasoning, config)}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return BenchmarkMetrics(**data)
    except Exception as e:
        logger.debug("Benchmark cache read failed", error=str(e)[:120])
        return None


def store_cached(model_id: str, case: Any, context_length: int, reasoning: str | None, config: Any, metrics: BenchmarkMetrics) -> None:
    try:
        root = cache_root()
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{_key(model_id, case, context_length, reasoning, config)}.json"
        path.write_text(json.dumps(asdict(metrics), ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.debug("Benchmark cache write failed", error=str(e)[:120])
