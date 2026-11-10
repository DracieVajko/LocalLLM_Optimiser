"""Model bake-off: load time, generation time (incl. thinking) and sandbox scores.

Runs a model x task matrix while keeping the model loaded between tasks, so
the measured load cost is paid once and reported separately from generation.
Generation time always includes the model's thinking/reasoning phase, because
it is measured around the single chat call and thinking is enabled explicitly.

Examples:
    python tools/model_bakeoff.py --models qwen9b,e4b --tasks email_write,company_website
    python tools/model_bakeoff.py --models all --tasks company_website,blender_skyblock
    python tools/model_bakeoff.py --models bonsai --tasks email_write,company_website --vram-only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from lm_optimizer.domain.models import LoadConfiguration
from lm_optimizer.services.sandbox_history import record_run
from lm_optimizer.services.model_gate import ModelGate, ModelGateTimeout
from lm_optimizer.services.sandbox_lab import SANDBOX_TASKS, SandboxPolicy
from lm_optimizer.services.sandbox_runner import (
    SandboxRunner,
    apply_retention,
    build_command_for,
)

CANDIDATES = {
    "qwen9b": "qwen3.8-9b-distill",
    "e4b": "nvidia-nemotron-3.5-bolt-e4b",
    "bonsai": "prism-ml/bonsai-27b",
    "swift": "swift-qwen3.8-27b",
    "twin": "qwen3.8-27b-twin-turbo-fable-cold-fusion-709-ultra-heretic-uncensored-nm-dau-neo-mtp",
    "nemotron74b": "nvidia-nemotron-3.5-bolt-74b-a9b",
    "qwen35b": "qwen/qwen3.6-35b-a3b",
    "gemma": "google/gemma-4-26b-a4b-qat",
    "gptoss": "openai-gpt-oss-20b-claude-4.5-opus-heretic-uncensored-i1",
}

DEFAULT_TASKS = "email_write,company_website,blender_skyblock"
DEFAULT_ROOT = Path("results") / "bakeoff"


def _slug(model: str) -> str:
    out = model
    for ch in '/\\:@ ':
        out = out.replace(ch, "_")
    return out[:80]


def _backend_models() -> list[str]:
    """List models from the configured backend (LM Studio / Ollama)."""
    import asyncio

    from lm_optimizer.cli.main import get_client

    client = get_client()

    async def _list() -> list[str]:
        await client.connect(echo_probe=False)
        try:
            models = await client.list_models(force_refresh=True)
        finally:
            await client.close()
        return [m.id for m in models if "embed" not in m.id.lower()]

    return asyncio.run(_list())


def _resolve_models(spec: str) -> list[str]:
    raw = (spec or "all").strip()
    if raw.lower() in ("all", "*"):
        models = _backend_models()
        if not models:
            raise RuntimeError(
                "No models returned by the configured backend; pass --models explicitly"
            )
        return models
    resolved = []
    for part in (p.strip() for p in raw.split(",") if p.strip()):
        resolved.append(CANDIDATES.get(part, part))
    return resolved


def _load_config(
    model: str, context: int, kv_ram: bool = False, safe: bool = False
) -> tuple[LoadConfiguration, int]:
    from lm_optimizer.cli.sandbox_duel import _load_best_config

    try:
        cfg, _ = _load_best_config(model)
    except ValueError:
        cfg = LoadConfiguration(context_length=context)
    # A fixed context makes the comparison fair and bounds KV-cache cost.
    cfg = replace(cfg, context_length=context)
    if kv_ram:
        cfg = replace(cfg, offload_kv_cache_to_gpu=False)
    if safe:
        # Large models on a 6 GB card: one sequence, small batches, KV in RAM.
        cfg = replace(
            cfg,
            offload_kv_cache_to_gpu=False,
            eval_batch_size=128,
            physical_batch_size=128,
            parallel=1,
        )
    return cfg, context


async def _run_task(
    client,
    model: str,
    task_id: str,
    *,
    thinking: bool,
    load_s: float | None,
    root: Path,
    reasoning_effort: str,
) -> dict:
    definition = SANDBOX_TASKS[task_id]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_dir = root / _slug(model) / task_id
    workdir = base_dir / stamp
    policy = SandboxPolicy(
        workdir=workdir,
        network_enabled=False,
        timeout_s=definition.timeout_s,
        allowed_executables=definition.allowed_executables,
    )
    metrics: dict = {"attempts": [], "gen_s": 0.0, "tokens": 0, "thinking_chars": 0}

    async def generate(feedback: str) -> str:
        prompt = definition.prompt
        if feedback:
            prompt = feedback + "\n\n" + prompt
        started = time.perf_counter()
        if not thinking:
            reasoning_value = "off"
        elif reasoning_effort.strip().lower() in ("", "default"):
            reasoning_value = None
        else:
            reasoning_value = reasoning_effort
        response = await client.chat_completion(
            model=model,
            input_text=prompt,
            temperature=0.0,
            max_output_tokens=definition.max_output_tokens,
            reasoning=reasoning_value,
        )
        elapsed = time.perf_counter() - started
        if isinstance(response, dict):
            usage = response.get("usage") or {}
            choices = response.get("choices") or []
            tokens = int(usage.get("completion_tokens", 0) or 0)
            thinking_text = response.get("thinking_text") or ""
            stats = response.get("stats") or {}
            content = (
                (choices[0].get("message") or {}).get("content", "")
                if choices
                else ""
            )
        else:
            tokens = int(response.usage.completion_tokens or 0)
            thinking_text = response.thinking_text or ""
            stats = response.stats or {}
            content = response.choices[0].message.content if response.choices else ""
        thinking_chars = len(thinking_text)
        metrics["gen_s"] += elapsed
        metrics["tokens"] += tokens
        metrics["thinking_chars"] += thinking_chars
        metrics["attempts"].append(
            {
                "gen_s": round(elapsed, 1),
                "tokens": tokens,
                "tok_s": round(tokens / elapsed, 2) if elapsed else 0.0,
                "thinking_chars": thinking_chars,
                "server_tok_s": stats.get("tokens_per_second"),
                "ttft_s": stats.get("time_to_first_token_seconds"),
            }
        )
        return content

    runner = SandboxRunner(
        task=definition,
        policy=policy,
        workdir=workdir,
        command=build_command_for(definition),
        model=model,
    )
    result = await runner.run_async(generate)
    payload = result.as_dict()
    record_run(
        model,
        task_id,
        payload,
        workdir=str(workdir),
        duration_s=metrics["gen_s"],
    )
    apply_retention(base_dir, policy)

    gen_s = round(metrics["gen_s"], 1)
    measured = str(payload.get("status") or "measured") == "measured"
    return {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "task": task_id,
        "thinking": thinking,
        "context": None,
        "load_s": round(load_s, 1) if load_s is not None else None,
        "load_measured": load_s is not None,
        "gen_s": gen_s,
        "total_s": round((load_s or 0.0) + metrics["gen_s"], 1),
        "tokens": metrics["tokens"],
        "tok_s": round(metrics["tokens"] / metrics["gen_s"], 2) if metrics["gen_s"] else 0.0,
        "thinking_chars": metrics["thinking_chars"],
        "status": "measured" if measured else "not_measured",
        "first_pass_success": payload.get("first_pass_success"),
        "final_success": payload.get("final_success"),
        "repair_count": payload.get("repair_count"),
        "final_score": score if measured else None,
        "penalized_score": payload.get("penalized_score") if measured else None,
        "error": payload.get("error") or "",
        "critical_failures": payload.get("critical_failures") or [],
        "attempts": metrics["attempts"],
        "workdir": str(workdir),
    }


async def _run_model(
    model: str,
    tasks: list[str],
    *,
    thinking: bool,
    context: int,
    root: Path,
    reasoning_effort: str,
    kv_ram: bool = False,
    safe: bool = False,
) -> list[dict]:
    from lm_optimizer.cli.main import get_client

    client = get_client()
    rows: list[dict] = []
    await client.connect(echo_probe=False)
    try:
        cfg, _ = _load_config(model, context, kv_ram, safe)
        gate = ModelGate(client)
        print(f"[load] {model} ctx={context}", flush=True)
        try:
            lease = await gate.acquire(model, cfg)
        except ModelGateTimeout as exc:
            print(f"[load] BLOCKED {model}: {exc}", flush=True)
            return [
                {
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "model": model,
                    "task": "(load)",
                    "thinking": thinking,
                    "context": context,
                    "load_s": 0.0,
                    "error": f"model gate: {exc}"[:300],
                }
            ]
        load_s = lease.load_s if lease.load_measured else None
        suffix = " (reused)" if lease.reused else ""
        if not lease.load_measured:
            suffix += " (load response lost; load time not measured)"
        if lease.fallback:
            suffix += f" (fallback for {model})"
        print(f"[load] ok {lease.load_s:.1f}s{suffix}", flush=True)
        try:
            for task_id in tasks:
                print(f"[task] {lease.model} :: {task_id}", flush=True)
                row = await _run_task(
                    client,
                    lease.model,
                    task_id,
                    thinking=thinking,
                    load_s=load_s,
                    root=root,
                    reasoning_effort=reasoning_effort,
                )
                row["context"] = context
                rows.append(row)
                print(
                    f"[task] {task_id}: score={row['final_score']} "
                    f"pass={row['final_success']} gen={row['gen_s']}s "
                    f"tok/s={row['tok_s']} think_chars={row['thinking_chars']}",
                    flush=True,
                )
        finally:
            await gate.release(lease)
    finally:
        await client.close()
    return rows


def _write_summary(rows: list[dict], root: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = root / f"summary_{stamp}.md"
    by_model: dict[str, list[dict]] = {}
    for row in rows:
        by_model.setdefault(row["model"], []).append(row)
    lines = ["# Model bake-off", "", f"Generated: {stamp}", ""]
    lines.append(
        "| model | task | score | pass | load_s | gen_s | total_s | "
        "tok/s | thinking_chars |"
    )
    lines.append("|---|---|---:|---|---:|---:|---:|---:|---:|")
    for model, model_rows in by_model.items():
        for row in model_rows:
            score = row.get("final_score")
            score_text = "-" if score is None else score
            if row.get("status") == "not_measured":
                score_text = "not measured"
            lines.append(
                f"| {model} | {row.get('task')} | {score_text} | "
                f"{row.get('final_success')} | {row.get('load_s')} | "
                f"{row.get('gen_s')} | {row.get('total_s')} | "
                f"{row.get('tok_s')} | {row.get('thinking_chars')} |"
            )
    lines.append("")
    lines.append("## Model totals (load once + all tasks)")
    lines.append("")
    lines.append("| model | load_s | gen_s | total_s | tokens | tok/s | mean_score | scored |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for model, model_rows in by_model.items():
        loads = [r.get("load_s") for r in model_rows if r.get("load_s") is not None]
        load_s = loads[0] if loads else None
        gen_s = round(sum(r.get("gen_s") or 0.0 for r in model_rows), 1)
        tokens = sum(r.get("tokens") or 0 for r in model_rows)
        scores = [r["final_score"] for r in model_rows if r.get("final_score") is not None]
        toks = round(tokens / gen_s, 2) if gen_s else 0.0
        mean = round(statistics.fmean(scores), 3) if scores else None
        total = round((load_s or 0.0) + gen_s, 1)
        lines.append(
            f"| {model} | {load_s if load_s is not None else 'n/a'} | {gen_s} | {total} | "
            f"{tokens} | {toks} | {mean if mean is not None else '-'} | {len(scores)}/{len(model_rows)} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


async def run_bakeoff(
    models: list[str],
    tasks: list[str],
    *,
    thinking: bool,
    context: int,
    out: str,
    reasoning_effort: str,
    kv_ram: bool = False,
    safe: bool = False,
) -> int:
    unknown = [t for t in tasks if t not in SANDBOX_TASKS]
    if unknown:
        print(f"Unknown task(s): {', '.join(unknown)}")
        return 2
    root = Path(out)
    root.mkdir(parents=True, exist_ok=True)
    jsonl = root / "runs.jsonl"
    all_rows: list[dict] = []
    for model in models:
        try:
            rows = await _run_model(
                model,
                tasks,
                thinking=thinking,
                context=context,
                root=root,
                reasoning_effort=reasoning_effort,
                kv_ram=kv_ram,
                safe=safe,
            )
        except Exception as exc:  # one bad model must not stop the sweep
            print(f"[model] {model} crashed: {type(exc).__name__}: {exc}", flush=True)
            rows = [
                {
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "model": model,
                    "task": "(crash)",
                    "error": f"{type(exc).__name__}: {exc}"[:300],
                }
            ]
        for row in rows:
            with jsonl.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        all_rows.extend(rows)
    path = _write_summary(all_rows, root)
    print(f"\nsummary: {path}")
    return 0


async def main_async(args) -> int:
    models = _resolve_models(args.models)
    tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]
    return await run_bakeoff(
        models,
        tasks,
        thinking=args.thinking,
        context=args.context,
        out=args.out,
        reasoning_effort=args.reasoning_effort,
        kv_ram=args.kv_ram,
        safe=args.safe,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default="all", help="aliases/full ids, comma separated")
    parser.add_argument("--tasks", default=DEFAULT_TASKS, help="comma separated sandbox task ids")
    parser.add_argument("--context", type=int, default=8192, help="fixed context for every model")
    parser.add_argument("--thinking", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--kv-ram",
        action="store_true",
        help="keep the KV cache in system RAM (offload_kv_cache_to_gpu=false)",
    )
    parser.add_argument(
        "--safe",
        action="store_true",
        help="minimal memory config: parallel 1, batch 128, KV cache in RAM",
    )
    parser.add_argument(
        "--reasoning-effort",
        default="on",
        help="Reasoning level: off|on|low|medium|high|xhigh|default or any server value",
    )
    parser.add_argument("--out", default=str(DEFAULT_ROOT))
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
