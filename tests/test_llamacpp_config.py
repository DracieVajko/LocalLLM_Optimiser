"""Tests for llama.cpp config translation."""

from __future__ import annotations

from lm_optimizer.domain.models import LoadConfiguration
from lm_optimizer.backends.llamacpp.config import (
    from_load_config,
    moe_n_cpu_moe_recommendation,
    kv_quant_to_cache_type,
    LlamaCppArgs,
)


def test_basic_translation():
    cfg = LoadConfiguration(context_length=4096, flash_attention=True)
    args = from_load_config(cfg, model_path="/m.gguf", vram_gb=8.0, model_size_gb=4.0)
    cli = args.to_cli_args()
    assert "--ctx-size" in cli
    assert "4096" in cli
    assert "--flash-attn" in cli
    assert "--n-gpu-layers" in cli


def test_moe_n_cpu_moe():
    cfg = LoadConfiguration(context_length=8192)
    args = from_load_config(cfg, model_path="/m.gguf", vram_gb=6.0, model_size_gb=12.0, is_moe=True, num_experts=8)
    assert args.n_cpu_moe > 0


def test_no_moe_no_cpu_offload():
    cfg = LoadConfiguration(context_length=4096)
    args = from_load_config(cfg, model_path="/m.gguf", vram_gb=8.0, model_size_gb=4.0, is_moe=False)
    assert args.n_cpu_moe == 0


def test_kv_quant_mapping():
    assert kv_quant_to_cache_type("q8_0") == "q8_0"
    assert kv_quant_to_cache_type("f16") == "f16"
    assert kv_quant_to_cache_type("q4_0") == "q4_0"


def test_rope_scaling():
    cfg = LoadConfiguration(context_length=8192)
    args = from_load_config(cfg, model_path="/m.gguf", vram_gb=8.0, model_size_gb=4.0, native_context=4096)
    assert args.rope_freq_base_checked is True
    assert args.rope_freq_base > 0


def test_moe_recommendation():
    # Model fits in VRAM
    assert moe_n_cpu_moe_recommendation(12.0, 8.0) == 0
    # Model doesn't fit
    result = moe_n_cpu_moe_recommendation(6.0, 12.0)
    assert result > 0


def test_cli_string():
    args = LlamaCppArgs(model_path="/m.gguf", ctx_size=4096)
    s = args.to_cli_string()
    assert "--model /m.gguf" in s
    assert "--ctx-size 4096" in s