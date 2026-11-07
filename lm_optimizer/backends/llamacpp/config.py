"""Translate LoadConfiguration to llama-server CLI arguments.

Maps optimizer concepts to llama.cpp flags:
  context_length     -> --ctx-size
  flash_attention    -> --flash-attn
  offload_kv_cache   -> (implicit in --ctx-size + VRAM)
  eval_batch_size    -> --batch-size
  physical_batch_size-> --ubatch-size
  parallel           -> --parallel (n_parallel)
  gpu_ratio          -> --n-gpu-layers (derived)
  num_experts (MoE)  -> --n-cpu-moe
  kv quantization    -> --cache-type-k / --cache-type-v
  rope settings      -> --rope-freq-base / --rope-freq-scale
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lm_optimizer.domain.models import LoadConfiguration


@dataclass
class LlamaCppArgs:
    """Structured llama-server arguments."""

    model_path: str = ""
    ctx_size: int = 4096
    n_gpu_layers: int = 99
    n_cpu_moe: int = 0
    flash_attn: bool = True
    batch_size: int = 2048
    ubatch_size: int = 512
    parallel: int = 1
    threads: int = 0
    cache_type_k: str = "f16"
    cache_type_v: str = "f16"
    rope_freq_base: float = 0.0
    rope_freq_scale: float = 1.0
    rope_freq_base_checked: bool = False
    mlock: bool = False
    no_mmap: bool = False
    temperature: float = 0.7
    seed: int = 42

    def to_cli_args(self) -> list[str]:
        """Convert to a list of CLI argument strings."""
        args: list[str] = []
        if self.model_path:
            args.extend(["--model", self.model_path])
        args.extend(["--ctx-size", str(self.ctx_size)])
        args.extend(["--n-gpu-layers", str(self.n_gpu_layers)])
        if self.n_cpu_moe > 0:
            args.extend(["--n-cpu-moe", str(self.n_cpu_moe)])
        if self.flash_attn:
            args.append("--flash-attn")
        else:
            args.append("--no-flash-attn")
        args.extend(["--batch-size", str(self.batch_size)])
        args.extend(["--ubatch-size", str(self.ubatch_size)])
        args.extend(["--parallel", str(self.parallel)])
        if self.threads > 0:
            args.extend(["--threads", str(self.threads)])
        args.extend(["--cache-type-k", self.cache_type_k])
        args.extend(["--cache-type-v", self.cache_type_v])
        if self.rope_freq_base_checked and self.rope_freq_base > 0:
            args.extend(["--rope-freq-base", str(self.rope_freq_base)])
        if self.rope_freq_scale != 1.0:
            args.extend(["--rope-freq-scale", str(self.rope_freq_scale)])
        if self.mlock:
            args.append("--mlock")
        if self.no_mmap:
            args.append("--no-mmap")
        args.extend(["--temp", str(self.temperature)])
        args.extend(["--seed", str(self.seed)])
        return args

    def to_cli_string(self) -> str:
        """Convert to a single CLI command string."""
        return " ".join(self.to_cli_args())


def from_load_config(
    config: LoadConfiguration,
    model_path: str = "",
    vram_gb: float = 0.0,
    model_size_gb: float = 0.0,
    is_moe: bool = False,
    num_experts: int = 0,
    native_context: int = 0,
    kv_quant: str = "f16",
    threads: int = 0,
) -> LlamaCppArgs:
    """Translate a LoadConfiguration into llama-server CLI arguments.

    Args:
        config: The optimizer's load configuration.
        model_path: Path to the GGUF model file.
        vram_gb: Available VRAM in GB.
        model_size_gb: Model weight size in GB.
        is_moe: Whether the model is Mixture-of-Experts.
        num_experts: Number of experts (for MoE).
        native_context: Model's native context length.
        kv_quant: KV cache quantization (f16, q8_0, q4_0).
        threads: CPU thread count (0 = auto).
    """
    args = LlamaCppArgs()
    args.model_path = model_path
    args.ctx_size = config.context_length
    args.flash_attn = config.flash_attention if config.flash_attention is not None else True
    args.batch_size = config.eval_batch_size or 2048
    args.ubatch_size = config.physical_batch_size or 512
    args.parallel = config.parallel or 1
    args.threads = threads
    args.cache_type_k = kv_quant
    args.cache_type_v = kv_quant

    # GPU layers: derive from gpu_ratio (default: full offload)
    ratio = 1.0 if config.gpu_ratio is None else float(config.gpu_ratio)
    if ratio >= 0.99:
        args.n_gpu_layers = 99  # all layers on GPU
    elif ratio > 0:
        args.n_gpu_layers = max(1, int(99 * ratio))
    else:
        args.n_gpu_layers = 0  # CPU only

    # MoE: n-cpu-moe
    if is_moe and num_experts and num_experts > 0:
        # For MoE, keep attention on GPU, shift experts to CPU
        # n_cpu_moe = number of layers whose experts go to CPU
        if vram_gb > 0 and model_size_gb > vram_gb:
            # Model doesn't fit in VRAM -> offload experts
            # Estimate: keep ~60% of layers' experts on GPU
            args.n_cpu_moe = max(1, int(32 * (1 - (vram_gb / model_size_gb))))
        else:
            args.n_cpu_moe = 0  # fits in VRAM, no CPU offload needed

    # RoPE scaling: enable if context exceeds native
    if native_context > 0 and config.context_length > native_context:
        args.rope_freq_base_checked = True
        # Standard RoPE base for extended context
        args.rope_freq_base = 10000.0 * (config.context_length / native_context)
        args.rope_freq_scale = native_context / config.context_length

    return args


def moe_n_cpu_moe_recommendation(
    vram_gb: float,
    model_size_gb: float,
    total_layers: int = 32,
) -> int:
    """Calculate recommended --n-cpu-moe for a MoE model.

    Keeps attention layers on GPU, shifts expert weights to CPU
    when the model doesn't fit in VRAM.
    """
    if vram_gb >= model_size_gb:
        return 0  # fits in VRAM
    # Fraction of model that doesn't fit
    overflow_ratio = 1.0 - (vram_gb / model_size_gb)
    # Shift that fraction of layers' experts to CPU
    return max(1, int(total_layers * overflow_ratio))


def kv_quant_to_cache_type(quant: str) -> str:
    """Map KV quantization string to llama.cpp cache type."""
    mapping = {
        "f16": "f16",
        "q8_0": "q8_0",
        "q8": "q8_0",
        "q4_0": "q4_0",
        "q4": "q4_0",
        "q5_0": "q5_0",
        "q5": "q5_0",
        "q6_k": "q6_K",
        "q8_k": "q8_K",
    }
    return mapping.get(quant.lower(), "f16")
