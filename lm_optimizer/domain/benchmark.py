"""Benchmark case and metrics models."""

from dataclasses import dataclass

@dataclass
class BenchmarkCase:
    """A single benchmark test case."""

    name: str
    category: str
    prompt: str
    max_tokens: int
    temperature: float = 0.7
    top_p: float | None = None
    top_k: int | None = None
    stop_sequences: list[str] | None = None

@dataclass
class BenchmarkMetrics:
    """Metrics from a single benchmark test.

    Note: estimated_ttft_ms is an *estimate* derived from total generation
    time when streaming is not available (ttft ~ 10% of total time).
    It is NOT a directly measured time-to-first-token. See docs/OPTIMIZATION_METHOD.md.
    """

    test_name: str
    category: str
    success: bool
    load_time_ms: float = 0.0
    estimated_ttft_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_processing_ms: float = 0.0
    generation_ms: float = 0.0
    prompt_tok_s: float = 0.0
    generation_tok_s: float = 0.0
    error: str | None = None
    output_text: str = ""
    # Reasoning trace, when the server exposes it separately from the answer.
    # Empty for non-reasoning models and all pre-plumbing rows (honest "n/a").
    thinking_text: str = ""
    # The exact prompt sent (for per-test Prompt/Thinking/Output display).
    prompt: str = ""

    # Cache provenance (WP R2-1): True when this metric was served from cache
    # rather than a fresh measurement. Never present cached data as measured.
    from_cache: bool = False

    # MTP / Speculative Decoding metrics (P0)
    # Only populated when speculative decoding / MTP is active and server
    # exposes the statistics. Remain None/0 when not applicable.
    draft_tokens_proposed: int = 0
    draft_tokens_accepted: int = 0
    acceptance_rate: float = 0.0
    speedup_ratio: float = 1.0
    draft_vram_delta_mb: float = 0.0
    draft_ram_delta_mb: float = 0.0
    draft_ttft_delta_ms: float = 0.0

    # Thermal / power (spec §11.4, §17.2). None means unavailable.
    gpu_temp_c: float | None = None
    gpu_util_pct: float | None = None
    gpu_power_w: float | None = None
    on_ac: bool | None = None
    thermal_flag: str = ""

    @property
    def ttft_ms(self) -> float:
        """Backward compatibility alias for estimated_ttft_ms."""
        return self.estimated_ttft_ms

    @ttft_ms.setter
    def ttft_ms(self, value: float) -> None:
        self.estimated_ttft_ms = value
