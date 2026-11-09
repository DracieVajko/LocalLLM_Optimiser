"""Quick A/B: KV cache on GPU vs system RAM, same weights and context.

Loads one model twice (unload in between), measures load time and generation
time on an identical prompt. Quality is identical by construction; the
difference is speed and memory placement.

Example:
    python tools/quick_cache_ab.py --model qwen3.8-9b-distill --context 8192
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from lm_optimizer.cli.main import get_client
from lm_optimizer.cli.sandbox_duel import _load_best_config
from lm_optimizer.domain.models import LoadConfiguration

PROMPT = (
    "Write a concise but complete technical brief of about 500 words explaining "
    "how the KV cache in a transformer works, why it grows with context length, "
    "and the trade-offs between keeping it in GPU memory and in system RAM. "
    "Use short headings and bullet points."
)


def _pick(response) -> tuple[str, int, str, dict]:
    if isinstance(response, dict):
        choices = response.get("choices") or []
        usage = response.get("usage") or {}
        content = (choices[0].get("message") or {}).get("content", "") if choices else ""
        return (
            content,
            int(usage.get("completion_tokens", 0) or 0),
            response.get("thinking_text") or "",
            response.get("stats") or {},
        )
    choices = response.choices or []
    return (
        choices[0].message.content if choices else "",
        int(response.usage.completion_tokens or 0),
        response.thinking_text or "",
        response.stats or {},
    )


async def _variant(model: str, context: int, kv_gpu: bool, runs: int) -> dict:
    client = get_client()
    await client.connect(echo_probe=False)
    result = {"kv_gpu": kv_gpu, "load_s": 0.0, "runs": []}
    try:
        await client.unload_all()
        try:
            cfg, _ = _load_best_config(model)
        except ValueError:
            cfg = LoadConfiguration()
        cfg = replace(
            cfg,
            context_length=context,
            offload_kv_cache_to_gpu=kv_gpu,
        )
        started = time.perf_counter()
        loaded = await client.load_model(model, cfg)
        result["load_s"] = round(time.perf_counter() - started, 1)
        if not getattr(loaded, "success", False):
            result["error"] = str(getattr(loaded, "error", "load failed"))[:300]
            return result
        try:
            for index in range(runs):
                started = time.perf_counter()
                response = await client.chat_completion(
                    model=model,
                    input_text=PROMPT,
                    temperature=0.0,
                    max_output_tokens=1200,
                    reasoning="on",
                )
                elapsed = time.perf_counter() - started
                content, tokens, thinking, stats = _pick(response)
                result["runs"].append(
                    {
                        "run": index + 1,
                        "gen_s": round(elapsed, 2),
                        "tokens": tokens,
                        "tok_s": round(tokens / elapsed, 2) if elapsed else 0.0,
                        "thinking_chars": len(thinking),
                        "ttft_s": stats.get("time_to_first_token_seconds"),
                        "server_tok_s": stats.get("tokens_per_second"),
                        "chars": len(content),
                    }
                )
        finally:
            await client.ensure_unloaded(model)
    finally:
        await client.close()
    return result


async def main_async(args) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "model": args.model,
        "context": args.context,
        "runs": args.runs,
        "variants": [],
    }
    for kv_gpu in (True, False):
        label = "KV_GPU" if kv_gpu else "KV_RAM"
        print(f"[{label}] loading {args.model} ctx={args.context}", flush=True)
        variant = await _variant(args.model, args.context, kv_gpu, args.runs)
        payload["variants"].append(variant)
        if "error" in variant:
            print(f"[{label}] FAILED: {variant['error']}", flush=True)
            continue
        print(f"[{label}] load={variant['load_s']}s", flush=True)
        for run in variant["runs"]:
            print(
                f"[{label}] run{run['run']}: gen={run['gen_s']}s "
                f"tok/s={run['tok_s']} tokens={run['tokens']} "
                f"thinking_chars={run['thinking_chars']}",
                flush=True,
            )
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out / f"cache_ab_{stamp}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nreport: {path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen3.8-9b-distill")
    parser.add_argument("--context", type=int, default=8192)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--out", default="results/bakeoff")
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
