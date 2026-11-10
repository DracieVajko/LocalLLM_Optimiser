"""Split domain/models.py into aggregate modules with a re-export facade."""

import pathlib

ROOT = pathlib.Path("lm_optimizer/domain")
lines = (ROOT / "models.py").read_text(encoding="utf-8").splitlines()


def block(start: int, end: int) -> str:
    return "\n".join(lines[start - 1 : end]).strip() + "\n"


files = {
    "enums.py": (
        '"""Optimization enums shared by every aggregate."""\n\n'
        "from enum import Enum\n\n"
        + block(11, 153)
    ),
    "hardware.py": (
        '"""Hardware snapshot models."""\n\n'
        "from dataclasses import dataclass, field\n"
        "from datetime import datetime\n\n"
        + block(155, 184)
    ),
    "model.py": (
        '"""Model identity model."""\n\n'
        "from dataclasses import dataclass, field\n"
        "from datetime import datetime\n\n"
        + block(186, 216)
    ),
    "benchmark.py": (
        '"""Benchmark case and metrics models."""\n\n'
        "from dataclasses import dataclass, field\n\n"
        + block(218, 230)
        + "\n"
        + block(360, 415)
    ),
    "configuration.py": (
        '"""Load configuration and host capability models."""\n\n'
        "from dataclasses import dataclass, field\n"
        "from typing import ClassVar\n\n"
        + block(232, 358)
    ),
    "quality.py": (
        '"""Deterministic quality-score model."""\n\n'
        "from dataclasses import dataclass, field\n\n"
        + block(417, 458)
    ),
    "run.py": (
        '"""Run, configuration-result and profile-weight models."""\n\n'
        "import statistics\n"
        "from dataclasses import dataclass, field\n"
        "from datetime import datetime\n"
        "from uuid import UUID, uuid4\n\n"
        "from .benchmark import BenchmarkMetrics\n"
        "from .configuration import LoadConfiguration\n"
        "from .enums import ConfigurationStatus, OptimizationProfile, OptimizationStage, RunStatus\n"
        "from .hardware import HardwareInfo\n"
        "from .model import ModelIdentity\n"
        "from .quality import QualityScore\n\n"
        + block(460, len(lines))
    ),
}

for name, content in files.items():
    (ROOT / name).write_text(content, encoding="utf-8")
    print(f"wrote {name}")

facade = '''"""Domain models.

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
'''
(ROOT / "models.py").write_text(facade, encoding="utf-8")
print("wrote facade models.py")
