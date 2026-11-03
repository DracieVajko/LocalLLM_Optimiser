"""Domain models.

The aggregates live in sibling modules; this module re-exports them so the
historical ``from lm_optimizer.domain.models import ...`` import path keeps
working while new code can depend on the narrower module.
"""

from .benchmark import BenchmarkCase, BenchmarkMetrics
from .configuration import LMStudioCapabilities, LoadConfiguration
from .enums import (
    SOFT_FAILURES,
    ConfigurationStatus,
    OptimizationPhase,
    OptimizationProfile,
    OptimizationStage,
    RunStatus,
)
from .hardware import GPUInfo, HardwareInfo
from .model import ModelIdentity
from .quality import QualityScore
from .run import (
    DEFAULT_PROFILE_WEIGHTS,
    ConfigurationResult,
    OptimizationRun,
    ProfileWeights,
)

__all__ = [
    "DEFAULT_PROFILE_WEIGHTS",
    "SOFT_FAILURES",
    "BenchmarkCase",
    "BenchmarkMetrics",
    "ConfigurationResult",
    "ConfigurationStatus",
    "GPUInfo",
    "HardwareInfo",
    "LMStudioCapabilities",
    "LoadConfiguration",
    "ModelIdentity",
    "OptimizationPhase",
    "OptimizationProfile",
    "OptimizationRun",
    "OptimizationStage",
    "ProfileWeights",
    "QualityScore",
    "RunStatus",
]
