"""Best-effort operation logging for tolerated failures.

Replaces the copy-pasted ``except Exception: pass`` blocks in orchestration
paths. The exception is still swallowed (the operation is genuinely optional),
but it is now visible at debug level with its type, message and traceback.
"""

from __future__ import annotations

from lm_optimizer.logging_config import get_logger

logger = get_logger(__name__)


def log_best_effort(operation: str, exc: BaseException) -> None:
    """Log a tolerated failure without changing control flow."""
    detail = f"{type(exc).__name__}: {exc}"[:240]
    logger.debug(
        "Best-effort operation failed",
        operation=operation,
        error=detail,
        exc_info=True,
    )


__all__ = ["log_best_effort"]
