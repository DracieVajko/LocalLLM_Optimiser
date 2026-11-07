"""Tests for llama.cpp n-cpu-moe support."""

from __future__ import annotations

from lm_optimizer.domain.configuration import LoadConfiguration, LMStudioCapabilities
from lm_optimizer.domain.model import ModelIdentity
from lm_optimizer.domain.hardware import HardwareInfo, GPUInfo
from lm_optimizer.backends.llamacpp.config import moe_n_cpu_moe_recommendation


def test_moe_recommendation_fits_in_vram():
    """Model fits in VRAM -> no CPU offload needed."""
    assert moe_n_cpu_moe_recommendation(12.0, 8.0) == 0


def test_moe_recommendation_overflows_vram():
    """Model larger than VRAM -> offload experts to CPU."""
    result = moe_n_cpu_moe_recommendation(6.0, 12.0)
    assert result > 0


def test_moe_recommendation_extreme_overflow():
    """Massive overflow -> high CPU offload."""
    result = moe_n_cpu_moe_recommendation(4.0, 24.0)
    assert result > 8


def test_load_config_has_n_cpu_moe_field():
    """LoadConfiguration has n_cpu_moe field."""
    cfg = LoadConfiguration(n_cpu_moe=16)
    assert cfg.n_cpu_moe == 16


def test_capabilities_has_supports_n_cpu_moe():
    """LMStudioCapabilities has supports_n_cpu_moe field."""
    caps = LMStudioCapabilities(supports_n_cpu_moe=True)
    assert caps.supports_n_cpu_moe is True


def test_capabilities_default_n_cpu_moe_false():
    """Default supports_n_cpu_moe is False."""
    caps = LMStudioCapabilities()
    assert caps.supports_n_cpu_moe is False


def test_moe_model_has_is_moe_and_num_experts():
    """ModelIdentity has MoE fields."""
    model = ModelIdentity(
        id="test/moe-model",
        name="moe-model",
        is_moe=True,
        num_experts=8,
        size_bytes=12 * 1024**3,
    )
    assert model.is_moe is True
    assert model.num_experts == 8


def test_hardware_has_gpu_vram():
    """HardwareInfo exposes GPU VRAM."""
    hw = HardwareInfo(
        os="Windows",
        cpu_name="Intel i7",
        cpu_cores_physical=8,
        cpu_cores_logical=16,
        total_ram_gb=32.0,
        gpu_count=1,
        gpus=[GPUInfo(index=0, name="RTX 3060", vram_gb=6.0, vendor="NVIDIA")],
    )
    assert hw.gpus[0].vram_gb == 6.0