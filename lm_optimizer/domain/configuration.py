"""Load configuration and host capability models."""

from dataclasses import dataclass, field
from typing import ClassVar

@dataclass
class LoadConfiguration:
    """Model load configuration parameters.

    `gpu_ratio` / `rope_freq_*` are kept for preset/space compatibility but are
    NOT sent to the server (rejected via REST, HTTP 400 `unrecognized_keys`).
    `to_api_params()` returns only server-supported keys (verified live).
    """

    # Keys accepted by POST /api/v1/models/load (verified live 2026-09-19).
    API_KEYS: ClassVar[frozenset] = frozenset(
        {
            "context_length",
            "flash_attention",
            "offload_kv_cache_to_gpu",
            "eval_batch_size",
            "physical_batch_size",
            "parallel",
            "context_checkpoints",
            "reasoning_budget_message",
            "num_experts",
            "speculative_draft_max_tokens",
            "speculative_draft_min_tokens",
            "speculative_draft_min_continue_probability",
            "speculative_draft_mtp",
            "speculative_draft_simple",
            "speculative_draft_model",
        }
    )

    context_length: int | None = None
    gpu_ratio: float | None = None
    flash_attention: bool | None = None
    offload_kv_cache_to_gpu: bool | None = None
    eval_batch_size: int | None = None
    physical_batch_size: int | None = None
    parallel: int | None = None
    context_checkpoints: int | None = None
    reasoning_budget_message: str | None = None
    num_experts: int | None = None
    speculative_draft_max_tokens: int | None = None
    speculative_draft_min_tokens: int | None = None
    speculative_draft_min_continue_probability: float | None = None
    speculative_draft_mtp: bool | None = None
    speculative_draft_simple: bool | None = None
    speculative_draft_model: str | None = None
    rope_freq_base: float | None = None
    rope_freq_scale: float | None = None
    # llama.cpp-only: not sent via REST (unrecognized key). Used for llama-server CLI translation.
    n_cpu_moe: int | None = None

    def to_dict(self) -> dict:
        """Convert to dict, excluding None values."""
        return {k: v for k, v in self.__dict__.items() if v is not None}

    def to_api_params(self) -> dict:
        """Convert to API parameters: only server-supported keys, excluding None."""
        return {k: v for k, v in self.__dict__.items() if k in self.API_KEYS and v is not None}


@dataclass
class LMStudioCapabilities:
    """Detected LM Studio API capabilities."""

    version: str = "unknown"
    supports_context_length: bool = True
    supports_gpu_ratio: bool = True
    supports_flash_attention: bool = False
    supports_kv_cache_placement: bool = False
    supports_kv_cache_quantization: bool = False
    supports_eval_batch_size: bool = True
    supports_physical_batch_size: bool = True
    supports_parallel: bool = True
    supports_context_checkpoints: bool = True
    supports_num_experts: bool = False
    supports_rope_scaling: bool = False
    # Speculative decoding / MTP (probed 2026-10-21: all five keys are
    # recognized by the live REST v1 API).
    supports_speculative_draft: bool = False
    supports_speculative_mtp: bool = False
    supports_n_cpu_moe: bool = False
    # Runtime-only facts on this build: KV cache quantization, CPU threads,
    # mmap and keep-in-memory are NOT settable through REST (400
    # unrecognized_keys in every spelling tried). They are observed, never
    # searched - see lm_optimizer/services/lm_studio_capabilities.py.
    supports_cpu_threads: bool = False
    supports_mmap: bool = False
    load_parameters: list[str] = field(default_factory=list)

    def get_supported_load_params(self) -> list[str]:
        """Get list of supported load parameters."""
        params = []
        if self.supports_context_length:
            params.append("context_length")
        if self.supports_gpu_ratio:
            params.append("gpu_ratio")
        if self.supports_flash_attention:
            params.append("flash_attention")
        if self.supports_kv_cache_placement:
            params.append("offload_kv_cache_to_gpu")
        if self.supports_kv_cache_quantization:
            params.append("kv_cache_quantization")
        if self.supports_eval_batch_size:
            params.append("eval_batch_size")
        if self.supports_physical_batch_size:
            params.append("physical_batch_size")
        if self.supports_parallel:
            params.append("parallel")
        if self.supports_context_checkpoints:
            params.append("context_checkpoints")
        if self.supports_num_experts:
            params.append("num_experts")
        if self.supports_rope_scaling:
            params.extend(["rope_freq_base", "rope_freq_scale"])
        if self.supports_speculative_draft:
            params.extend(
                [
                    "speculative_draft_max_tokens",
                    "speculative_draft_min_tokens",
                    "speculative_draft_min_continue_probability",
                ]
            )
        if self.supports_speculative_mtp:
            params.append("speculative_draft_mtp")
        for extra in ("reasoning_budget_message", "speculative_draft_simple",
                      "speculative_draft_model"):
            if extra in (self.load_parameters or []) and extra not in params:
                params.append(extra)
        return params
