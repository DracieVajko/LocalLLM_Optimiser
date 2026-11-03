"""Hardware snapshot models."""

from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class HardwareInfo:
    """Hardware information snapshot."""

    os: str
    cpu_name: str
    cpu_cores_physical: int
    cpu_cores_logical: int
    total_ram_gb: float
    gpu_count: int
    gpus: list["GPUInfo"] = field(default_factory=list)
    cuda_version: str | None = None
    metal_available: bool = False
    vulkan_available: bool = False
    detected_at: datetime = field(default_factory=datetime.now)


@dataclass
class GPUInfo:
    """GPU information."""

    index: int
    name: str
    vram_gb: float
    vendor: str
    driver_version: str | None = None
    compute_capability: str | None = None
    shared_memory_gb: float | None = None
