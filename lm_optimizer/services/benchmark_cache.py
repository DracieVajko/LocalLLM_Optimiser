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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lm_optimizer.benchmark.suite_version import BENCHMARK_SUITE_VERSION
from lm_optimizer.domain.models import BenchmarkMetrics
from lm_optimizer.logging_config import get_logger
from lm_optimizer.services.best_effort import log_best_effort

logger = get_logger(__name__)

_CACHE_ENV = "LM_OPTIMIZER_BENCHMARK_CACHE"
_DEFAULT_ROOT = Path("data") / "benchmark_cache"
_CACHE_RW_ENV = "LM_OPTIMIZER_BENCHMARK_CACHE_RW"
_CACHE_TTL_DAYS = 14


def cache_root() -> Path:
    env = os.environ.get(_CACHE_ENV)
    if env:
        return Path(env).expanduser().resolve()
    return _DEFAULT_ROOT


def cache_reads_enabled() -> bool:
    """Whether cache reads are enabled.

    Default is ``off`` (never read, still write) to prevent stale replay.
    Set LM_OPTIMIZER_BENCHMARK_CACHE_RW=on to enable reads.
    """
    return os.environ.get(_CACHE_RW_ENV, "off").lower() in ("on", "true", "1", "yes")


def _host_fingerprint() -> str:
    """Best-effort host fingerprint for cache keying.

    Includes GPU name, VRAM, and OS info. Does not require a server probe.
    """
    parts = []
    try:
        import platform
        parts.append(platform.system())
        parts.append(platform.machine())
        parts.append(platform.python_version())
    except Exception as exc:
        log_best_effort("host fingerprint detection failed", exc)
    try:
        from lm_optimizer.services.host.hardware import hardware_detector
        hw = hardware_detector.detect()
        for g in getattr(hw, "gpus", []) or []:
            parts.append(getattr(g, "name", ""))
            parts.append(str(getattr(g, "vram_gb", 0)))
    except Exception as exc:
        log_best_effort("hardware detection failed", exc)
    return "|".join(str(p) for p in parts)


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
        "host_fingerprint": _host_fingerprint(),
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_cached(model_id: str, case: Any, context_length: int, reasoning: str | None, config: Any) -> BenchmarkMetrics | None:
    if not cache_reads_enabled():
        return None
    path = cache_root() / f"{_key(model_id, case, context_length, reasoning, config)}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        # Check TTL
        created_at = data.get("_created_at")
        if created_at:
            from datetime import datetime, timezone
            try:
                created = datetime.fromisoformat(created_at)
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                age_days = (datetime.now(timezone.utc) - created).days
                if age_days > _CACHE_TTL_DAYS:
                    logger.debug("Benchmark cache expired", age_days=age_days, path=str(path))
                    return None
            except (ValueError, TypeError):
                pass
        return BenchmarkMetrics(**{k: v for k, v in data.items() if k != "_created_at"})
    except Exception as e:
        logger.debug("Benchmark cache read failed", error=str(e)[:120])
        return None


def store_cached(model_id: str, case: Any, context_length: int, reasoning: str | None, config: Any, metrics: BenchmarkMetrics) -> None:
    try:
        root = cache_root()
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{_key(model_id, case, context_length, reasoning, config)}.json"
        data = asdict(metrics)
        data["_created_at"] = datetime.now(timezone.utc).isoformat()
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.debug("Benchmark cache write failed", error=str(e)[:120])
