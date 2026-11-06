"""Optional test: MoE Expert Cache (MiB) impact on generation speed.

This test is NOT part of the default pytest suite. Run it explicitly:

    pytest tests/test_moe_expert_cache.py -m expert_cache -v -s

It benchmarks MoE models at different MoE Expert Cache values (0, 256, 512,
1024 MiB) to measure whether larger expert caches improve generation speed
on this hardware (RTX 3060 6 GB).

Requires a running LM Studio server at http://127.0.0.1:1234 with at least
one MoE model loaded and available.
"""

from __future__ import annotations

import httpx
import pytest

from lm_optimizer.services.host.lm_studio import LMStudioClient

# MoE expert cache values to test (in MiB)
EXPERT_CACHE_VALUES = [0, 256, 512, 1024]

# Models known to be MoE (active parameters < total parameters)
MOE_MODELS = [
    "qwen/qwen3-coder-30b",
    "qwen/qwen3.6-35b-a3b",
    "nvidia-nemotron-3.5-bolt-74b-a9b-24gb",
    "swift-qwen3.8-27b@q2_k",
    "swift-qwen3.8-27b@q4_k_s",
    "recursivesi/flint",
]

# Benchmark prompt - short enough for quick measurement
BENCHMARK_PROMPT = "Write a Python function to compute fibonacci numbers."
MAX_OUTPUT_TOKENS = 128


def _is_moe_model(model_id: str) -> bool:
    """Heuristic: model is MoE if its identifier contains MoE indicators."""
    moe_indicators = ("moe", "a3b", "a9b", "flint", "mixtral", "deepseek")
    return any(ind in model_id.lower() for ind in moe_indicators)


