"""Run, configuration-result and profile-weight models."""

import statistics
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from .benchmark import BenchmarkMetrics
from .configuration import LoadConfiguration
from .enums import ConfigurationStatus, OptimizationProfile, OptimizationStage, RunStatus
from .hardware import HardwareInfo
from .model import ModelIdentity
from .quality import QualityScore
from lm_optimizer import __version__

@dataclass
class ConfigurationResult:
    """Result of testing a single configuration."""

    id: UUID = field(default_factory=uuid4)
    run_id: UUID | None = None
    config: LoadConfiguration = field(default_factory=LoadConfiguration)
    context_length: int = 4096
    status: ConfigurationStatus = ConfigurationStatus.PENDING
    metrics: list[BenchmarkMetrics] = field(default_factory=list)
    quality_score: QualityScore | None = None
    stability_score: float = 1.0
    peak_vram_gb: float | None = None
    peak_ram_gb: float | None = None
    error: str | None = None
    # Score eligibility (§25): None until load+verify+benchmark+quality all
    # succeed. Failed configs keep score None and can never win.
    score: float | None = None
    score_breakdown: dict | None = None
    tested_at: datetime | None = None
    duration_ms: float = 0.0
    generation: dict | None = None
    validation_repetitions_effective: int = 1  # generation settings (style, temperature overrides)

    def get_avg_generation_tok_s(self) -> float:
        """Median generation speed across successful tests (outlier-robust, R35)."""
        speeds = [m.generation_tok_s for m in self.metrics if m.success and m.generation_tok_s > 0]
        if not speeds:
            return 0.0
        return statistics.median(speeds)

    def get_avg_prompt_tok_s(self) -> float:
        """Median prompt speed across successful tests (R35)."""
        speeds = [m.prompt_tok_s for m in self.metrics if m.success and m.prompt_tok_s > 0]
        if not speeds:
            return 0.0
        return statistics.median(speeds)

    def get_avg_ttft_ms(self) -> float:
        """Backward compat: returns estimated TTFT."""
        return self.get_avg_estimated_ttft_ms()

    def get_avg_estimated_ttft_ms(self) -> float:
        """Median estimated TTFT across successful tests (R35)."""
        ttfts = [m.estimated_ttft_ms for m in self.metrics if m.success and m.estimated_ttft_ms > 0]
        if not ttfts:
            return 0.0
        return statistics.median(ttfts)


