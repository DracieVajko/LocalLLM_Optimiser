"""Tests for llama.cpp RoPE scaling support."""

from __future__ import annotations

from lm_optimizer.domain.configuration import LoadConfiguration
from lm_optimizer.backends.llamacpp.config import from_load_config


def test_rope_scaling_when_context_exceeds_native():
    cfg = LoadConfiguration(context_length=8192)
    args = from_load_config(cfg, model_path="/m.gguf", vram_gb=8.0, model_size_gb=4.0, native_context=4096)
    assert args.rope_freq_base_checked is True
    assert args.rope_freq_base > 0
    assert args.rope_freq_scale < 1.0  # scale down for larger context


def test_rope_no_scaling_when_context_within_native():
    cfg = LoadConfiguration(context_length=2048)
    args = from_load_config(cfg, model_path="/m.gguf", vram_gb=8.0, model_size_gb=4.0, native_context=4096)
    assert args.rope_freq_base_checked is False
    assert args.rope_freq_scale == 1.0


def test_rope_in_cli():
    cfg = LoadConfiguration(context_length=8192)
    args = from_load_config(cfg, model_path="/m.gguf", vram_gb=8.0, model_size_gb=4.0, native_context=4096)
    cli = args.to_cli_string()
    assert "--rope-freq-base" in cli
    assert "--rope-freq-scale" in cli


def test_no_rope_when_no_native_context():
    cfg = LoadConfiguration(context_length=8192)
    args = from_load_config(cfg, model_path="/m.gguf", vram_gb=8.0, model_size_gb=4.0, native_context=0)
    assert args.rope_freq_base_checked is False