@pytest.mark.expert_cache
class TestMoEExpertCache:
    """MoE Expert Cache impact tests - run only with -m expert_cache."""

    async def _measure_tok_s(
        self,
        client: LMStudioClient,
        model_id: str,
        expert_cache_mib: int,
        repetitions: int = 1,
    ) -> float | None:
        """Measure generation tok/s for one model at one expert cache value.

        Returns tok/s or None if the run failed.
        """
        total_tok_s = 0.0
        successful = 0

        for _ in range(repetitions):
            try:
                # Apply expert cache setting via LM Studio API
                # Note: exact parameter name may vary by LM Studio version
                load_body = {
                    "model": model_id,
                    "context_length": 4096,
                    "flash_attention": True,
                    "offload_kv_cache_to_gpu": True,
                    "eval_batch_size": 2048,
                    "physical_batch_size": 512,
                    "parallel": 4,
                    "context_checkpoints": 32,
                    # MoE Expert Cache key - may be rejected by older server versions
                    "moe_expert_cache_mib": expert_cache_mib,
                }

                await client.load_model(model_id, load_body)

                # Run a quick chat benchmark
                response = await client.chat_completion(
                    model=model_id,
                    input_text=BENCHMARK_PROMPT,
                    temperature=0.7,
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                )

                choices = response.get("choices") or []
                if choices:
                    stats = response.get("_stats") or {}
                    tok_s = stats.get("generation_tok_s")
                    if tok_s is not None:
                        total_tok_s += tok_s
                        successful += 1

            except Exception as e:  # noqa: BLE001
                # Server may reject unknown key; record failure and continue
                print(f"  {model_id} cache={expert_cache_mib}MiB: error={e}")
                continue
            finally:
                # Unload is best-effort: do not hide the original failure,
                # but ensure the slot is freed for the next candidate.
                try:
                    await client.unload_model(model_id)
                except Exception:  # noqa: BLE001
                    pass

        if successful == 0:
            return None
        return total_tok_s / successful

    @pytest.mark.asyncio
    async def test_expert_cache_affects_speed(self) -> None:
        """Measure tok/s across expert cache values for available MoE models.

        This test is informational - it prints results but does not assert
        pass/fail because optimal cache value is hardware-dependent.
        """
        client = LMStudioClient(base_url="http://127.0.0.1:1234")
        try:
            await client.connect()
            try:
                models_response = await client.get_models()
                available_models = [
                    m.get("key") or m.get("id") or ""
                    for m in models_response.get("models", [])
                ]
            except httpx.ConnectError as e:
                pytest.skip(f"Cannot connect to LM Studio: {e}")

            moe_models = [m for m in available_models if _is_moe_model(m)]
            if not moe_models:
                pytest.skip("No MoE models available on this LM Studio instance")

            print(f"\n{'='*70}")
            print("MOE EXPERT CACHE BENCHMARK (MiB -> tok/s)")
            print(f"{'='*70}")
            print(f"{'Model':<40} {'Cache MiB':<12} {'tok/s':<10}")
            print(f"{'-'*70}")

            results: dict[str, dict[int, float | None]] = {}

            for model_id in moe_models:
                cache_results: dict[int, float | None] = {}
                for cache_val in EXPERT_CACHE_VALUES:
                    tok_s = await self._measure_tok_s(
                        client, model_id, cache_val, repetitions=1
                    )
                    cache_results[cache_val] = tok_s
                    display = f"{tok_s:.2f}" if tok_s is not None else "FAILED"
                    print(f"{model_id:<40} {cache_val:<12} {display:<10}")
                results[model_id] = cache_results

            print(f"{'='*70}")

            # Print summary of best cache value per model
            print(f"\n{'BEST CACHE PER MODEL':^70}")
            print(f"{'-'*70}")
            for model_id, cache_results in results.items():
                valid = {k: v for k, v in cache_results.items() if v is not None}
                if valid:
                    best_cache = max(valid, key=valid.get)
                    best_tok = valid[best_cache]
                    print(f"{model_id:<40} best={best_cache}MiB tok/s={best_tok:.2f}")
                else:
                    print(f"{model_id:<40} all failed")

        finally:
            await client.close()

        moe_models = [m for m in available_models if _is_moe_model(m)]
        if not moe_models:
            pytest.skip("No MoE models available on this LM Studio instance")

        print(f"\n{'='*70}")
        print("MOE EXPERT CACHE BENCHMARK (MiB -> tok/s)")
        print(f"{'='*70}")
        print(f"{'Model':<40} {'Cache MiB':<12} {'tok/s':<10}")
        print(f"{'-'*70}")

        results: dict[str, dict[int, float | None]] = {}

        for model_id in moe_models:
            cache_results: dict[int, float | None] = {}
            for cache_val in EXPERT_CACHE_VALUES:
                tok_s = await self._measure_tok_s(
                    client, model_id, cache_val, repetitions=1
                )
                cache_results[cache_val] = tok_s
                display = f"{tok_s:.2f}" if tok_s is not None else "FAILED"
                print(f"{model_id:<40} {cache_val:<12} {display:<10}")
            results[model_id] = cache_results

        print(f"{'='*70}")

        # Print summary of best cache value per model
        print(f"\n{'BEST CACHE PER MODEL':^70}")
        print(f"{'-'*70}")
        for model_id, cache_results in results.items():
            valid = {k: v for k, v in cache_results.items() if v is not None}
            if valid:
                best_cache = max(valid, key=valid.get)
                best_tok = valid[best_cache]
                print(f"{model_id:<40} best={best_cache}MiB tok/s={best_tok:.2f}")
            else:
                print(f"{model_id:<40} all failed")

    @pytest.mark.asyncio
    async def test_zero_cache_baseline_available(self) -> None:
        """Verify cache=0 (default) works on at least one MoE model."""
        client = LMStudioClient(base_url="http://127.0.0.1:1234")
        try:
            await client.connect()
            try:
                models_response = await client.get_models()
                available_models = [
                    m.get("key") or m.get("id") or ""
                    for m in models_response.get("models", [])
                ]
            except Exception as e:
                pytest.skip(f"Cannot list models: {e}")

            moe_models = [m for m in available_models if _is_moe_model(m)]
            if not moe_models:
                pytest.skip("No MoE models available")

            # Test that cache=0 works on first MoE model
            model_id = moe_models[0]
            tok_s = await self._measure_tok_s(client, model_id, 0, repetitions=1)
            assert tok_s is not None, f"cache=0 baseline failed on {model_id}"
            assert tok_s > 0, f"cache=0 produced 0 tok/s on {model_id}"
        finally:
            await client.close()