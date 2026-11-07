"""Hardware detection - authoritative implementation for GPU, CPU, memory."""

import platform
import shutil
import subprocess
from dataclasses import dataclass

import psutil

from ..config import config
from ..logging_config import get_logger

logger = get_logger(__name__)


# Legacy local dataclasses kept for backward compat (deprecated)
@dataclass
class GPUInfo:
    """GPU information (legacy, use domain.GPUInfo)."""

    name: str
    vram_gb: float
    driver_version: str | None = None
    cuda_version: str | None = None
    compute_capability: str | None = None
    gpu_index: int = 0


@dataclass
class CPUInfo:
    """CPU information (legacy)."""

    name: str
    cores_physical: int
    cores_logical: int
    frequency_ghz: float | None = None


@dataclass
class MemoryInfo:
    """System memory information (legacy)."""

    total_gb: float
    available_gb: float
    used_gb: float


@dataclass
class HardwareInfo:
    """Complete hardware information (legacy, use domain.HardwareInfo)."""

    gpu: GPUInfo | None
    cpu: CPUInfo
    memory: MemoryInfo
    os: str
    platform: str
    python_version: str


def get_gpu_info() -> GPUInfo | None:
    """Detect the first NVIDIA GPU using nvidia-smi."""
    try:
        result = subprocess.run(
            [
                shutil.which("nvidia-smi"),
                "--query-gpu=index,name,memory.total,driver_version,compute_cap",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        if result.returncode != 0 or not result.stdout.strip():
            logger.debug("nvidia-smi returned no GPU rows")
            return None
        parts = [p.strip() for p in result.stdout.strip().splitlines()[0].split(",")]
        if len(parts) < 5:
            logger.debug("Unexpected nvidia-smi row", row=result.stdout[:120])
            return None
        return GPUInfo(
            name=parts[1],
            vram_gb=round(float(parts[2]) / 1024, 2),
            driver_version=parts[3] or None,
            cuda_version=None,
            compute_capability=parts[4] or None,
            gpu_index=int(parts[0]),
        )
    except (FileNotFoundError, subprocess.SubprocessError, ValueError) as e:
        logger.debug("GPU detection failed", error=str(e))
        return None


def get_cpu_info() -> CPUInfo:
    """Detect CPU information."""
    cpu_name = platform.processor()
    if not cpu_name or cpu_name == "":
        cpu_name = "Unknown CPU"

    return CPUInfo(
        name=cpu_name,
        cores_physical=psutil.cpu_count(logical=False) or 1,
        cores_logical=psutil.cpu_count(logical=True) or 1,
        frequency_ghz=_cpu_freq_ghz(),
    )


def _cpu_freq_ghz() -> float | None:
    """CPU frequency in GHz, or None where the platform cannot report it.

    psutil.cpu_freq may be missing entirely (some macOS runners) or return
    None: frequency is informational, detection must never fail because of it.
    """
    try:
        freq = psutil.cpu_freq()
    except (AttributeError, TypeError, OSError):
        return None
    try:
        if freq is None or freq.max is None:
            return None
        return round(freq.max / 1000, 2)
    except (TypeError, AttributeError):
        return None


def get_memory_info() -> MemoryInfo:
    """Detect system memory information."""
    mem = psutil.virtual_memory()
    return MemoryInfo(
        total_gb=round(mem.total / (1024**3), 2),
        available_gb=round(mem.available / (1024**3), 2),
        used_gb=round(mem.used / (1024**3), 2),
    )


def detect_hardware() -> HardwareInfo:
    """Detect all hardware information."""
    gpu = get_gpu_info()
    cpu = get_cpu_info()
    memory = get_memory_info()

    # Override with config values if provided
    hw_config = config.hardware
    if hw_config.gpu_vram_gb is not None and gpu:
        gpu.vram_gb = hw_config.gpu_vram_gb
    if hw_config.system_ram_gb is not None:
        memory.total_gb = hw_config.system_ram_gb
    if hw_config.gpu_name is not None and gpu:
        gpu.name = hw_config.gpu_name

    return HardwareInfo(
        gpu=gpu,
        cpu=cpu,
        memory=memory,
        os=platform.system(),
        platform=platform.platform(),
        python_version=platform.python_version(),
    )


def format_hardware_info(info: HardwareInfo) -> str:
    """Format hardware info for display."""
    lines = [
        "=== Hardware Information ===",
        f"OS: {info.os} ({info.platform})",
        f"Python: {info.python_version}",
        "",
        "CPU:",
        f"  Name: {info.cpu.name}",
        f"  Cores: {info.cpu.cores_physical} physical / {info.cpu.cores_logical} logical",
    ]
    if info.cpu.frequency_ghz:
        lines.append(f"  Max Frequency: {info.cpu.frequency_ghz:.2f} GHz")

    lines.append("")
    lines.append("Memory:")
    lines.append(f"  Total: {info.memory.total_gb:.1f} GB")
    lines.append(f"  Available: {info.memory.available_gb:.1f} GB")
    lines.append(f"  Used: {info.memory.used_gb:.1f} GB")

    if info.gpu:
        lines.append("")
        lines.append("GPU:")
        lines.append(f"  Name: {info.gpu.name}")
        lines.append(f"  VRAM: {info.gpu.vram_gb:.1f} GB")
        if info.gpu.driver_version:
            lines.append(f"  Driver: {info.gpu.driver_version}")
        if info.gpu.cuda_version:
            lines.append(f"  CUDA: {info.gpu.cuda_version}")
        if info.gpu.compute_capability:
            lines.append(f"  Compute Capability: {info.gpu.compute_capability}")
    else:
        lines.append("")
        lines.append("GPU: Not detected")

    return "\n".join(lines)
