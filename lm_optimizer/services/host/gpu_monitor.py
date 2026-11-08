"""GPU/CPU usage monitor for scheduling decisions (no LLM load).

Ignores integrated GPU (iGPU) — only considers discrete RTX/NVIDIA GPU
load. CPU load is still checked but can be overridden by user.
"""

from __future__ import annotations

import shutil
import subprocess

import psutil


def _discrete_gpu_load() -> float:
    """Return load of the discrete (RTX) GPU, or 0.0 if unavailable."""
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return 0.0
    try:
        result = subprocess.run(
            [nvidia_smi, "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            loads = [float(x.strip()) for x in result.stdout.strip().split("\n") if x.strip()]
            # Return max load across discrete GPUs (ignore iGPU if multiple)
            return max(loads) if loads else 0.0
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        return 0.0
    return 0.0


def is_gpu_busy(threshold_percent: float = 10.0) -> bool:
    """Check if discrete GPU has load above threshold (iGPU ignored)."""
    load = _discrete_gpu_load()
    return load > threshold_percent / 100.0


def is_cpu_busy(threshold_percent: float = 80.0) -> bool:
    """Check if overall CPU load exceeds threshold."""
    try:
        load = psutil.cpu_percent(interval=0.1)
        return load > threshold_percent
    except Exception:
        return False


def should_run_tests() -> dict:
    """Return scheduling recommendation based on current load (discrete GPU only)."""
    gpu_busy = is_gpu_busy()
    cpu_busy = is_cpu_busy()
    return {
        "gpu_busy": gpu_busy,
        "cpu_busy": cpu_busy,
        "can_run_full": not (gpu_busy or cpu_busy),
        "suggest_short_tests": gpu_busy or cpu_busy,
        "suggest_wait_minutes": 15 if (gpu_busy or cpu_busy) else 0,
        "suggest_check_again_in_hours": 4,
        "discrete_gpu_load": _discrete_gpu_load(),
    }