@dataclass
class OptimizationRun:
    """Complete optimization run."""

    id: UUID = field(default_factory=uuid4)
    model: ModelIdentity = field(default_factory=lambda: ModelIdentity(id="", name=""))
    hardware: HardwareInfo = field(
        default_factory=lambda: HardwareInfo(
            os="",
            cpu_name="",
            cpu_cores_physical=0,
            cpu_cores_logical=0,
            total_ram_gb=0,
            gpu_count=0,
        )
    )
    hardware_id: str | None = None
    backend_id: str | None = None  # "lmstudio", "ollama", "llamacpp"
    profile: OptimizationProfile = OptimizationProfile.BALANCED
    profile_weights: dict[str, float] = field(default_factory=dict)
    quality_threshold: float = 0.97
    status: RunStatus = RunStatus.PENDING
    stage: OptimizationStage = OptimizationStage.DISCOVERY
    configurations: list[ConfigurationResult] = field(default_factory=list)
    best_config_id: UUID | None = None
    pareto_config_ids: list[UUID] = field(default_factory=list)
    baseline_config_id: UUID | None = None
    baseline_metrics: dict | None = None
    is_experimental: bool = False
    experimental_reason: str | None = None
    search_space: dict = field(default_factory=dict)
    benchmark_params: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float = 0.0
    error: str | None = None
    optimizer_version: str = __version__
    benchmark_repetitions: int = 3
    validation_repetitions: int = 5
    # Phase A/B strategy fields (all defaulted; legacy runs ignore them).
    phase: str = "speed"
    speed_context: int | None = None
    quality_context: int | None = None
    raw_fastest_config_id: UUID | None = None
    phase_b_enabled: bool = False
    phase_b_result: dict | None = None
    advanced_settings: dict = field(default_factory=dict)

    # --- Speed floor (spec §3) ---
    min_generation_tok_s: float = 2.0
    enforce_min_generation_speed: bool = True

    # --- Preset and stage selection (spec §2, §7) ---
    run_preset: str = "standard"  # quick, standard, thorough, custom
    selected_stages: list[str] = field(default_factory=list)
    max_speed_probes: int | None = None
    max_finalists: int | None = None
    benchmark_repetitions_override: int | None = None
    validation_repetitions_min: int = 2
    validation_repetitions_max: int = 5
    recovery_budget: int = 3

    # --- Context strategies (spec §5) ---
    context_strategy_modes: list[str] = field(default_factory=list)

    # --- Final sandbox (spec §6) ---
    final_sandbox_mode: str = "off"  # off, one, all, custom
    final_sandbox_preset_ids: list[str] = field(default_factory=list)
    final_sandbox_custom_prompts: list[dict] = field(default_factory=list)
    sandbox_compare_baseline: bool = False

    # --- Scheduled artifact test (fourth option, runs last on the winner) ---
    artifact_test_id: str | None = None  # builtin task id or "custom:<path>"

    # --- Resolved preset budgets (frozen at run start, for reporting) ---
    resolved_preset: dict | None = None

    # Explicit reason when a terminal run produced no eligible winner
    # (e.g. NO_CONFIG_MEETS_SPEED_FLOOR). None means "a winner exists or
    # the run failed for another reason recorded in `error`".
    no_winner_reason: str | None = None

    def get_best_config(self) -> ConfigurationResult | None:
        if self.best_config_id:
            for c in self.configurations:
                if c.id == self.best_config_id:
                    return c
        return None

    def get_pareto_configs(self) -> list[ConfigurationResult]:
        return [c for c in self.configurations if c.id in self.pareto_config_ids]

    def get_baseline_config(self) -> ConfigurationResult | None:
        if self.baseline_config_id:
            for c in self.configurations:
                if c.id == self.baseline_config_id:
                    return c
        return None


@dataclass
class ProfileWeights:
    """Optimization profile weights."""

    generation_speed: float = 0.0
    prompt_speed: float = 0.0
    ttft: float = 0.0
    quality: float = 0.0
    stability: float = 0.0
    context: float = 0.0
    memory_efficiency: float = 0.0

    def validate(self) -> bool:
        total = (
            self.generation_speed
            + self.prompt_speed
            + self.ttft
            + self.quality
            + self.stability
            + self.context
            + self.memory_efficiency
        )
        return abs(total - 1.0) < 0.01

    def to_dict(self) -> dict:
        return {
            "generation_speed": self.generation_speed,
            "prompt_speed": self.prompt_speed,
            "ttft": self.ttft,
            "quality": self.quality,
            "stability": self.stability,
            "context": self.context,
            "memory_efficiency": self.memory_efficiency,
        }


DEFAULT_PROFILE_WEIGHTS = {
    OptimizationProfile.SPEED: ProfileWeights(
        generation_speed=0.40,
        prompt_speed=0.25,
        ttft=0.15,
        quality=0.10,
        stability=0.05,
        context=0.03,
        memory_efficiency=0.02,
    ),
    OptimizationProfile.BALANCED: ProfileWeights(
        generation_speed=0.27,
        prompt_speed=0.15,
        ttft=0.12,
        quality=0.12,
        stability=0.12,
        context=0.11,
        memory_efficiency=0.11,
    ),
    OptimizationProfile.CONTEXT: ProfileWeights(
        generation_speed=0.10,
        prompt_speed=0.10,
        ttft=0.10,
        quality=0.15,
        stability=0.15,
        context=0.25,
        memory_efficiency=0.15,
    ),
    OptimizationProfile.QUALITY: ProfileWeights(
        generation_speed=0.08,
        prompt_speed=0.08,
        ttft=0.08,
        quality=0.35,
        stability=0.13,
        context=0.21,
        memory_efficiency=0.07,
    ),
}
