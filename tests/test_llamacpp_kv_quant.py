"""Tests for llama.cpp KV cache quantization support."""

from __future__ import annotations

from lm_optimizer.domain.configuration import LoadConfiguration, LMStudioCapabilities
from lm_optimizer.backends.llamacpp.config import from_load_config, kv_quant_to_cache_type


def test_kv_quant_f16_default():
    cfg = LoadConfiguration(context_length=4096)
    args = from_load_config(cfg, model_path="/m.gguf", vram_gb=8.0, model_size_gb=4.0)
    assert args.cache_type_k == "f16"
    assert args.cache_type_v == "f16"


def test_kv_quant_q8():
    cfg = LoadConfiguration(context_length=4096, kv_cache_quant="q8_0")
    args = from_load_config(cfg, model_path="/m.gguf", vram_gb=8.0, model_size_gb=4.0)
    assert args.cache_type_k == "q8_0"
    assert args.cache_type_v == "q8_0"


def test_kv_quant_q4():
    cfg = LoadConfiguration(context_length=4096, kv_cache_quant="q4_0")
    args = from_load_config(cfg, model_path="/m.gguf", vram_gb=8.0, model_size_gb=4.0)
    assert args.cache_type_k == "q4_0"
    assert args.cache_type_v == "q4_0"


def test_kv_quant_in_cli():
    cfg = LoadConfiguration(context_length=4096, kv_cache_quant="q8_0")
    args = from_load_config(cfg, model_path="/m.gguf", vram_gb=8.0, model_size_gb=4.0)
    cli = args.to_cli_string()
    assert "--cache-type-k q8_0" in cli
    assert "--cache-type-v q8_0" in cli


def test_capabilities_has_supports_kv_cache_quantization():
    caps = LMStudioCapabilities(supports_kv_cache_quantization=True)
    assert caps.supports_kv_cache_quantization is True


def test_load_config_has_kv_cache_quant_field():
    cfg = LoadConfiguration(kv_cache_quant="q8_0")
    assert cfg.kv_cache_quant == "q8_0"


def test_kv_quant_to_cache_type_mapping():
    assert kv_quant_to_cache_type("q8_0") == "q8_0"
    assert kv_quant_to_cache_type("q4_0") == "q4_0"
    assert kv_quant_to_cache_type("f16") == "f16"
    assert kv_quant_to_cache_type("unknown") == "f16"