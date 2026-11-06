# EXPERIMENT-PLAN.md — Corrected Benchmark for Q2_K / Q4_K_S on RTX 3060 6 GB

## Why this plan exists

Two prior runs (Q4_K_S, Q2_K) tested 16 configs at ctx 4096 but only 2 at ctx 8192.
Batch, physical_batch, context_checkpoints showed no trend (confirmed twice).
parallel=1 consistently won (+10–15%).
Validation rounds were cache-replayed (Q2) or flaky (Q4, 2/6 failed quality).
`long_context` sent only 297 tokens (4% of window).
`gpu_ratio` was never sent (CLI/GUI-only gap).

This plan fixes all of the above.

## Noise floor (measured)

- Identical config, 5 samples: sd ≈ 6% (2.57–3.01 tok/s)
- To distinguish a 10% effect from noise: need ≥3 samples per config

## No-op dimensions (confirmed twice, two models)

| Parameter | Evidence | Decision |
|---|---|---|
| eval_batch_size | No trend (1.61–2.5 across values) | Fix at 2048 |
| physical_batch_size | Contradictory (1.71–2.06) | Fix at 512 |
| context_checkpoints | No trend (1.73–2.4) | Fix at 32 |
| parallel | +10–15% for par=1 | Fix at 1 |

## Active dimensions to sweep

| Dimension | Values | Rationale |
|---|---|---|
| gpu_ratio (offload) | auto, 0.7, 0.5 | RTX 3060 6 GB, model 12–17 GB. Offload split is the dominant speed lever on this hardware. |
| context_length | 4096, 8192 | Two context sizes to measure actual context scaling. |

## Experiment matrix

```
fix: batch=2048, phys=512, ck=32, par=1, flash=on, kv=on-GPU
sweep:  gpu_ratio {auto, 0.7, 0.5}   ×   ctx {4096, 8192}
        = 6 configs × 3 repetitions = 18 measurements
```

## Expected duration

- 18 measurements × ~20 min each ≈ 6 hours
- Plus recall probe on ctx {8192, 16384} ≈ 20 min
- Total: ~6.5 hours

## Commands

### Q2_K (run first)

```bash
python -m lm_optimizer.cli.main run \
  --model "swift-qwen3.8-27b@q2_k" \
  --preset standard \
  --repetitions 3 \
  --context-lengths 4096 8192 \
  --gpu-ratios auto 0.7 0.5 \
  --batch-size 2048 \
  --physical-batch-size 512 \
  --context-checkpoints 32 \
  --parallel 1 \
  --flash-attention on \
  --offload-kv-cache-to-gpu on
```

### Q4_K_S (run second, after Q2)

Same command with `--model "swift-qwen3.8-27b@q4_k_s"`.

## Acceptance criteria ("enough")

1. Every config has ≥3 measured samples (not cached)
2. `long_context` prompt_tokens ≥ 60% of context window
3. `gpu_ratio` is recorded in the report (not "N/A")
4. Phase timings sum to ≥90% of duration_ms
5. DB row has status=success, completed_at set, pareto non-empty
6. No cache replay (cache_hits=0 or all measured)

## What this experiment will answer

- Does offloading 30% or 50% of layers to CPU improve or hurt speed on 6 GB?
- Does the 6% noise floor make the par=1 win real or illusory?
- What is the actual max stable context (with recall probe)?
- Is the model's quality stable across 3 samples?

## What this experiment will NOT answer

- Optimal batch/phys/ck (confirmed no-op, fixed)
- Throughput under concurrent load (separate throughput profile)
- Other quantizations (Q3, Q5, Q6, Q8 — separate runs)
