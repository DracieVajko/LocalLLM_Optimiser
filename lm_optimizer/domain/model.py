"""Model identity model."""

from dataclasses import dataclass

@dataclass
class ModelIdentity:
    """Unique model identifier."""

    id: str
    name: str
    architecture: str | None = None
    parameter_count: int | None = None
    quantization: str | None = None
    context_limit: int | None = None
    is_moe: bool = False
    num_experts: int | None = None
    size_bytes: int | None = None
    # Provider-declared model type ("llm", "embedding", "reranker", ...).
    # None when the backend does not report it; eligibility then falls back to
    # architecture/name signals and stays conservative.
    model_type: str | None = None
    # LM Studio key (publisher/model) - distinct from id when variants exist.
    # e.g. id="swift-qwen3.8-27b@q3_k_m", key="swift-qwen3.8-27b"
    key: str | None = None
    # Selected variant from LM Studio (e.g. "swift-qwen3.8-27b@q3_k_m")
    selected_variant: str | None = None

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if isinstance(other, ModelIdentity):
            return self.id == other.id
        return False
