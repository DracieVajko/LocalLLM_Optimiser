"""Process-wide run registry for the API.

Kept in one small object instead of scattered module globals so the lifespan
hook can clear it and tests can reset it without importing route internals.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from lm_optimizer.services.orchestration.optimizer import AdaptiveOptimizer


@dataclass
class RunRegistry:
    optimizer: AdaptiveOptimizer | None = None
    run_id: UUID | None = None

    def set(self, optimizer: AdaptiveOptimizer, run_id: UUID) -> None:
        self.optimizer = optimizer
        self.run_id = run_id

    def clear(self) -> None:
        self.optimizer = None
        self.run_id = None

    def matches(self, run_id: UUID | str) -> bool:
        return self.run_id is not None and str(self.run_id) == str(run_id)


registry = RunRegistry()

__all__ = ["RunRegistry", "registry"]
