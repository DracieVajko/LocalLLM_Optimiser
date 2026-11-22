"""Shared Mixture-of-Experts detection.

The LM Studio host adapter and the discovery inspector used two different
keyword lists, so the same model could be classified differently depending on
which path inspected it. This module is the single source of truth.
"""

from __future__ import annotations

# Gemma 4 26B A4B is an MoE: 26B total, ~4B active. The ``a4b`` suffix is the
# clearest signal, but the full names are kept for readability.
MOE_INDICATORS = (
    "moe",
    "mixtral",
    "grok",
    "deepseek-moe",
    "qwen-moe",
    "phi-moe",
    "gpt-oss",
    "gpt_oss",
    "gemma-4-26b-a4b",
    "gemma 4 26b a4b",
    "gemma4-26b-a4b",
    "a4b",
)


def is_moe_model(
    *,
    architecture: str | None = None,
    model_type: str | None = None,
    name: str | None = None,
    model_id: str | None = None,
) -> bool:
    """True when any of the model's identifiers carries an MoE signal."""
    haystacks = (
        (architecture or "").lower(),
        (model_type or "").lower(),
        (name or "").lower(),
        (model_id or "").lower(),
    )
    return any(
        indicator in haystack
        for indicator in MOE_INDICATORS
        for haystack in haystacks
    )