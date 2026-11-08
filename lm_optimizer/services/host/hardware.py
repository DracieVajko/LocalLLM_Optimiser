"""Hardware detection service.

Detects GPU, CPU, and system information for optimization.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass

from lm_optimizer.logging_config import get_logger
from lm_optimizer.services.best_effort import log_best_effort

logger = get_logger(__name__)

# Try to import WMI for Windows hardware detection
WMI_AVAILABLE = False
try:
    import wmi

    WMI_AVAILABLE = True
except ImportError:
    pass


@dataclass
class GPUInfo:
    index: int
    name: str
    vram_gb: float
    vendor: str = "unknown"
    driver_version: str | None = None
    compute_capability: str | None = None
    shared_memory_gb: float | None = None


@dataclass
class HardwareInfo:
    os: str
    cpu_name: str
    cpu_cores_physical: int
    cpu_cores_logical: int
    total_ram_gb: float
    gpu_count: int
    gpus: list[GPUInfo] = None
    cuda_version: str | None = None
    metal_available: bool = False
    vulkan_available: bool = False
    detected_at: str = ""

    def __post_init__(self):
        if self.gpus is None:
            self.gpus = []
        if not self.detected_at:
            from datetime import datetime

            self.detected_at = datetime.now().isoformat()


class HardwareDetector:
    """Detects hardware information."""

    def __init__(self):
        self._cached_hardware = None

    def detect(self) -> HardwareInfo:
        """Detect hardware information."""
        if self._cached_hardware is not None:
            return self._cached_hardware

        gpus = self._detect_gpus()
        gpu_count = len(gpus)
        total_ram_gb = self._get_total_ram_gb()
        cpu_name = self._get_cpu_name()
        cpu_cores_physical = self._get_cpu_cores_physical()
        cpu_cores_logical = self._get_cpu_cores_logical()
        cuda_version = self._get_cuda_version()
        metal_available = platform.system() == "Darwin"
        vulkan_available = self._check_vulkan()

        from lm_optimizer.config import config

        hardware = HardwareInfo(
            os=platform.system(),
            cpu_name=cpu_name,
            cpu_cores_physical=cpu_cores_physical,
            cpu_cores_logical=cpu_cores_logical,
            total_ram_gb=total_ram_gb,
            gpu_count=gpu_count,
            gpus=gpus,
            cuda_version=cuda_version,
            metal_available=metal_available,
            vulkan_available=vulkan_available,
        )

        # Apply config overrides
        hw_config = config.hardware
        if hw_config.gpu_vram_gb is not None and hardware.gpus:
            hardware.gpus[0].vram_gb = hw_config.gpu_vram_gb
        if hw_config.system_ram_gb is not None:
            hardware.total_ram_gb = hw_config.system_ram_gb
        if hw_config.gpu_name is not None and hardware.gpus:
            hardware.gpus[0].name = hw_config.gpu_name

        self._cached_hardware = hardware
        logger.info("Hardware detected", gpu_count=gpu_count, ram_gb=total_ram_gb)
        return hardware

    def _get_cpu_name(self) -> str:
        """Get CPU name."""
        cpu_name = platform.processor()
        if not cpu_name or cpu_name == "":
            if platform.system() == "Windows" and WMI_AVAILABLE:
                try:
                    c = wmi.WMI()
                    for processor in c.Win32_Processor():
                        cpu_name = processor.Name
                        break
                except Exception as exc:
                    log_best_effort("best-effort operation failed", exc)
        if not cpu_name:
            cpu_name = platform.machine()
        return cpu_name

    def _get_cpu_cores_physical(self) -> int:
        """Get number of physical CPU cores."""
        try:
            import psutil

            return psutil.cpu_count(logical=False) or 1
        except Exception:
            return 1

    def _get_cpu_cores_logical(self) -> int:
        """Get number of logical CPU cores."""
        try:
            import psutil

            return psutil.cpu_count(logical=True) or 1
        except Exception:
            return 1

    def _get_total_ram_gb(self) -> float:
        """Get total system RAM in GB."""
        try:
            import psutil

            return psutil.virtual_memory().total / (1024**3)
        except Exception:
            return 0.0

    def _detect_gpus(self) -> list[GPUInfo]:
        """Detect GPU information."""
        gpus = []

        # Try nvidia-smi for more details
        if platform.system() == "Windows" or platform.system() == "Linux":
            nvidia_smi = shutil.which("nvidia-smi")
            if nvidia_smi:
                try:
                    result = subprocess.run(
                        [
                            nvidia_smi,
                            "--query-gpu=index,name,memory.total,driver_version,compute_cap",
                            "--format=csv,noheader,nounits",
                        ],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=5,
                    )
                    if result.returncode == 0:
                        for line in result.stdout.strip().split("\n"):
                            parts = [p.strip() for p in line.split(",")]
                            if len(parts) >= 5:
                                idx = int(parts[0])
                                # Update existing or add new
                                existing = next((g for g in gpus if g.index == idx), None)
                                if existing:
                                    existing.driver_version = parts[3]
                                    existing.compute_capability = parts[4]
                                else:
                                    gpus.append(
                                        GPUInfo(
                                            index=idx,
                                            name=parts[1],
                                            vram_gb=round(float(parts[2]) / 1024, 2),
                                            vendor="NVIDIA",
                                            driver_version=parts[3],
                                            compute_capability=parts[4],
                                        )
                                    )
                except (subprocess.SubprocessError, FileNotFoundError, ValueError):
                    pass

        # AMD GPU detection on Linux
        if platform.system() == "Linux":
            rocm_smi = shutil.which("rocm-smi")
            if rocm_smi:
                try:
                    result = subprocess.run(
                        [rocm_smi, "--showproductname", "--showmeminfo", "vram", "--json"],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=5,
                    )
                    if result.returncode == 0:
                        import json

                        data = json.loads(result.stdout)
                        for idx, gpu_data in enumerate(data):
                            gpus.append(
                                GPUInfo(
                                    index=idx,
                                    name=gpu_data.get("Card series", "AMD GPU"),
                                    vram_gb=gpu_data.get("VRAM Total Memory (B)", 0) / (1024**3),
                                    vendor="AMD",
                                )
                            )
                except Exception as exc:
                    log_best_effort("best-effort operation failed", exc)
        return gpus

    def _get_cuda_version(self) -> str | None:
        """Get CUDA version."""
        nvcc_path = shutil.which("nvcc")
        if not nvcc_path:
            return None
        try:
            result = subprocess.run(
                [nvcc_path, "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if "release" in line.lower():
                        return line.split("release")[-1].split(",")[0].strip()
        except Exception as exc:
            log_best_effort("best-effort operation failed", exc)
        return None

    def _check_vulkan(self) -> bool:
        """Check Vulkan availability."""
        vulkaninfo_path = shutil.which("vulkaninfo")
        if not vulkaninfo_path:
            return False
        try:
            result = subprocess.run(
                [vulkaninfo_path, "--summary"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def get_available_vram(self) -> float:
        """Get available VRAM."""
        # Try nvidia-smi
        nvidia_smi = shutil.which("nvidia-smi")
        if nvidia_smi:
            try:
                result = subprocess.run(
                    [nvidia_smi, "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=5,
                )
                if result.returncode == 0:
                    try:
                        return float(result.stdout.strip().split("\n")[0])
                    except (ValueError, IndexError):
                        pass
            except Exception as exc:
                log_best_effort("best-effort operation failed", exc)
        return 0.0


# Module-level singleton used by routes and other services.
hardware_detector = HardwareDetector()