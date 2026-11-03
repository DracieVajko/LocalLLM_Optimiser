"""Optimization enums shared by every aggregate."""

from enum import Enum

class OptimizationProfile(str, Enum):
    """Optimization profile types."""

    SPEED = "speed"
    BALANCED = "balanced"
    CONTEXT = "context"
    QUALITY = "quality"
    CUSTOM = "custom"


class OptimizationStage(str, Enum):
    """Optimization stages."""

    DISCOVERY = "discovery"
    COARSE_SEARCH = "coarse_search"
    REFINEMENT = "refinement"
    BATCH_OPTIMIZATION = "batch_optimization"
    MICRO_REFINEMENT = "micro_refinement"
    VALIDATION = "validation"
    # Phase A/B strategy stages (legacy values above kept for compat).
    SPEED_DISCOVERY = "speed_discovery"
    CONTEXT_SPEED = "context_speed"
    QUALITY_CHECK = "quality_check"
    RECOVERY = "recovery"
    FINAL_VALIDATION = "final_validation"
    CONTEXT_OPTIONAL = "context_optional"
    COMPLETE = "complete"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    ERROR = "error"


class OptimizationPhase(str, Enum):
    """Phase A/B strategy phases.

    SPEED: fixed small-context speed discovery + frontier.
    CONTEXT_SPEED: doubling context-speed ladder on the fastest config.
    QUALITY: full quality suite on frozen speed finalists.
    RECOVERY: bounded causal rollback after quality failure.
    FINAL_VALIDATION: adaptive validation of the final runtime config.
    CONTEXT_OPTIONAL: optional Phase B max-context on the frozen winner.
    """

    SPEED = "speed"
    CONTEXT_SPEED = "context_speed"
    QUALITY = "quality"
    RECOVERY = "recovery"
    FINAL_VALIDATION = "final_validation"
    CONTEXT_OPTIONAL = "context_optional"


class RunStatus(str, Enum):
    """Optimization run status.

    SUCCESS: a validated winning configuration was found; individual other
    candidate failures never downgrade the run.
    COMPLETED_NO_WINNER: the campaign completed and the model generated usable
    output, but no configuration passed the configured quality threshold. It is
    an honest terminal state (not a failure, not a validated winner).
    PARTIAL_SUCCESS: legacy/transitional — an incomplete campaign that kept
    useful validated results. New completed runs no longer use it for mere
    candidate failures (that is SUCCESS).
    FAILED: genuine run-level failure (model never loaded, no usable output).
    CANCELLED/INTERRUPTED are terminal interruption states.
    RESUMED marks a run that was restored from a checkpoint and is running.
    COMPLETED is kept as a legacy alias of SUCCESS.
    """

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    COMPLETED_NO_WINNER = "completed_no_validated_winner"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    RESUMED = "resumed"


# Terminal success-class states (winner may exist).
SUCCESS_STATES: frozenset = frozenset(
    {
        RunStatus.COMPLETED,
        RunStatus.SUCCESS,
        RunStatus.PARTIAL_SUCCESS,
        RunStatus.COMPLETED_NO_WINNER,
    }
)

# Terminal states that mark a finished campaign (nothing left to run).
TERMINAL_STATES: frozenset = frozenset(
    {
        RunStatus.COMPLETED,
        RunStatus.SUCCESS,
        RunStatus.PARTIAL_SUCCESS,
        RunStatus.COMPLETED_NO_WINNER,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.INTERRUPTED,
    }
)


class ConfigurationStatus(str, Enum):
    """Configuration test status (strict failure state machine).

    Terminal failure classes are never collapsed: LOAD_FAILED (soft unless
    structural), INCOMPATIBLE (hard lock), OOM (soft/learned), TIMEOUT (soft),
    BENCHMARK_FAILED / VERIFY_FAILED / PREHEAT_FAILED (stage of failure),
    QUALITY_FAILED (metrics preserved, excluded from winners).
    Only CANDIDATE_ELIGIBLE-equivalent results (PASSED + score set) may win.
    Legacy FAILED/OOM/TIMEOUT values still round-trip from older databases.
    """

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    LOAD_FAILED = "load_failed"
    VERIFY_FAILED = "verify_failed"
    PREHEAT_FAILED = "preheat_failed"
    BENCHMARK_FAILED = "benchmark_failed"
    QUALITY_FAILED = "quality_failed"
    INCOMPATIBLE = "incompatible"
    OOM = "oom"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


# Soft/learned failures (may succeed later under other conditions).
SOFT_FAILURES: frozenset = frozenset(
    {
        ConfigurationStatus.LOAD_FAILED,
        ConfigurationStatus.OOM,
        ConfigurationStatus.TIMEOUT,
        ConfigurationStatus.BENCHMARK_FAILED,
        ConfigurationStatus.VERIFY_FAILED,
        ConfigurationStatus.PREHEAT_FAILED,
        ConfigurationStatus.FAILED,
    }
)