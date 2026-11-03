"""Typed boundary object for advanced optimization settings.

The optimizer historically accepted a raw ``dict`` and re-applied defaults in
every layer. ``AdvancedSettings`` keeps the mapping behaviour (so persistence
and JSON serialization are unchanged) but centralizes the keys, defaults and
typed accessors at the CLI/API boundary.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DEFAULTS: dict[str, Any] = {
    "run_preset": "standard",
    "style": "balanced",
    "workload_type": "interactive",
    "max_tokens_scale": 1.0,
    "min_speed": 0.0,
    "warmup_runs": 1,
    "min_generation_tok_s": 2.0,
    "enforce_min_generation_speed": True,
    "optimize_context": False,
    "min_context_speed": 1.0,
    "skip_phases": [],
    "selection_threshold": 0.05,
}


class AdvancedSettings(dict[str, Any]):
    """Mapping with typed accessors for the optimizer's advanced settings.

    Subclasses ``dict`` so callers that persist ``run.advanced_settings`` or
    serialize the run keep working. Construct it once at the CLI/API boundary;
    inner layers can then use the typed properties instead of repeating
    ``.get(key, default)``.
    """

    DEFAULTS = DEFAULTS

    def __init__(
        self,
        values: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        if values is not None:
            if not isinstance(values, Mapping):
                raise TypeError(
                    f"AdvancedSettings expects a mapping, got {type(values).__name__}"
                )
            self.update(values)
        if kwargs:
            self.update(kwargs)

    @classmethod
    def coerce(
        cls, value: Mapping[str, Any] | "AdvancedSettings" | None
    ) -> "AdvancedSettings":
        """Return a typed view without copying an existing instance."""
        if isinstance(value, cls):
            return value
        return cls(value)

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict for JSON/persistence boundaries."""
        return dict(self)

    # -- scalar accessors -------------------------------------------------
    @property
    def style(self) -> str:
        return str(self.get("style", "balanced") or "balanced").strip().lower()

    @property
    def workload_type(self) -> str:
        return str(self.get("workload_type", "interactive") or "interactive").strip().lower()

    @property
    def run_preset(self) -> str:
        return str(self.get("run_preset", "standard") or "standard").strip().lower()

    @property
    def max_tokens_scale(self) -> float:
        try:
            return min(1.0, max(0.25, float(self.get("max_tokens_scale", 1.0))))
        except (TypeError, ValueError):
            return 1.0

    @property
    def min_speed(self) -> float:
        try:
            return max(0.0, float(self.get("min_speed", 0.0)))
        except (TypeError, ValueError):
            return 0.0

    @property
    def warmup_runs(self) -> int:
        try:
            return min(5, max(0, int(self.get("warmup_runs", 1))))
        except (TypeError, ValueError):
            return 1

    @property
    def min_generation_tok_s(self) -> float:
        try:
            return max(0.0, float(self.get("min_generation_tok_s", 2.0)))
        except (TypeError, ValueError):
            return 2.0

    @property
    def min_context_speed(self) -> float:
        try:
            return max(0.0, float(self.get("min_context_speed", 1.0)))
        except (TypeError, ValueError):
            return 1.0

    @property
    def selection_threshold(self) -> float:
        try:
            return min(1.0, max(0.0, float(self.get("selection_threshold", 0.05))))
        except (TypeError, ValueError):
            return 0.05

    @property
    def enforce_min_generation_speed(self) -> bool:
        return bool(self.get("enforce_min_generation_speed", True))

    @property
    def optimize_context(self) -> bool:
        return bool(self.get("optimize_context", False))

    @property
    def speed_only(self) -> bool:
        return bool(self.get("speed_only", False))

    @property
    def quality_only(self) -> bool:
        return bool(self.get("quality_only", False))

    @property
    def mtp_test(self) -> bool:
        return bool(self.get("mtp_test", False))

    @property
    def reasoning_sweep(self) -> bool:
        return bool(self.get("reasoning_sweep", False))

    @property
    def quality_lab(self) -> bool:
        return bool(self.get("quality_lab", False))

    @property
    def gpu_via_cli(self) -> bool:
        return bool(self.get("gpu_via_cli", False))

    @property
    def test_only(self) -> bool:
        return bool(self.get("test_only", False))

    # -- optional scalars -------------------------------------------------
    @property
    def artifact_test_id(self) -> str | None:
        value = self.get("artifact_test_id")
        return str(value) if value else None

    @property
    def speed_context(self) -> int | None:
        value = self.get("speed_context")
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @property
    def speed_probe_repetitions(self) -> int | None:
        value = self.get("speed_probe_repetitions")
        if value is None:
            return None
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return None

    # -- list accessors ---------------------------------------------------
    @property
    def skip_phases(self) -> list[str]:
        return self._as_str_list("skip_phases")

    @property
    def context_strategy_modes(self) -> list[str]:
        return self._as_str_list("context_strategy_modes")

    @property
    def include_categories(self) -> set[str] | None:
        values = self._as_str_list("include_categories")
        return set(values) if values else None

    @property
    def test_names(self) -> list[str] | None:
        values = self._as_str_list("test_names")
        return values or None

    @property
    def physical_batches(self) -> list[int]:
        values = self.get("physical_batches")
        if not isinstance(values, (list, tuple)):
            return []
        result: list[int] = []
        for value in values:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                result.append(parsed)
        return result

    def _as_str_list(self, key: str) -> list[str]:
        values = self.get(key)
        if isinstance(values, str):
            values = values.split(",")
        if not isinstance(values, (list, tuple, set)):
            return []
        return [str(value).strip() for value in values if str(value).strip()]


__all__ = ["AdvancedSettings", "DEFAULTS"]
