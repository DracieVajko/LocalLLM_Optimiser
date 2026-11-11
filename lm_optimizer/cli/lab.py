"""Lab CLI: Context Explorer, Quality Lab, Model Recommender, Duel.
These commands expose the P2-P5 modules as real, runnable workflows:
- `lm-optimizer context-explorer <model>` - context capacity with 1.5x
  bracketing, fill ratios and retrieval validation (P2).
- `lm-optimizer quality-lab <model>` - deterministic quality tasks with
  hard gates and reliability across seeds (P3).
- `lm-optimizer recommend` - model recommendations for this hardware (P5).
- `lm-optimizer duel <model-a> <model-b>` - controlled/best-profile duel
  with blind evaluation (P4).
All commands are read-only against the database except the duel, which
only measures.
"""
from __future__ import annotations
import json
import statistics
from typing import Any
import sys
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table
from lm_optimizer.logging_config import get_logger, setup_logging
from lm_optimizer.services.context_explorer import (
    ContextPoint,
    PointVerdict,
    build_filler,
    build_needles,
    build_report,
    classify_point,
    fill_ratios,
    format_report,
    geometric_contexts,
    score_retrieval,
)
from lm_optimizer.services.quality_lab import (
    default_tasks,
    run_task_with_seeds,
)
from lm_optimizer.services.best_effort import log_best_effort
from lm_optimizer.services.sandbox_lab import SandboxTask
logger = get_logger(__name__)
console = Console()
app = typer.Typer(
    name="lab",
    help="Context Explorer, Quality Lab, Recommender and Duel workflows",
    add_completion=False,
)
# --- helpers ---------------------------------------------------------------
def _client():
    from lm_optimizer.cli.main import get_client
    return get_client()
def _report_dir() -> Path:
    base = Path("results")
    base.mkdir(parents=True, exist_ok=True)
    return base
def _write_json(name: str, payload: dict) -> Path:
    path = _report_dir() / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
# --- P2 Context Explorer --------------------------------------------------
@app.command("context-explorer")
def context_explorer(
    model: str = typer.Argument(..., help="Model ID to explore"),
    min_context: int = typer.Option(4096, "--min-context"),
    max_context: int = typer.Option(65536, "--max-context"),
    detailed: bool = typer.Option(False, "--detailed", help="Full fill-ratio matrix"),
    retrieval: bool = typer.Option(True, "--retrieval/--no-retrieval"),
    gpu_ratio: float = typer.Option(1.0, "--gpu-ratio"),
    kv_gpu: bool = typer.Option(True, "--kv-gpu/--kv-cpu"),
    flash: bool = typer.Option(True, "--flash/--no-flash"),
    batch: int = typer.Option(2048, "--batch"),
    repetitions: int = typer.Option(1, "--repetitions"),
    min_tps: float = typer.Option(
        1.0,
        "--min-tps",
        help="Interactive speed floor for PASS (spec 8.2 default 1.0 tok/s)",
    ),
):
    """Explore the real context capacity of one model (P2).
    1.5x geometric bracketing (never power-of-two), fill-ratio validation
    and needle retrieval - a context that merely ALLOCATES is not usable.
    """
    setup_logging()
    from lm_optimizer.domain.models import LoadConfiguration
    from lm_optimizer.services.benchmark import BenchmarkService
    async def _run():
        client = _client()
        try:
            await client.connect()
            info = await client.get_model(model)
            if not info:
                console.print(f"[red]Model not found: {model}[/red]")
                sys.exit(1)
            hi = min(max_context, info.context_limit or max_context)
            ladder = geometric_contexts(min_context, hi, factor=1.5, round_to=512)
            ratios = fill_ratios(detailed=detailed)
            svc = BenchmarkService(client)
            points: list[ContextPoint] = []
            console.print(f"[dim]Ladder: {ladder}[/dim]")
            for ctx in ladder:
                cfg = LoadConfiguration(
                    context_length=ctx,
                    gpu_ratio=gpu_ratio,
                    flash_attention=flash,
                    offload_kv_cache_to_gpu=kv_gpu,
                    eval_batch_size=batch,
                )
                speeds: list[float] = []
                err = ""
                ok = False
                for _ in range(max(1, repetitions)):
                    good, tok, error = await svc.smoke_test(model, cfg)
                    if good:
                        ok = True
                        speeds.append(tok)
                    else:
                        err = error
                median = statistics.median(speeds) if speeds else None
                verdict = classify_point(median, ok=ok, error=err, min_tps=min_tps)
                point = ContextPoint(
                    ctx=ctx,
                    verdict=verdict,
                    median_tok_s=median,
                    error=err[:160],
                )
                points.append(point)
                console.print(
                    f"  {ctx:<8} {verdict.value:<15} "
                    f"{median if median is not None else '-'} tok/s"
                )
                if verdict in (PointVerdict.FAIL_OOM, PointVerdict.FAIL_LOAD):
                    break
            # Retrieval validation on the largest usable point.
            if retrieval:
                usable = [p for p in points if p.ok and p.median_tok_s]
                if usable:
                    best = max(usable, key=lambda p: p.ctx)
                    # Fill-ratio validation (spec 8.4): the same context must
                    # still answer with the prompt filled to 50% / 90% (fast)
                    # or the full matrix (--detailed). A context that only
                    # LOADS is not usable.
                    cfg = LoadConfiguration(
                        context_length=best.ctx,
                        gpu_ratio=gpu_ratio,
                        flash_attention=flash,
                        offload_kv_cache_to_gpu=kv_gpu,
                        eval_batch_size=batch,
                    )
                    ok, _ident, _loaded, _ch, _ap, err = await svc._channel_load(model, cfg)
                    if not ok:
                        console.print(f"[yellow]retrieval load failed: {err}[/yellow]")
                    else:
                        # Reserve room for the question + the answer. The
                        # filler's token estimate now counts punctuation, so
                        # the budget can be used directly.
                        reserve = 512
                        for ratio in ratios:
                            budget = max(128, int((best.ctx - reserve) * ratio))
                            filler = build_filler(budget, kind="mixed", seed=42)
                            question = "\n\nWhat is the access code for the north depot?"
                            try:
                                response = await client.chat_completion(
                                    model=model,
                                    input_text=filler + question,
                                    temperature=0.0,
                                    max_output_tokens=64,
                                )
                                text = ""
                                choices = response.get("choices") or []
                                if choices:
                                    text = choices[0].get("message", {}).get("content", "")
                                mark = "PASS" if text.strip() else "FAIL"
                                best.fill_ratio = ratio
                                console.print(
                                    f"  fill {ratio:.0%} @ ctx {best.ctx}: {mark} "
                                    f"({len(text.split())} words back)"
                                )
                            except Exception as e:  # noqa: BLE001
                                console.print(
                                    f"  fill {ratio:.0%} @ ctx {best.ctx}: "
                                    f"[red]error {str(e)[:80]}[/red]"
                                )
                        # Needle retrieval at 95% on the same load.
                        needle_filler = build_filler(
                            max(128, int((best.ctx - reserve) * 0.9)),
                            kind="mixed",
                            seed=42,
                        )
                        needles = build_needles(needle_filler)
                        needle = needles[-1]
                        try:
                            response = await client.chat_completion(
                                model=model,
                                input_text=needle.prompt + "\n\n" + needle.question,
                                temperature=0.0,
                                max_output_tokens=64,
                            )
                            text = ""
                            choices = response.get("choices") or []
                            if choices:
                                text = choices[0].get("message", {}).get("content", "")
                            best.retrieval_passed = score_retrieval(text, needle.key)
                            console.print(
                                f"  retrieval @ {best.ctx}: "
                                f"{'PASS' if best.retrieval_passed else 'FAIL'}"
                            )
                        except Exception as e:  # noqa: BLE001
                            console.print(f"[yellow]retrieval failed: {e}[/yellow]")
                        try:
                            await svc.ensure_unloaded(model)
                        except Exception as exc:
                            log_best_effort("best-effort operation failed", exc)
            report = build_report(points, min_tps=min_tps)
            console.print("")
            console.print(format_report(report, model))
            path = _write_json(
                f"context-explorer-{model.replace('/', '_').replace(':', '_')}.json",
                report.as_dict(),
            )
            console.print(f"\nReport saved: {path}")
        finally:
            try:
                await client.close()
            except Exception as exc:
                log_best_effort("best-effort operation failed", exc)
    import asyncio
    asyncio.run(_run())
# --- P3 Quality Lab -------------------------------------------------------
@app.command("quality-lab")
def quality_lab(
    model: str = typer.Argument(..., help="Model ID to evaluate"),
    category: list[str] = typer.Option(
        None, "--category", help="Only run these categories (repeatable)"
    ),
    seeds: int = typer.Option(3, "--seeds", help="Repetitions per task (reliability)"),
    context_length: int = typer.Option(8192, "--context"),
    batch: int = typer.Option(2048, "--batch"),
    threshold: float = typer.Option(0.97, "--threshold"),
):
    """Run the deterministic quality task suite on one model (P3).
    Hard gates run BEFORE scoring; reliability is reported as mean /
    median / worst / stdev / success rate over several seeds.
    """
    setup_logging()
    from lm_optimizer.domain.models import LoadConfiguration
    from lm_optimizer.services.benchmark import BenchmarkService
    wanted = {c.strip() for c in category} if category else None
    tasks = [t for t in default_tasks() if not wanted or t.category.value in wanted]
    if not tasks:
        console.print("[red]No matching tasks.[/red]")
        sys.exit(2)
    async def _run():
        client = _client()
        try:
            await client.connect()
            cfg = LoadConfiguration(
                context_length=context_length,
                flash_attention=True,
                offload_kv_cache_to_gpu=True,
                eval_batch_size=batch,
            )
            svc = BenchmarkService(client)
            ok, _i, _l, _ch, _ap, err = await svc._channel_load(model, cfg)
            if not ok:
                console.print(f"[red]Load failed: {err}[/red]")
                sys.exit(1)
            results = []
            for task in tasks:
                outcomes, reliability = await run_task_with_seeds(
                    task,
                    lambda prompt, max_tokens: _chat(client, model, prompt, max_tokens),
                    seeds=list(range(1, max(1, seeds) + 1)),
                )
                results.append(
                    {
                        "task": task.id,
                        "category": task.category.value,
                        "reliability": reliability.as_dict(),
                        "outcomes": [o.as_dict() for o in outcomes],
                    }
                )
                console.print(
                    f"  {task.id:<28} score={reliability.mean:.3f} "
                    f"worst={reliability.worst:.3f} pass={reliability.success_rate:.0%}"
                )
            overall = statistics.fmean(
                [r["reliability"]["mean"] for r in results]
            ) if results else 0.0
            console.print("")
            console.print(f"Overall quality: {overall:.3f} (threshold {threshold})")
            path = _write_json(
                f"quality-lab-{model.replace('/', '_').replace(':', '_')}.json",
                {"model": model, "overall": overall, "results": results},
            )
            console.print(f"Report saved: {path}")
        finally:
            try:
                await client.close()
            except Exception as exc:
                log_best_effort("best-effort operation failed", exc)
    import asyncio
    asyncio.run(_run())
async def _chat(
    client, model: str, prompt: str, max_tokens: int, reasoning: str = "off"
) -> str:
    # The reasoning value is passed through as-is (off/on/low/medium/high/
    # xhigh/default/...). "default" omits the key so the server uses its own
    # default. The client retries without the key when a model or server
    # rejects the value, so unknown levels degrade safely.
    reasoning_value = None if reasoning.strip().lower() in ("", "default") else reasoning
    response = await client.chat_completion(
        model=model,
        input_text=prompt,
        temperature=0.0,
        max_output_tokens=max_tokens,
        reasoning=reasoning_value,
    )
    choices = response.get("choices") or []
    if not choices:
        return ""
    return choices[0].get("message", {}).get("content", "") or ""
# --- P5 Recommender -------------------------------------------------------
@app.command("recall")
def recall_probe(
    model: str = typer.Argument(..., help="Model ID to probe"),
    ctx: int = typer.Option(8192, "--ctx", help="Context size to probe"),
    depth: float = typer.Option(0.5, "--depth", help="Needle depth (0-1)"),
    depth_set: str = typer.Option(None, "--depth-set", help="Comma-separated depths"),
    max_cost: float = typer.Option(900.0, "--max-cost", help="Max probe cost in seconds"),
):
    """Run a deterministic context-recall probe on one model (WP C2)."""
    import asyncio
    setup_logging()
    from lm_optimizer.services.recall_probe import (
        RecallProbeSpec, run_recall_probe, run_recall_probe_deep,
    )
    depths = None
    if depth_set:
        depths = tuple(float(d.strip()) for d in depth_set.split(","))
    async def _run():
        client = _client()
        try:
            await client.connect()
            if depths:
                result = await run_recall_probe_deep(
                    client, model, ctx,
                    depth_points=depths,
                    spec=RecallProbeSpec(target_tokens=ctx, max_probe_cost_s=max_cost),
                )
                console.print("recall_all_depths: " + str(result["recall_all_depths"]))
                console.print("worst_depth: " + str(result["worst_depth"]))
                for r in result["depth_results"]:
                    console.print(
                        "  depth=" + str(r["depth"]) + " status=" + str(r["status"]) +
                        " prompt_tokens=" + str(r["prompt_tokens"]) +
                        " answer=" + str(r["answer_raw"])[:60]
                    )
            else:
                spec = RecallProbeSpec(
                    target_tokens=ctx, depth=depth, max_probe_cost_s=max_cost,
                )
                result = await run_recall_probe(client, model, ctx, spec)
                console.print("status: " + str(result.status))
                console.print("prompt_tokens: " + str(result.prompt_tokens))
                console.print("truncated: " + str(result.truncated))
                console.print("answer: " + str(result.answer_raw)[:60])
                console.print("estimated_cost_s: " + f"{result.estimated_cost_s:.0f}")
                console.print("actual_cost_s: " + f"{result.actual_cost_s:.0f}")
        finally:
            await client.close()
    asyncio.run(_run())
@app.command("recommend")
def recommend(
    min_tps: float = typer.Option(5.0, "--min-tps"),
    min_context: int = typer.Option(8192, "--min-context"),
    vram_only: bool = typer.Option(False, "--vram-only"),
    use_case: str = typer.Option("general", "--use-case"),
    json_out: bool = typer.Option(False, "--json"),
):
    """Recommend models for THIS hardware (P5).
    The recommender never hardcodes a VRAM limit: it uses the detected
    fingerprint, the model FILE SIZE (not the parameter count) and treats
    local measurements as stronger evidence than community priors.
    """
    setup_logging()
    from lm_optimizer.services.recommender import (
        ModelRecommender,
        RecommenderRequest,
        UseCase,
    )
    hw = _detect_hardware_fingerprint()
    console.print(
        f"[dim]{hw.gpu_name} | {hw.vram_gb:.1f} GB VRAM | {hw.cpu_name} | "
        f"{hw.ram_gb:.0f} GB RAM ({hw.ram_channels} ch)[/dim]\n"
    )
    catalog = _default_catalog()
    rec = ModelRecommender(catalog=catalog)
    local = _load_local_measurements()
    for model_id, (tps, run_id, ctx) in local.items():
        rec.add_local_measurement(model_id, tps, run_ids=[run_id], context_length=ctx)
    if local:
        console.print(
            f"[dim]{len(local)} local measurement(s) attached "
            f"(local evidence outranks community priors)[/dim]\n"
        )
    try:
        use = UseCase(use_case)
    except ValueError:
        console.print(f"[red]Unknown use case: {use_case}[/red]")
        sys.exit(2)
    request = RecommenderRequest(
        hardware=hw,
        use_case=use,
        min_tps=min_tps,
        min_context=min_context,
        vram_only=vram_only,
    )
    results = rec.recommend(request)
    if json_out:
        console.print(rec.to_json(results))
        return
    table = Table(title=f"Recommended models (min {min_tps} tok/s, ctx {min_context})")
    table.add_column("Model")
    table.add_column("Fit")
    table.add_column("Est. tok/s")
    table.add_column("Why")
    for r in results:
        table.add_row(
            f"{r.entry.quant} {r.entry.total_params_b:.0f}B ({r.entry.file_size_gb:.1f} GB)",
            r.fit_class.value,
            f"{r.expected_tps:.1f}" if r.expected_tps else "-",
            r.reasons[0] if r.reasons else "",
        )
    console.print(table)
def _detect_hardware_fingerprint():
    """Detect the real hardware fingerprint (never hardcode a GPU).
    GPU bandwidth and RAM channel count are not always detectable; when a
    value is unknown the recommender falls back to a conservative estimate
    and the recommendation says so.
    """
    from lm_optimizer.services.host.hardware import hardware_detector
    from lm_optimizer.services.recommender import HardwareFingerprint
    try:
        info = hardware_detector.detect()
    except Exception:
        info = None
    gpu = None
    if info is not None and getattr(info, "gpus", None):
        gpu = max(info.gpus, key=lambda g: getattr(g, "vram_gb", 0) or 0)
    # Known bandwidths for common GPUs (GB/s) - used only when the driver
    # does not report it. Unknown GPUs keep 0.0, which disables the
    # bandwidth-based speed estimate (the fit class still works).
    known_bandwidth = {
        "3060": 192.0,
        "3050": 192.0,
        "4060": 272.0,
        "4070": 504.0,
        "4090": 1008.0,
        "5060": 448.0,
        "5070": 624.0,
        "5080": 960.0,
        "5090": 1792.0,
    }
    bandwidth = 0.0
    name = (getattr(gpu, "name", "") or "").lower()
    for key, value in known_bandwidth.items():
        if key in name:
            bandwidth = value
            break
    ram_channels = 0
    try:
        import psutil  # type: ignore
        channels = psutil.virtual_memory().total
        del channels
    except Exception:
        ram_channels = 0
    return HardwareFingerprint(
        gpu_name=getattr(gpu, "name", "") or "",
        vram_gb=float(getattr(gpu, "vram_gb", 0) or 0),
        gpu_bandwidth_gbps=bandwidth,
        gpu_tdp_w=float(getattr(gpu, "tdp_w", 0) or 0),
        cpu_name=getattr(info, "cpu_name", "") or "",
        physical_cores=int(getattr(info, "cpu_cores_physical", 0) or 0),
        logical_threads=int(getattr(info, "cpu_cores_logical", 0) or 0),
        ram_gb=float(getattr(info, "total_ram_gb", 0) or 0),
        ram_channels=ram_channels or 1,
        disk_type="",
        os_name=getattr(info, "os", "") or "",
    )
def _load_local_measurements() -> dict[str, tuple[float, str, int | None]]:
    """Latest measured median tok/s per model from the local database.
    Local measurements are the strongest evidence the recommender has
    (spec 16.4: "local results have priority over community priors"). The
    measurement context is returned too - 9 tok/s at 4096 tokens is NOT
    comparable with 9 tok/s at 16384.
    """
    import sqlite3
    from pathlib import Path
    db = Path("data/optimizer.db")
    if not db.exists():
        return {}
    out: dict[str, tuple[float, str, int | None]] = {}
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        runs = con.execute(
            "SELECT id, model_id, created_at FROM runs "
            "WHERE status IN ('completed_no_validated_winner','success','completed') "
            "ORDER BY created_at DESC"
        ).fetchall()
        seen: set[str] = set()
        for run in runs:
            model_id = run["model_id"]
            if model_id in seen:
                continue
            speeds: list[float] = []
            contexts: list[int] = []
            for cfg in con.execute(
                "SELECT metrics_json, context_length FROM configurations "
                "WHERE run_id=? AND status='passed'",
                (run["id"],),
            ):
                raw = cfg["metrics_json"]
                if raw:
                    try:
                        for t in json.loads(raw):
                            g = t.get("generation_tok_s")
                            if isinstance(g, (int, float)) and t.get("category") == "speed":
                                speeds.append(g)
                    except Exception:
                        continue
                if cfg["context_length"]:
                    contexts.append(int(cfg["context_length"]))
            if len(speeds) >= 4:
                ctx = max(contexts) if contexts else None
                out[model_id] = (statistics.median(speeds), run["id"], ctx)
                seen.add(model_id)
        con.close()
    except Exception as e:
        logger.debug("local measurement load failed", error=str(e))
    return out
def _default_catalog() -> list:
    """Curated catalog of candidates for this class of hardware."""
    from lm_optimizer.services.recommender import Confidence, ModelCatalogEntry
    def entry(**kw) -> dict[str, Any]:
        base = dict(
            repository="",
            filename="",
            architecture="qwen35",
            quant="",
            bits_per_weight=4.0,
            file_size_gb=0.0,
            total_params_b=0.0,
            max_context=262144,
            capabilities=["chat", "tools"],
            confidence=Confidence.C,
        )
        base.update(kw)
        return ModelCatalogEntry(**base)
    return [
        entry(repository="lmstudio-community", filename="bonsai-q1_0.gguf", quant="Q1_0",
              bits_per_weight=1.0, file_size_gb=4.4, total_params_b=27.0,
              model_id="prism-ml/bonsai-27b",
              capabilities=["chat", "tools", "vision"]),
        entry(repository="empero-ai", filename="qwen3.8-9b-q4_km.gguf", quant="Q4_K_M",
              bits_per_weight=4.0, file_size_gb=5.8, total_params_b=9.0,
              model_id="qwen3.8-9b-distill"),
        entry(repository="bartowski", filename="Qwen3.8-27B-IQ3_XS.gguf", quant="IQ3_XS",
              bits_per_weight=3.0, file_size_gb=12.8, total_params_b=27.0,
              model_id="swift-qwen3.8-27b",
              capabilities=["chat", "tools", "vision"]),
        entry(repository="bartowski", filename="Qwen3.8-27B-IQ4_XS.gguf", quant="IQ4_XS",
              bits_per_weight=4.0, file_size_gb=15.4, total_params_b=27.0,
              model_id="qwen3.8-27b-uncensored-hauhaucs-aggressive-mtp@iq4_xs",
              capabilities=["chat", "tools", "vision"]),
        entry(repository="openai", filename="gpt-oss-20b-mxfp4.gguf", quant="MXFP4",
              bits_per_weight=4.0, file_size_gb=12.1, total_params_b=21.0,
              active_params_b=3.6, max_context=131072,
              model_id="openai/gpt-oss-20b",
              capabilities=["chat", "tools", "reasoning"]),
        entry(repository="mradermacher", filename="gpt-oss-20b-heretic-q4_ks.gguf",
              quant="Q4_K_S", bits_per_weight=4.0, file_size_gb=14.7, total_params_b=21.0,
              active_params_b=3.6, max_context=131072,
              model_id="openai-gpt-oss-20b-claude-4.5-opus-heretic-uncensored-i1",
              capabilities=["chat", "tools", "reasoning"]),
        entry(repository="qwen", filename="qwen3-coder-30b-q4_km.gguf", quant="Q4_K_M",
              bits_per_weight=4.0, file_size_gb=18.6, total_params_b=30.5,
              active_params_b=3.3, architecture="qwen3moe",
              model_id="qwen/qwen3-coder-30b",
              capabilities=["chat", "tools"]),
        entry(repository="qwen", filename="qwen3.6-35b-a3b-q4_km.gguf", quant="Q4_K_M",
              bits_per_weight=4.0, file_size_gb=22.1, total_params_b=35.0,
              active_params_b=3.0, architecture="qwen35moe",
              model_id="qwen/qwen3.6-35b-a3b",
              capabilities=["chat", "tools"]),
    ]
# --- P4 Duel --------------------------------------------------------------
# --- P4 Duel --------------------------------------------------------------
def _resolve_duel_task_ids(duel_type: str, tasks: str | None) -> tuple[object, list[str]]:
    """Resolve the duel type and the task ids it will run."""
    from lm_optimizer.services.duel import DUEL_TASKS, DuelType

    try:
        dt = DuelType(duel_type)
    except ValueError:
        raise ValueError(
            f"Unknown duel type {duel_type!r}. "
            f"Available: {', '.join(t.value for t in DuelType)}"
        ) from None
    if tasks and tasks.strip().lower() not in ("all", "*"):
        task_ids = [t.strip() for t in tasks.split(",") if t.strip()]
    else:
        task_ids = list(DUEL_TASKS[dt])
    return dt, task_ids


def _run_duel_one(
    model_a: str,
    model_b: str,
    *,
    duel_type: str = "micro_quality",
    mode: str = "controlled",
    blind: bool = True,
    context_length: int = 16384,
    tasks: str | None = None,
    custom_prompt: str | None = None,
) -> dict:
    """Measure both sides on the same task set and return the duel payload."""
    from dataclasses import replace as _replace

    from lm_optimizer.services.duel import (
        DuelMode,
        DuelSide,
        compute_verdict,
    )
    from lm_optimizer.services.quality_lab import default_tasks, run_task

    dt, task_ids = _resolve_duel_task_ids(duel_type, tasks)
    try:
        dm = DuelMode(mode)
    except ValueError:
        raise ValueError(
            f"Unknown duel mode {mode!r}. Available: "
            f"{', '.join(m.value for m in DuelMode)}"
        ) from None

    side_a = DuelSide(model_id=model_a, context_length=context_length)
    side_b = DuelSide(model_id=model_b, context_length=context_length)
    all_tasks = {t.id: t for t in default_tasks()}
    if custom_prompt:
        all_tasks = {
            task_id: _replace(task, prompt=custom_prompt)
            for task_id, task in all_tasks.items()
        }

    import asyncio

    async def _measure() -> dict[str, dict]:
        from lm_optimizer.domain.models import LoadConfiguration
        from lm_optimizer.services.benchmark import BenchmarkService

        client = _client()
        results: dict[str, dict] = {}
        try:
            await client.connect()
            svc = BenchmarkService(client)
            for side in (side_a, side_b):
                cfg = LoadConfiguration(
                    context_length=context_length,
                    flash_attention=True,
                    offload_kv_cache_to_gpu=True,
                    eval_batch_size=2048,
                )
                ok, _i, _l, _ch, _ap, err = await svc._channel_load(side.model_id, cfg)
                if not ok:
                    console.print(f"[red]Load failed for {side.model_id}: {err}[/red]")
                    for task_id in task_ids:
                        side.outcomes[task_id] = {
                            "score": 0.0,
                            "error": f"load failed: {err}"[:200],
                            "gate_passed": False,
                            "critical_failure": "load_failed",
                        }
                    results[side.model_id] = side.outcomes
                    continue
                for task_id in task_ids:
                    task = all_tasks.get(task_id)
                    if task is None:
                        side.outcomes[task_id] = {
                            "score": 0.0,
                            "error": f"unknown task {task_id}",
                            "gate_passed": False,
                        }
                        continue
                    outcome = await run_task(
                        task,
                        lambda prompt, max_tokens, _m=side.model_id: _chat(
                            client, _m, prompt, max_tokens
                        ),
                    )
                    side.outcomes[task_id] = {
                        "score": outcome.score,
                        "tokens_per_second": 0.0,
                        "tokens": 0,
                        "gate_passed": outcome.gate_passed,
                        "output": outcome.output,
                        "error": outcome.error,
                        "critical_failure": (
                            "quality_failed"
                            if not outcome.passed and not outcome.error
                            else ""
                        ),
                    }
                    console.print(
                        f"  {side.model_id[:34]:34s} {task_id:<26s} "
                        f"score={outcome.score:.2f}"
                    )
                results[side.model_id] = side.outcomes
                # The host must be clean before the NEXT side is loaded
                # (only one model fits into the VRAM at a time).
                try:
                    await svc.ensure_unloaded(side.model_id)
                except Exception as exc:
                    log_best_effort("best-effort operation failed", exc)
        finally:
            try:
                await client.close()
            except Exception as exc:
                log_best_effort("best-effort operation failed", exc)
        return results

    asyncio.run(_measure())

    verdict = compute_verdict(side_a, side_b, task_ids)
    return {
        "duel_type": dt.value,
        "mode": dm.value,
        "tasks": task_ids,
        "side_a": side_a.as_dict(),
        "side_b": side_b.as_dict(),
        "verdict": verdict.as_dict(),
    }


@app.command("duel")
def duel(
    model_a: str = typer.Argument(...),
    model_b: str = typer.Argument(...),
    duel_type: str = typer.Option("micro_quality", "--type"),
    mode: str = typer.Option("controlled", "--mode"),
    blind: bool = typer.Option(True, "--blind/--no-blind"),
    context_length: int = typer.Option(16384, "--context"),
    seeds: int = typer.Option(1, "--seeds"),
    tasks: str | None = typer.Option(
        None, "--tasks", help="Comma-separated task ids (default: the type's set)"
    ),
    custom_prompt: str | None = typer.Option(
        None, "--custom-prompt", help="Override every task prompt (default: task prompt)"
    ),
):
    """Duel two models on the same tasks (P4).

    Controlled mode uses identical context, sampling and seed for both
    sides; the judge (if any) sees anonymized Candidate A/B only.
    """
    setup_logging()
    try:
        payload = _run_duel_one(
            model_a,
            model_b,
            duel_type=duel_type,
            mode=mode,
            blind=blind,
            context_length=context_length,
            tasks=tasks,
            custom_prompt=custom_prompt,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(2)
    console.print(json.dumps(payload["verdict"], indent=2, ensure_ascii=False))
    path = _write_json(
        f"duel-{model_a.replace('/', '_')}-{model_b.replace('/', '_')}.json", payload
    )
    console.print(f"\nReport saved: {path}")


@app.command("duel-matrix")
def duel_matrix(
    models: str = typer.Option(
        ..., "--models", help="Comma-separated ids or a glob; every pair is dueled"
    ),
    tasks: str | None = typer.Option(
        None, "--tasks", help="Comma-separated task ids (default: the duel type's set)"
    ),
    duel_type: str = typer.Option("micro_quality", "--type"),
    mode: str = typer.Option("controlled", "--mode"),
    blind: bool = typer.Option(True, "--blind/--no-blind"),
    context_length: int = typer.Option(16384, "--context"),
    custom_prompt: str | None = typer.Option(
        None, "--custom-prompt", help="Override every task prompt"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print the planned pairs without running them"
    ),
):
    """Duel every pair of the selected models on the selected tasks.

    Examples:
      lab duel-matrix --models a,b --tasks company_website
      lab duel-matrix --models qwen/* --type complete_sandbox
      lab duel-matrix --models a,b,c --custom-prompt "Explain X"
    """
    setup_logging()
    import itertools

    try:
        _dt, task_ids = _resolve_duel_task_ids(duel_type, tasks)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(2)

    model_ids = _resolve_models(models)
    if len(model_ids) < 2:
        console.print("[red]duel-matrix needs at least two models.[/red]")
        sys.exit(2)

    pairs = list(itertools.combinations(model_ids, 2))
    console.print(
        f"[bold]Duel matrix:[/bold] {len(model_ids)} model(s) -> "
        f"{len(pairs)} pair(s) x {len(task_ids)} task(s)"
    )
    console.print("Models: " + ", ".join(model_ids))
    console.print("Tasks:  " + ", ".join(task_ids))
    for a, b in pairs:
        console.print(f"  [dim]pair[/dim] {a} vs {b}")
    if custom_prompt:
        console.print("[yellow]custom prompt override active[/yellow]")

    if dry_run:
        console.print("[green]Dry run: nothing executed.[/green]")
        return

    summary_path = Path("results") / "duel_matrix.jsonl"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    from datetime import datetime

    wins_a = 0
    wins_b = 0
    draws = 0
    failures = 0
    try:
        for index, (model_a, model_b) in enumerate(pairs, 1):
            console.print(
                f"\n[bold]=== [{index}/{len(pairs)}] {model_a} vs {model_b} ===[/bold]"
            )
            entry: dict = {
                "model_a": model_a,
                "model_b": model_b,
                "duel_type": duel_type,
                "tasks": task_ids,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            }
            try:
                payload = _run_duel_one(
                    model_a,
                    model_b,
                    duel_type=duel_type,
                    mode=mode,
                    blind=blind,
                    context_length=context_length,
                    tasks=",".join(task_ids),
                    custom_prompt=custom_prompt,
                )
                verdict = payload.get("verdict") or {}
                winner = verdict.get("winner") or "draw"
                entry["winner"] = winner
                entry["verdict"] = verdict
                if winner == model_a:
                    wins_a += 1
                elif winner == model_b:
                    wins_b += 1
                else:
                    draws += 1
                console.print(f"[dim]winner: {winner}[/dim]")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                entry["error"] = str(exc)[:300]
                console.print(f"[red]pair failed: {exc}[/red]")
            with summary_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted; partial results kept.[/yellow]")
    console.print(
        f"\n[bold]Duel matrix finished: {wins_a} A-wins, {wins_b} B-wins, "
        f"{draws} draws, {failures} failures.[/bold] Summary: {summary_path}"
    )


# --- P4 Sandbox -----------------------------------------------------------
MIN_SANDBOX_CONTEXT = 4096


def _available_model_ids() -> list[str]:
    """Chat-capable model ids reported by LM Studio (excludes embeddings)."""
    import asyncio

    async def _list() -> list[str]:
        client = _client()
        try:
            await client.connect(echo_probe=False)
            models = await client.list_models()
            out: list[str] = []
            for model in models:
                if (model.model_type or "llm").lower() != "llm":
                    continue
                out.append(model.id)
            return out
        finally:
            try:
                await client.close()
            except Exception as exc:
                log_best_effort("best-effort operation failed", exc)

    try:
        return asyncio.run(_list())
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Cannot list models from LM Studio: {exc}[/red]")
        return []


def _resolve_models(spec: str) -> list[str]:
    """Resolve a model selector.

    Accepts ``all`` (every chat model LM Studio reports), a comma-separated
    list of ids, or a glob such as ``qwen/*``.
    """
    raw = (spec or "all").strip()
    if raw.lower() in ("all", "*"):
        return _available_model_ids()
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) == 1 and any(ch in parts[0] for ch in "*?["):
        import fnmatch

        available = _available_model_ids()
        matched = fnmatch.filter(available, parts[0])
        return matched
    return parts


def _resolve_tasks(spec: str | None, available: list[str]) -> list[str]:
    """Resolve a task selector against the known task ids."""
    raw = (spec or "all").strip()
    if raw.lower() in ("all", "*"):
        return sorted(available)
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) == 1 and any(ch in parts[0] for ch in "*?["):
        import fnmatch

        return fnmatch.filter(sorted(available), parts[0])
    return parts


def _load_prompt_overrides(path: Path | None) -> dict[str, str]:
    """Load a JSON map of task_id -> custom prompt (optional)."""
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read prompt file {path}: {exc}") from None
    if not isinstance(data, dict):
        raise ValueError("Prompt file must be a JSON object {task_id: prompt}")
    return {str(key): str(value) for key, value in data.items()}


def _stamp_model_into_artifacts(
    task: SandboxTask, workdir: Path, model: str
) -> None:
    """Stamp the model that generated the artifact into the primary file.

    Web tasks get an HTML comment, Python tasks a Python comment. Kept
    best-effort: a missing or unreadable artifact never fails the run.
    """

    if task.kind.value not in ("web", "blender"):
        return
    artifacts = task.artifacts or ("output.txt",)
    primary = artifacts[0]
    if primary.endswith("/"):
        primary = primary.rstrip("/") + "/output.txt"
    path = workdir / primary
    if not path.exists() or not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log_best_effort("best-effort operation failed", exc)
        return
    marker = f"Generated by model: {model}"
    if task.kind.value == "web":
        comment = f"<!-- {marker} -->\n"
        if comment.strip() in text:
            return
        if text.lstrip().startswith("<!DOCTYPE"):
            text = text.replace("<!DOCTYPE", comment + "<!DOCTYPE", 1)
        elif text.lstrip().startswith("<html"):
            text = text.replace("<html", comment + "<html", 1, 1)
        else:
            text = comment + text
    else:
        comment = f"# {marker}\n"
        if comment.strip() in text:
            return
        text = comment + text
    try:
        path.write_text(text, encoding="utf-8", errors="replace")
    except OSError as exc:
        log_best_effort("best-effort operation failed", exc)


def _run_sandbox_one(
    task_id: str,
    model: str,
    *,
    custom_prompt: str | None = None,
    context_length: int | None = None,
    reasoning: str = "off",
    origin: str = "local",
    kv_quant: str | None = None,
    threads: str | int | None = None,
) -> dict:
    """Execute one sandbox task for one model and return the result dict."""
    from dataclasses import replace as _replace

    from lm_optimizer.services.lmstudio_defaults import read_load_defaults
    from lm_optimizer.services.sandbox_lab import SANDBOX_TASKS, SandboxPolicy
    from lm_optimizer.services.sandbox_runner import SandboxRunner, build_command_for

    declared = read_load_defaults(model) if model else {}
    kv_quant = kv_quant or declared.get("kv_quant")
    threads = threads if threads not in (None, "") else declared.get("threads")

    definition = SANDBOX_TASKS.get(task_id)
    if definition is None:
        raise ValueError(
            f"Unknown sandbox task {task_id!r}. "
            f"Available: {', '.join(sorted(SANDBOX_TASKS))}"
        )
    if custom_prompt:
        definition = _replace(definition, prompt=custom_prompt)

    from datetime import datetime

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_slug = (model or "none").replace("/", "_").replace(":", "_").replace(" ", "_")
    base_dir = Path("results") / "sandbox" / task_id
    workdir = base_dir / f"{stamp}_{model_slug}"
    policy = SandboxPolicy(
        workdir=workdir,
        network_enabled=False,
        timeout_s=definition.timeout_s,
        allowed_executables=definition.allowed_executables,
    )
    runner = SandboxRunner(
        task=definition,
        policy=policy,
        workdir=workdir,
        command=build_command_for(definition),
        model=model,
    )
    from dataclasses import replace as _replace_cfg

    from lm_optimizer.cli.sandbox_duel import _load_best_config
    from lm_optimizer.domain.models import LoadConfiguration
    from lm_optimizer.services.model_gate import ModelGate, ModelGateTimeout
    from lm_optimizer.services.sandbox_history import settings_from_reasoning
    from lm_optimizer.services.sandbox_lab import SandboxResult

    run_meta: dict = {}

    async def _run_with_gate():
        client = _client()
        await client.connect(echo_probe=False)
        try:
            effective = context_length or MIN_SANDBOX_CONTEXT
            try:
                cfg, ctx = _load_best_config(model)
                effective = context_length or max(MIN_SANDBOX_CONTEXT, ctx or 0)
                if ctx is not None and ctx < effective:
                    cfg = _replace_cfg(cfg, context_length=effective)
                    console.print(
                        f"[yellow]context_length raised from {ctx} to "
                        f"{effective} for sandbox run[/yellow]"
                    )
            except ValueError:
                cfg = LoadConfiguration(context_length=effective)
            run_meta["settings"] = settings_from_reasoning(
                reasoning,
                context_length=int(effective),
                max_output_tokens=definition.max_output_tokens,
                kv_quant=kv_quant,
                threads=threads,
            )

            gate = ModelGate(client)
            try:
                lease = await gate.acquire(model, cfg)
            except ModelGateTimeout as exc:
                console.print(f"[red]model gate: {exc}[/red]")
                failed = SandboxResult(task_id=task_id)
                failed.error = f"model gate: {exc}"[:200]
                return failed

            async def _generate(feedback: str) -> str:
                prompt = definition.prompt
                if feedback:
                    prompt = feedback + "\n\n" + definition.prompt
                return await _chat(
                    client,
                    lease.model,
                    prompt,
                    definition.max_output_tokens,
                    reasoning=reasoning,
                )

            try:
                return await runner.run_async(_generate)
            finally:
                await gate.release(lease)
        finally:
            try:
                await client.close()
            except Exception as exc:
                log_best_effort("best-effort operation failed", exc)

    import asyncio

    if model:
        result = asyncio.run(_run_with_gate())
    else:
        result = asyncio.run(runner.run_async(lambda feedback: ""))
    # Artifact retention: keep the newest N runs per task (spec §13.5).
    from lm_optimizer.services.sandbox_runner import apply_retention

    removed = apply_retention(base_dir, policy)
    if removed:
        console.print(f"[dim]retention: pruned {len(removed)} old sandbox run(s)[/dim]")
    from lm_optimizer.services.sandbox_history import record_run

    payload = result.as_dict()
    record_run(
        model or "(none)",
        task_id,
        payload,
        workdir=str(workdir),
        duration_s=sum(a.duration_s for a in result.attempts),
        prompt=definition.prompt,
        settings=run_meta.get("settings"),
        origin=origin,
    )
    payload["workdir"] = str(workdir)
    # Stamp every generated web / blender artifact with the model that made it,
    # so the sandbox output is self-documenting.
    if model:
        from lm_optimizer.services.sandbox_lab import SANDBOX_TASKS

        task_def = SANDBOX_TASKS.get(task_id)
        if task_def is not None:
            _stamp_model_into_artifacts(task_def, workdir, model)
    return payload


@app.command("sandbox")
def sandbox(
    task: str = typer.Option("company_website", "--task", help="Sandbox task id"),
    model: str = typer.Option("", "--model", help="Model that produces the solution"),
    custom_prompt: str | None = typer.Option(
        None, "--custom-prompt", help="Override the task prompt (default: task prompt)"
    ),
    scene: str | None = typer.Option(
        None,
        "--scene",
        help="Scene variation for minecraft_world, e.g. 'fewer trees, a lighthouse'",
    ),
    context_length: int | None = typer.Option(
        None, "--context", help="Force context length (default: best config, min 4096)"
    ),
    reasoning: str = typer.Option(
        "off",
        "--reasoning",
        help="Reasoning level: off|on|low|medium|high|xhigh|default (unknown values fall back)",
    ),
    origin: str = typer.Option(
        "local",
        "--origin",
        help="local (this hardware) or frontier (an API provider)",
    ),
    kv_quant: str = typer.Option(
        "",
        "--kv-quant",
        help="KV-cache quantization you set in LM Studio (q4|q5|q8|f16). Label only.",
    ),
    threads: str = typer.Option(
        "",
        "--threads",
        help="CPU threads you set in LM Studio (max or a number). Label only.",
    ),
):
    """Run one sandbox task with the repair loop (P4).

    The model writes into an isolated workdir; the acceptance criteria are
    checked automatically; on failure the model receives the EVIDENCE (not
    the solution) and the remaining repair budget.
    """
    setup_logging()
    if scene and not custom_prompt:
        if task != "minecraft_world":
            console.print("[red]--scene only applies to --task minecraft_world[/red]")
            sys.exit(2)
        from lm_optimizer.services.sandbox_lab import build_minecraft_prompt

        custom_prompt = build_minecraft_prompt(scene)
    try:
        payload = _run_sandbox_one(
            task,
            model,
            custom_prompt=custom_prompt,
            context_length=context_length,
            reasoning=reasoning,
            origin=origin,
            kv_quant=kv_quant or None,
            threads=threads or None,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(2)
    console.print(json.dumps(payload, indent=2, ensure_ascii=False))
    clean = {k: v for k, v in payload.items() if k != "workdir"}
    path = _write_json(f"sandbox-{task}.json", clean)
    console.print(f"\nReport saved: {path}")


@app.command("prune-runs")
def prune_runs(
    apply: bool = typer.Option(
        False, "--apply", help="Rewrite the JSONL files and delete artifact dirs"
    ),
    sandbox: bool = typer.Option(
        True, "--sandbox/--no-sandbox", help="Prune results/sandbox_runs.jsonl"
    ),
    bakeoff: bool = typer.Option(
        True, "--bakeoff/--no-bakeoff", help="Prune results/bakeoff/runs.jsonl"
    ),
):
    """Collapse duplicate run history (same model + task + prompt + settings).

    Dry run by default: prints what would be dropped per model/task and keeps
    every file untouched. ``--apply`` rewrites the history and removes the
    artifact dirs of the dropped rows.
    """
    from pathlib import Path as _Path

    from lm_optimizer.services.sandbox_history import prune_history

    paths = []
    if sandbox:
        paths.append(_Path("results") / "sandbox_runs.jsonl")
    if bakeoff:
        paths.append(_Path("results") / "bakeoff" / "runs.jsonl")
    if not paths:
        console.print("[yellow]nothing selected[/yellow]")
        raise typer.Exit(1)
    for path in paths:
        report = prune_history(path, apply=apply)
        console.print(
            f"[bold]{path}[/bold]: {report['before']} -> {report['after']} rows, "
            f"{report['removed']} duplicate(s), "
            f"{report['directories_removed']} dir(s) deleted"
        )
        for group in report["groups"][:40]:
            console.print(
                f"  {group['model']} · {group['task']} · "
                f"{group['run_key'] or 'legacy'} · kept {group['kept_ts'] or '-'} · "
                f"dropped {group['dropped']}"
            )
        if len(report["groups"]) > 40:
            console.print(f"  ... {len(report['groups']) - 40} more group(s)")
    if not apply:
        console.print("[dim]dry run — rerun with --apply to write[/dim]")


@app.command("mark-origin")
def mark_origin(
    model: str = typer.Option(..., "--model", help="Model id (or substring) to re-label"),
    origin: str = typer.Option(
        "frontier", "--origin", help="local or frontier (API provider, not this hardware)"
    ),
    apply: bool = typer.Option(False, "--apply", help="Rewrite the history files"),
    sandbox: bool = typer.Option(
        True, "--sandbox/--no-sandbox", help="results/sandbox_runs.jsonl"
    ),
    bakeoff: bool = typer.Option(
        True, "--bakeoff/--no-bakeoff", help="results/bakeoff/runs.jsonl"
    ),
):
    """Re-label existing runs as local or frontier.

    Rows written before the field existed default to local. Use this to move an
    API-provider run (DeepSeek, Gemini, ChatGPT, ...) out of the local table.
    """
    from pathlib import Path as _Path

    from lm_optimizer.services.sandbox_history import mark_origin as _mark_origin

    paths = []
    if sandbox:
        paths.append(_Path("results") / "sandbox_runs.jsonl")
    if bakeoff:
        paths.append(_Path("results") / "bakeoff" / "runs.jsonl")
    total_changed = 0
    for path in paths:
        report = _mark_origin(path, model_match=model, origin=origin, apply=apply)
        total_changed += report["changed"]
        models = ", ".join(report["models"]) or "no match"
        console.print(
            f"[bold]{path}[/bold]: {report['matched']} row(s) match, "
            f"{report['changed']} would change -> {report['origin']} ({models})"
        )
    if not apply:
        console.print(
            f"[dim]dry run — {total_changed} row(s) would change; "
            "rerun with --apply to write[/dim]"
        )
    else:
        console.print(f"[green]{total_changed} row(s) re-labelled[/green]")


@app.command("debug")
def debug_sandbox(
    run: str | None = typer.Option(
        None, "--run", help="Sandbox workdir (or debug.json path); latest when omitted"
    ),
    task: str = typer.Option(
        "minecraft_world", "--task", help="Task id used to find the latest run"
    ),
):
    """Explain why a sandbox run failed: per-attempt errors and raw command output."""
    import json as _json
    from pathlib import Path as _Path

    if run:
        path = _Path(run)
    else:
        task_dir = _Path("results") / "sandbox" / task
        candidates = sorted(
            task_dir.glob("*/debug.json"),
            key=lambda p: p.stat().st_mtime,
        )
        if not candidates:
            console.print(f"[red]No debug.json under {task_dir}[/red]")
            sys.exit(2)
        path = candidates[-1]
    if path.is_dir():
        path = path / "debug.json"
    if not path.exists():
        console.print(f"[red]Not found: {path}[/red]")
        sys.exit(2)

    data = _json.loads(path.read_text(encoding="utf-8"))
    console.print(
        f"[bold]task[/bold]: {data.get('task')}  "
        f"[bold]model[/bold]: {data.get('model')}"
    )
    console.print(f"[bold]command[/bold]: {data.get('command')}")
    for attempt in data.get("attempts", []):
        console.print(
            f"\n[bold]attempt {attempt.get('attempt')}[/bold] "
            f"score={attempt.get('score')} passed={attempt.get('passed')} "
            f"gen={attempt.get('generate_s')}s exit={attempt.get('exit_code')}"
        )
        if attempt.get("error"):
            console.print(f"  [red]error: {attempt['error']}[/red]")
        if attempt.get("failing"):
            console.print(f"  failing: {'; '.join(attempt['failing'])}")
        if attempt.get("critical"):
            console.print(
                f"  [red]critical: {'; '.join(attempt['critical'])}[/red]"
            )
        if attempt.get("exec_error"):
            console.print(f"  exec_error: {attempt['exec_error'][:400]}")
        if attempt.get("stderr_tail"):
            console.print(f"  stderr: {attempt['stderr_tail'][-600:]}")
    final = data.get("final", {})
    console.print(
        f"\n[bold]final[/bold] score={final.get('final_score')} "
        f"success={final.get('final_success')} error={final.get('error')}"
    )


@app.command("run-debug")
def run_debug(
    run_id: str | None = typer.Argument(
        None, help="Optimization run id; omit to list recent failed runs"
    ),
    limit: int = typer.Option(10, "--limit", help="How many recent runs to scan"),
):
    """Explain why optimizer run(s) failed: config and per-test errors."""
    from lm_optimizer.database.repositories import run_repo

    if not run_id:
        runs = run_repo.list_all(limit=max(1, limit))
        failed = [
            run
            for run in runs
            if getattr(run.status, "value", str(run.status)).lower()
            in ("failed", "partial_success")
        ]
        if not failed:
            console.print("[green]No failed optimizer runs found[/green]")
            return
        console.print("[bold]Recent failed optimizer runs[/bold]")
        for run in failed:
            console.print(
                f"  {run.id}  {getattr(run.model, 'id', '?')}  "
                f"{getattr(run.status, 'value', run.status)}  "
                f"error={run.error or '-'}"
            )
        console.print(
            "\nRun `lab run-debug <run_id>` for per-config and per-test details."
        )
        return

    run = run_repo.get(run_id)
    if run is None:
        console.print(f"[red]Run not found: {run_id}[/red]")
        sys.exit(2)
    console.print(
        f"[bold]run[/bold]: {run.id}  [bold]model[/bold]: "
        f"{getattr(run.model, 'id', '?')}  [bold]status[/bold]: "
        f"{getattr(run.status, 'value', run.status)}"
    )
    console.print(
        f"[bold]profile[/bold]: {getattr(run.profile, 'value', run.profile)}  "
        f"[bold]stage[/bold]: {getattr(run.stage, 'value', run.stage)}  "
        f"[bold]error[/bold]: {run.error or '-'}"
    )
    if not run.configurations:
        console.print("[yellow]No configurations recorded[/yellow]")
        return
    for config in run.configurations:
        metrics = getattr(config, "metrics", None) or []
        failed_tests = [
            m for m in metrics if not getattr(m, "success", False)
        ]
        console.print(
            f"\n[bold]config[/bold] ctx={config.context_length} "
            f"status={getattr(config.status, 'value', config.status)} "
            f"score={config.score} tok/s={config.get_avg_generation_tok_s():.2f} "
            f"error={config.error or '-'}"
        )
        for metric in failed_tests:
            console.print(
                f"  [red]test {getattr(metric, 'test_name', '?')} failed: "
                f"{getattr(metric, 'error', '') or '-'}[/red]"
            )


@app.command("sandbox-all")
def sandbox_all(
    model: str = typer.Option(..., "--model", help="Model that produces the solutions"),
    tasks: str | None = typer.Option(
        None, "--tasks", help="Comma-separated task ids or 'all' (default: all)"
    ),
    custom_prompt: str | None = typer.Option(
        None, "--custom-prompt", help="Override every task prompt"
    ),
    prompts_file: Path | None = typer.Option(
        None, "--prompts-file", help="JSON map {task_id: prompt} for per-task overrides"
    ),
    context_length: int | None = typer.Option(
        None, "--context", help="Force context length for every run"
    ),
    reasoning: str = typer.Option(
        "off",
        "--reasoning",
        help="Reasoning level: off|on|low|medium|high|xhigh|default",
    ),
):
    """Run every sandbox task (or a subset) for one model.

    Loads the model once per task with its best validated config and records
    each result in results/sandbox_runs.jsonl for the web UI.
    """
    setup_logging()
    from lm_optimizer.services.sandbox_lab import SANDBOX_TASKS

    task_ids = _resolve_tasks(tasks, list(SANDBOX_TASKS))
    unknown = [t for t in task_ids if t not in SANDBOX_TASKS]
    if unknown:
        console.print(f"[red]Unknown sandbox task(s): {', '.join(unknown)}[/red]")
        console.print("Available: " + ", ".join(sorted(SANDBOX_TASKS)))
        sys.exit(2)
    try:
        overrides = _load_prompt_overrides(prompts_file)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(2)
    total = len(task_ids)
    ok = 0
    failed = 0
    console.print(f"Running {total} sandbox task(s) for {model}")
    for index, task_id in enumerate(task_ids, 1):
        console.print(f"\n[bold]=== [{index}/{total}] {task_id} ===[/bold]")
        try:
            payload = _run_sandbox_one(
                task_id,
                model,
                custom_prompt=custom_prompt or overrides.get(task_id),
                context_length=context_length,
                reasoning=reasoning,
            )
        except Exception as exc:  # noqa: BLE001
            failed += 1
            console.print(f"[red]{task_id} failed: {exc}[/red]")
            continue
        if payload.get("final_success"):
            ok += 1
        else:
            failed += 1
        console.print(
            f"[dim]score={payload.get('final_score')} "
            f"passed={payload.get('final_success')}[/dim]"
        )
    console.print(
        f"\n[bold]{total} task(s) finished: {ok} passed, {failed} failed.[/bold]"
    )


@app.command("sandbox-matrix")
def sandbox_matrix(
    models: str = typer.Option(
        "all", "--models", help="'all', comma-separated ids, or a glob (qwen/*)"
    ),
    tasks: str = typer.Option(
        "all", "--tasks", help="'all', comma-separated task ids, or a glob"
    ),
    custom_prompt: str | None = typer.Option(
        None, "--custom-prompt", help="Override the prompt for every run"
    ),
    prompts_file: Path | None = typer.Option(
        None, "--prompts-file", help="JSON map {task_id: prompt} for per-task overrides"
    ),
    context_length: int | None = typer.Option(
        None, "--context", help="Force context length for every run"
    ),
    reasoning: str = typer.Option(
        "off",
        "--reasoning",
        help="Reasoning level: off|on|low|medium|high|xhigh|default",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print the matrix without running anything"
    ),
):
    """Run a model x task sandbox matrix (the flexible sweep).

    Examples:
      lab sandbox-matrix --models all --tasks all
      lab sandbox-matrix --models qwen/* --tasks company_website,email_write
      lab sandbox-matrix --models a,b --tasks all --custom-prompt "Explain X"
      lab sandbox-matrix --models all --tasks all --prompts-file prompts.json
    """
    setup_logging()
    from lm_optimizer.services.sandbox_lab import SANDBOX_TASKS

    model_ids = _resolve_models(models)
    if not model_ids:
        console.print("[red]No models matched.[/red]")
        sys.exit(2)
    task_ids = _resolve_tasks(tasks, list(SANDBOX_TASKS))
    unknown = [t for t in task_ids if t not in SANDBOX_TASKS]
    if unknown:
        console.print(f"[red]Unknown sandbox task(s): {', '.join(unknown)}[/red]")
        console.print("Available: " + ", ".join(sorted(SANDBOX_TASKS)))
        sys.exit(2)
    try:
        overrides = _load_prompt_overrides(prompts_file)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(2)

    total = len(model_ids) * len(task_ids)
    console.print(
        f"[bold]Sandbox matrix:[/bold] {len(model_ids)} model(s) x "
        f"{len(task_ids)} task(s) = {total} run(s)"
    )
    console.print("Models: " + ", ".join(model_ids))
    console.print("Tasks:  " + ", ".join(task_ids))
    if custom_prompt:
        console.print("[yellow]custom prompt override active[/yellow]")
    if overrides:
        console.print(f"[yellow]{len(overrides)} per-task prompt override(s)[/yellow]")

    if dry_run:
        for model_id in model_ids:
            for task_id in task_ids:
                console.print(f"  [dim]would run[/dim] {model_id} x {task_id}")
        console.print("[green]Dry run: nothing executed.[/green]")
        return

    summary_path = Path("results") / "sandbox_matrix.jsonl"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    from datetime import datetime

    ok = 0
    failed = 0
    index = 0
    try:
        for model_id in model_ids:
            console.print(f"\n[bold cyan]=== MODEL: {model_id} ===[/bold cyan]")
            for task_id in task_ids:
                index += 1
                console.print(
                    f"\n[bold]=== [{index}/{total}] {model_id} x {task_id} ===[/bold]"
                )
                entry: dict = {
                    "model": model_id,
                    "task": task_id,
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                }
                try:
                    payload = _run_sandbox_one(
                        task_id,
                        model_id,
                        custom_prompt=custom_prompt or overrides.get(task_id),
                        context_length=context_length,
                        reasoning=reasoning,
                    )
                    entry.update(
                        {
                            "ok": bool(payload.get("final_success")),
                            "score": payload.get("final_score"),
                            "repairs": payload.get("repair_count"),
                            "workdir": payload.get("workdir"),
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    entry.update({"ok": False, "error": str(exc)[:300]})
                with summary_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
                if entry.get("ok"):
                    ok += 1
                else:
                    failed += 1
                console.print(
                    f"[dim]score={entry.get('score')} ok={entry.get('ok')}[/dim]"
                )
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted; partial results kept.[/yellow]")
    console.print(
        f"\n[bold]Matrix finished: {ok} passed, {failed} failed "
        f"(of {total}). Summary: {summary_path}[/bold]"
    )


@app.command("bakeoff")
def bakeoff(
    models: str = typer.Option(
        "all",
        "--models",
        help="'all' (models from the configured backend), comma-separated ids or aliases",
    ),
    tasks: str = typer.Option(
        "email_write,company_website,minecraft_world",
        "--tasks",
        help="Comma-separated sandbox task ids",
    ),
    context: int = typer.Option(4096, "--context", help="Fixed context for every model"),
    thinking: bool = typer.Option(
        True, "--thinking/--no-thinking", help="Request reasoning where supported"
    ),
    reasoning_effort: str = typer.Option(
        "default",
        "--reasoning-effort",
        help="off|on|low|medium|high|xhigh|default or any server value",
    ),
    kv_ram: bool = typer.Option(
        False, "--kv-ram", help="Keep the KV cache in system RAM"
    ),
    safe: bool = typer.Option(
        False,
        "--safe",
        help="Minimal memory config: parallel 1, batch 128, KV cache in RAM",
    ),
    out: str = typer.Option("results/bakeoff", "--out", help="Output directory"),
    origin: str = typer.Option(
        "local",
        "--origin",
        help="local (this hardware) or frontier (an API provider)",
    ),
    kv_quant: str = typer.Option(
        "",
        "--kv-quant",
        help="KV-cache quantization you set in LM Studio (q4|q5|q8|f16). Label only.",
    ),
    threads: str = typer.Option(
        "",
        "--threads",
        help="CPU threads you set in LM Studio (max or a number). Label only.",
    ),
):
    """Benchmark any backend model on sandbox tasks (load vs generation + score).

    Works with any LM Studio or Ollama model id. ``--models all`` lists the
    models currently available from the configured backend, so nothing is
    hardcoded to this machine's test set.
    """
    import asyncio

    from lm_optimizer.services.bakeoff import _resolve_models, run_bakeoff

    setup_logging()
    try:
        model_ids = _resolve_models(models)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(2)
    task_ids = [t.strip() for t in tasks.split(",") if t.strip()]
    console.print(
        f"[bold]Bake-off[/bold]: {len(model_ids)} model(s) x "
        f"{len(task_ids)} task(s), ctx={context}, safe={safe}, kv_ram={kv_ram}"
    )
    code = asyncio.run(
        run_bakeoff(
            model_ids,
            task_ids,
            thinking=thinking,
            context=context,
            out=out,
            reasoning_effort=reasoning_effort,
            kv_ram=kv_ram,
            safe=safe,
            origin=origin,
            kv_quant=kv_quant or None,
            threads=threads or None,
        )
    )
    if code != 0:
        sys.exit(code)


@app.command("score-report")
def score_report(
    file: Path = typer.Argument(..., help="Report file (HTML for deep_research_report)"),
    task: str = typer.Option(
        "deep_research_report", "--task", help="Sandbox task id to score against"
    ),
    model: str = typer.Option(
        "external", "--model", help="Provider/model label recorded in results"
    ),
):
    """Score an external report with the same checks as the sandbox task."""
    from dataclasses import replace as _replace
    from datetime import datetime as _dt

    from lm_optimizer.services.sandbox_history import record_run
    from lm_optimizer.services.sandbox_lab import SANDBOX_TASKS, SandboxPolicy
    from lm_optimizer.services.sandbox_runner import SandboxRunner, build_command_for

    if not file.exists() or not file.is_file():
        console.print(f"[red]Report not found: {file}[/red]")
        sys.exit(2)
    definition = SANDBOX_TASKS.get(task)
    if definition is None:
        console.print(f"[red]Unknown task: {task}[/red]")
        sys.exit(2)
    definition = _replace(definition, max_repair_attempts=0)
    slug = "".join(c if c.isalnum() else "_" for c in model)[:60] or "external"
    workdir = (
        Path("results")
        / "external"
        / slug
        / task
        / _dt.now().strftime("%Y%m%d_%H%M%S")
    )
    policy = SandboxPolicy(
        workdir=workdir,
        network_enabled=False,
        timeout_s=definition.timeout_s,
        allowed_executables=definition.allowed_executables,
    )
    runner = SandboxRunner(
        task=definition,
        policy=policy,
        workdir=workdir,
        command=build_command_for(definition),
        model=model,
    )
    content = file.read_text(encoding="utf-8", errors="replace")
    result = runner.run(lambda feedback: content)
    payload = result.as_dict()
    record_run(
        model,
        task,
        payload,
        workdir=str(workdir),
        duration_s=sum(a.duration_s for a in result.attempts),
    )
    console.print(json.dumps(payload, indent=2, ensure_ascii=False))
    console.print(f"[dim]workdir: {workdir}[/dim]")


@app.command("research")
def research(
    question: str = typer.Argument(..., help="Research question"),
    model: str = typer.Option(..., "--model", help="Model id to use"),
    mode: str = typer.Option(
        "agent",
        "--mode",
        help="agent: the model calls search/fetch itself; pipeline: plan, scrape, write",
    ),
    queries: int = typer.Option(4, "--queries", help="Sub-queries (pipeline) or step budget hint"),
    sources: int = typer.Option(6, "--sources", help="Maximum scraped sources"),
    steps: int = typer.Option(8, "--steps", help="Maximum agent tool calls"),
    context: int = typer.Option(8192, "--context", help="Context length for the model"),
    out: Path = typer.Option(
        Path("results") / "research", "--out", help="Directory for the report"
    ),
    safe: bool = typer.Option(True, "--safe/--no-safe", help="Conservative load config"),
    thinking: bool = typer.Option(False, "--thinking/--no-thinking"),
):
    """Online deep research: the model calls real search/fetch tools and writes a report."""
    from datetime import datetime

    import asyncio

    from lm_optimizer.services.model_gate import ModelGate, ModelGateTimeout
    from lm_optimizer.services.web_research import (
        WebResearcher,
        build_report_prompt,
        plan_queries,
    )

    async def _run() -> dict:
        from lm_optimizer.cli.main import get_client
        from lm_optimizer.services.bakeoff import _load_config

        client = get_client()
        await client.connect(echo_probe=False)
        gate = ModelGate(client)
        cfg, _ = _load_config(model, context, False, safe)
        console.print(f"[cyan]Loading {model} (ctx={context})[/cyan]")
        try:
            lease = await gate.acquire(model, cfg)
        except ModelGateTimeout as exc:
            console.print(f"[red]Model gate blocked: {exc}[/red]")
            raise typer.Exit(code=1) from exc

        async def ask(prompt: str, max_tokens: int = 1024) -> str:
            response = await client.chat_completion(
                model=lease.model,
                input_text=prompt,
                temperature=0.2,
                max_output_tokens=max_tokens,
                reasoning=None if thinking else "off",
            )
            return (response.get("choices") or [{}])[0].get("message", {}).get("content", "")

        try:
            researcher = WebResearcher(queries=queries, max_sources=sources)
            try:
                if mode == "pipeline":
                    planned = await plan_queries(question, ask, count=queries)
                    console.print(f"[cyan]Queries:[/cyan] {planned}")
                    collected, warnings = await researcher.collect(planned)
                    if not collected:
                        raise RuntimeError("no sources could be scraped; check the network")
                    console.print(f"[cyan]Sources:[/cyan] {len(collected)} scraped")
                    report = await ask(
                        build_report_prompt(question, collected), max_tokens=8192
                    )
                    from lm_optimizer.services.research_agent import extract_html

                    return {
                        "report_html": extract_html(report),
                        "sources": collected,
                        "queries": planned,
                        "trace": [],
                        "warnings": warnings,
                    }

                from lm_optimizer.services.research_agent import ResearchAgent

                agent = ResearchAgent(ask, researcher, max_steps=steps)
                result = await agent.run(question)
                console.print(
                    f"[cyan]Tool calls:[/cyan] {result.tool_calls} "
                    f"(fetch {result.fetches})"
                )
                if not result.sources:
                    raise RuntimeError(
                        "the model fetched no pages; try --mode pipeline or another model"
                    )
                return {
                    "report_html": result.report_html,
                    "sources": result.sources,
                    "queries": [],
                    "trace": result.trace_payload(),
                    "warnings": result.warnings,
                }
            finally:
                await researcher.close()
        finally:
            await gate.release(lease)
            await client.close()

    payload = asyncio.run(_run())
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = "".join(c if c.isalnum() else "_" for c in question)[:48] or "research"
    out_dir = out / f"{slug}_{stamp}"
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)
    for source in payload["sources"]:
        (out_dir / "raw" / f"{source.id}.txt").write_text(
            f"{source.title}\n{source.url}\n\n{source.text}", encoding="utf-8"
        )
    (out_dir / "report.html").write_text(payload["report_html"], encoding="utf-8")
    (out_dir / "sources.json").write_text(
        json.dumps(
            {
                "question": question,
                "queries": payload["queries"],
                "warnings": payload["warnings"],
                "sources": [
                    {"id": s.id, "title": s.title, "url": s.url, "query": s.query}
                    for s in payload["sources"]
                ],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (out_dir / "trace.json").write_text(
        json.dumps(payload["trace"], indent=2, ensure_ascii=False), encoding="utf-8"
    )
    console.print(f"[green]Report:[/green] {out_dir / 'report.html'}")
    console.print(f"[green]Sources:[/green] {out_dir / 'sources.json'}")
    console.print(f"[green]Trace:[/green] {out_dir / 'trace.json'}")
    for warning in payload["warnings"]:
        console.print(f"[yellow]{warning}[/yellow]")


@app.command("community-import")
def community_import(
    file: Path = typer.Argument(..., help="JSON file with community benchmark records"),
):
    """Import community benchmark records (spec 16.4).
    Records are validated strictly; malformed ones are reported and skipped.
    Duplicates against the shipped database are skipped, never overwritten.
    """
    setup_logging()
    from lm_optimizer.services.community_benchmarks import COMMUNITY_BENCHMARKS
    from lm_optimizer.services.community_import import import_records, load_json_file
    try:
        payload = load_json_file(file)
        merged, warnings = import_records(payload, existing=COMMUNITY_BENCHMARKS)
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Import failed: {e}[/red]")
        sys.exit(1)
    added = len(merged) - len(COMMUNITY_BENCHMARKS)
    for warning in warnings:
        console.print(f"[yellow]{warning}[/yellow]")
    console.print(
        f"Imported {added} new record(s); "
        f"{len(COMMUNITY_BENCHMARKS)} already present."
    )
@app.command("community-export")
def community_export(
    file: Path = typer.Argument(Path("results") / "community-benchmarks.json"),
):
    """Export the shipped community benchmark database to JSON."""
    setup_logging()
    import json as _json
    from lm_optimizer.services.community_benchmarks import COMMUNITY_BENCHMARKS
    from lm_optimizer.services.community_import import export_records
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(
        _json.dumps(export_records(COMMUNITY_BENCHMARKS), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    console.print(f"Exported {len(COMMUNITY_BENCHMARKS)} record(s) to {file}")
@app.command("full-optimize")
def full_optimize(
    model: str = typer.Argument(..., help="Model ID"),
    skip_context: bool = typer.Option(False, "--skip-context", help="Skip the context explorer"),
    skip_quality: bool = typer.Option(False, "--skip-quality", help="Skip the Quality Lab"),
    max_context: int = typer.Option(32768, "--max-context"),
    quality_threshold: float = typer.Option(0.97, "--quality-threshold"),
):
    """Run the full workflow: runtime optimization -> context -> quality (spec §15).
    This command only ORCHESTRATES the existing modules; it never duplicates
    their logic. Each stage is a separate, resumable invocation.
    """
    setup_logging()
    import subprocess
    import sys as _sys
    stages: list[tuple[str, list[str]]] = [
        (
            "runtime",
            [
                _sys.executable, "-m", "lm_optimizer", "optimize", model,
                "--quality-lab", "--max-context", str(max_context),
                "--quality", str(quality_threshold), "--yes", "--non-interactive",
            ],
        ),
    ]
    if not skip_context:
        stages.append(
            (
                "context",
                [
                    _sys.executable, "-m", "lm_optimizer", "ctx", model,
                    "--factor", "1.5", "--round-to", "512",
                    "--max-context", str(max_context),
                ],
            )
        )
    if not skip_quality:
        stages.append(
            (
                "quality",
                [
                    _sys.executable, "-m", "lm_optimizer", "lab", "quality-lab", model,
                    "--seeds", "3",
                ],
            )
        )
    console.print(f"[bold]Full optimization: {model}[/bold]")
    for name, cmd in stages:
        console.print(f"  stage: {name}")
    results: dict[str, int] = {}
    for name, cmd in stages:
        console.print(f"\n[bold]=== {name} ===[/bold]")
        rc = subprocess.call(cmd, cwd=Path.cwd())
        results[name] = rc
        if rc != 0:
            console.print(f"[yellow]stage {name} exited with {rc}[/yellow]")
            break
    console.print("")
    for name, rc in results.items():
        status = "[green]ok[/green]" if rc == 0 else f"[red]rc={rc}[/red]"
        console.print(f"  {name}: {status}")
@app.command("hash-model")
def hash_model(
    model: str = typer.Argument(..., help="Model id (publisher/name)"),
    refresh: bool = typer.Option(False, "--refresh", help="Recompute even if cached"),
):
    """Compute the SHA256 of a model's GGUF file (spec §16.3).
    The hash is cached by path + size + mtime, so hashing a 16 GB file is a
    one-time cost per model version.
    """
    setup_logging()
    from lm_optimizer.services.model_hash import model_sha256
    result = model_sha256(model, refresh=refresh)
    if result["sha256"]:
        console.print(f"{model}")
        console.print(f"  path:   {result['path']}")
        console.print(f"  size:   {result['size_bytes'] / 1e9:.2f} GB")
        console.print(f"  sha256: {result['sha256']}")
        console.print(f"  cached: {result['cached']}")
    else:
        console.print(f"[red]{model}: {result['error']}[/red]")
        sys.exit(1)
@app.command("hash-all")
def hash_all() -> dict[str, Any]:
    """Hash every model currently listed by LM Studio."""
    setup_logging()
    import asyncio as _asyncio
    from lm_optimizer.services.model_hash import hash_all_models
    client = _client()
    async def _list():
        await client.connect()
        try:
            return [m.id for m in await client.list_models()]
        finally:
            try:
                await client.close()
            except Exception as exc:
                log_best_effort("best-effort operation failed", exc)
    ids = _asyncio.run(_list())
    results = hash_all_models(ids)
    for result in results:
        if result["sha256"]:
            console.print(
                f"  {result['model_id'][:52]:52s} {result['sha256'][:16]}... "
                f"{'cached' if result['cached'] else 'new'}"
            )
        else:
            console.print(f"  {result['model_id'][:52]:52s} [yellow]no file[/yellow]")
@app.command("catalogue-sync")
def catalogue_sync(
    query: str = typer.Option("qwen gguf", "--query", help="HuggingFace search query"),
    limit: int = typer.Option(20, "--limit", help="Max repos to inspect"),
    output: Path = typer.Option(
        Path("results") / "hf-catalogue.json", "--output", help="Where to write the catalogue"
    ),
):
    """Discover GGUF models on HuggingFace and add them to the catalogue (spec §16.3).
    Discovered entries are marked source=huggingface and confidence D: they
    are a PRIOR, never evidence. A local measurement upgrades them.
    """
    setup_logging()
    import json as _json
    from lm_optimizer.services.hf_catalog import sync_catalogue
    try:
        result = sync_catalogue(query=query, existing=_default_catalog(), limit=limit)
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Discovery failed: {e}[/red]")
        sys.exit(1)
    for error in result.errors[:10]:
        console.print(f"[yellow]{error}[/yellow]")
    console.print(
        f"Discovered {result.discovered} repo(s): {len(result.added)} new, "
        f"{result.skipped} skipped."
    )
    payload = {
        "query": query,
        "entries": [entry.as_dict() for entry in result.added],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"Catalogue written: {output}")
if __name__ == "__main__":
    app()
@app.command("export-config")
def export_config(
    run_id: str = typer.Argument(..., help="Run ID with a validated winner"),
    out: Path | None = typer.Option(None, "--out", help="Write JSON to this file (default: stdout)"),
    fmt: str = typer.Option("json", "--format", help="json (full export) or vllm (engine config only)"),
):
    """Export the validated winner as a reusable load-config JSON."""
    from lm_optimizer.database.repositories import run_repo
    from lm_optimizer.services.config_export import build_load_config_export
    run = run_repo.get(run_id)
    if not run:
        console.print(f"[red]Run not found: {run_id}[/red]")
        sys.exit(1)
    try:
        data = build_load_config_export(run)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    payload = data["vllm_engine_config"] if fmt == "vllm" else data
    text = json.dumps(payload, indent=2)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        console.print(f"Saved: {out}")
    else:
        console.print_json(text)
@app.command("save-default")
def save_default(
    run_id: str = typer.Argument(..., help="Run ID with a validated winner"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be written, change nothing"
    ),
    no_backup: bool = typer.Option(
        False, "--no-backup", help="Do not copy the previous defaults file"
    ),
    gpu_ratio: float | None = typer.Option(
        None,
        "--gpu-ratio",
        help="Force LM Studio offloadRatio (1.0 = all layers on GPU)",
    ),
    context: int | None = typer.Option(
        None,
        "--context",
        help="Override LM Studio contextLength",
    ),
    lmstudio_home: Path | None = typer.Option(
        None,
        "--lmstudio-home",
        help="LM Studio home dir (env LM_OPTIMIZER_LMSTUDIO_HOME; default ~/.lmstudio)",
    ),
):
    """Persist the validated winner as LM Studio's per-model load default.
    Writes `~/.lmstudio/.internal/user-concrete-model-default-config/...json`,
    which LM Studio applies on the next load (no restart). Unknown keys in
    the file are preserved and the previous version is backed up.
    """
    from lm_optimizer.database.repositories import run_repo
    from lm_optimizer.services.lmstudio_defaults import (
        DefaultsError,
        save_run_defaults,
    )
    run = run_repo.get(run_id)
    if not run:
        console.print(f"[red]Run not found: {run_id}[/red]")
        raise typer.Exit(1)
    if gpu_ratio is not None or context is not None:
        from dataclasses import replace
        best = run.get_best_config()
        if best is not None:
            overrides = {}
            if gpu_ratio is not None:
                overrides["gpu_ratio"] = gpu_ratio
            if context is not None:
                overrides["context_length"] = context
            best.config = replace(best.config, **overrides)
    try:
        result = save_run_defaults(
            run, dry_run=dry_run, backup=not no_backup, home=lmstudio_home
        )
    except DefaultsError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None
    if dry_run:
        console.print(f"[yellow]Dry run[/yellow] — {result.path} not written")
    else:
        console.print(f"[green]Saved[/green]: {result.path}")
    if result.backup_path:
        console.print(f"Backup: {result.backup_path}")
    table = Table(title="LM Studio load defaults")
    table.add_column("Key")
    table.add_column("Value", justify="right")
    for key, value in result.fields.items():
        table.add_row(key, json.dumps(value))
    console.print(table)
def _winner_config(run, run_id: str):
    """A run's validated winner config, with the context_length fallback."""
    from dataclasses import replace
    best = run.get_best_config() if hasattr(run, "get_best_config") else None
    config = getattr(best, "config", None)
    if config is None:
        console.print(f"[red]No validated winner in run {run_id}[/red]")
        raise typer.Exit(1)
    if config.context_length is None and getattr(best, "context_length", None):
        config = replace(config, context_length=best.context_length)
    return config
@app.command("diff-default")
def diff_default(
    run_id: str = typer.Argument(..., help="Run ID with a validated winner"),
    lmstudio_home: Path | None = typer.Option(
        None,
        "--lmstudio-home",
        help="LM Studio home dir (env LM_OPTIMIZER_LMSTUDIO_HOME; default ~/.lmstudio)",
    ),
):
    """Show how a model's LM Studio defaults differ from the run's winner.
    Read-only: the defaults file is never written by this command.
    """
    from lm_optimizer.database.repositories import run_repo
    from lm_optimizer.services.lmstudio_defaults import DefaultsError, diff_defaults
    run = run_repo.get(run_id)
    if not run:
        console.print(f"[red]Run not found: {run_id}[/red]")
        raise typer.Exit(1)
    config = _winner_config(run, run_id)
    model_id = getattr(getattr(run, "model", None), "id", "") or ""
    try:
        diff = diff_defaults(model_id, config, home=lmstudio_home)
    except DefaultsError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None
    console.print(f"Model: {diff.model_id}")
    console.print(f"File:  {diff.path}")
    if not diff.changes:
        console.print("[green]Defaults are already up to date.[/green]")
    else:
        table = Table(title=f"{len(diff.changes)} field(s) would change")
        table.add_column("Key")
        table.add_column("Current")
        table.add_column("Winner")
        for change in diff.changes:
            current = (
                "-"
                if change.get("kind") == "added"
                else json.dumps(change.get("current"))
            )
            table.add_row(
                str(change.get("key")),
                current,
                json.dumps(change.get("winner")),
            )
        console.print(table)
    console.print(
        f"{len(diff.changes)} change(s), {len(diff.unchanged)} unchanged, "
        f"{len(diff.preserved)} preserved key(s)"
    )
@app.command("restore-default")
def restore_default(
    model: str = typer.Argument(..., help="Model ID whose defaults to restore"),
    backup: str = typer.Option("latest", "--backup", help="Backup name, or 'latest'"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be restored, change nothing"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Restore without asking for confirmation"
    ),
    lmstudio_home: Path | None = typer.Option(
        None,
        "--lmstudio-home",
        help="LM Studio home dir (env LM_OPTIMIZER_LMSTUDIO_HOME; default ~/.lmstudio)",
    ),
):
    """Restore a model's LM Studio defaults from a backup.
    The current file is backed up before it is overwritten. An unknown
    backup fails before anything is written or any question is asked.
    """
    from lm_optimizer.services.lmstudio_defaults import DefaultsError, restore_defaults
    try:
        preview = restore_defaults(
            model, backup=backup, dry_run=True, home=lmstudio_home
        )
    except DefaultsError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None
    if not yes and not dry_run:
        console.print(f"Restore {model} from backup: {preview.restored_from}")
        typer.confirm("Overwrite the current LM Studio defaults?", abort=True)
    try:
        result = (
            preview
            if dry_run
            else restore_defaults(
                model, backup=backup, dry_run=False, home=lmstudio_home
            )
        )
    except DefaultsError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None
    console.print(f"Model: {result.model_id}")
    console.print(f"restored_from: {result.restored_from}")
    console.print(f"noop: {result.noop}")
    console.print(f"backup_path: {result.backup_path or '-'}")
    console.print(f"dry_run: {result.dry_run}")
    if dry_run:
        console.print(f"[yellow]Dry run[/yellow] — {result.path} not written")
    elif result.noop:
        console.print(f"[green]No change[/green]: {result.path} already matches")
    else:
        console.print(f"[green]Restored[/green]: {result.path}")
def _print_verify_result(result: dict) -> None:
    """Render a ``verify_defaults`` payload; exit 1 when it is not verified."""
    if not result.get("verified"):
        console.print("[red]not verified[/red]")
        if result.get("error"):
            console.print(f"[red]{result['error']}[/red]")
        mismatches = result.get("mismatches") or {}
        if mismatches:
            table = Table(title="Mismatches")
            table.add_column("Field")
            table.add_column("Expected")
            table.add_column("Actual")
            for key, values in mismatches.items():
                table.add_row(
                    str(key),
                    json.dumps(values.get("expected")),
                    json.dumps(values.get("actual")),
                )
            console.print(table)
        raise typer.Exit(1)
    checked = result.get("checked") or {}
    console.print(f"[green]verified[/green] — {len(checked)} field(s) match")
    unverified = result.get("unverified") or []
    if unverified:
        console.print(f"[yellow]not echoed by LM Studio: {', '.join(unverified)}[/yellow]")
    if not result.get("unloaded"):
        console.print("[yellow]model was not unloaded[/yellow]")
@app.command("verify-default")
def verify_default(
    run_id: str = typer.Argument(..., help="Run ID with a validated winner"),
):
    """Verify the saved defaults with an echo load (never writes).
    LM Studio resolves the saved default when loading with an empty config
    and echoes the resolved values back. Only echoed fields are verified;
    the model is unloaded again in every case.
    """
    import asyncio
    from lm_optimizer.api import routes
    from lm_optimizer.database.repositories import run_repo
    from lm_optimizer.services.lmstudio_default_verify import verify_defaults
    run = run_repo.get(run_id)
    if not run:
        console.print(f"[red]Run not found: {run_id}[/red]")
        raise typer.Exit(1)
    config = _winner_config(run, run_id)
    model_id = getattr(getattr(run, "model", None), "id", "") or ""
    async def _run():
        client_result = routes.get_lm_client(echo_probe=False)
        if hasattr(client_result, "__await__"):
            client = await client_result
        else:
            client = client_result
        try:
            return await verify_defaults(model_id, config, client=client)
        finally:
            try:
                close = getattr(client, "close", None)
                if close is not None:
                    await close()
            except Exception as exc:
                log_best_effort("best-effort operation failed", exc)
    result = asyncio.run(_run())
    _print_verify_result(result)
@app.command("test-manager")
def test_manager(
    interactive: bool = typer.Option(
        False, "--interactive", "-i", help="Prompt before each phase"
    ),
    use_assistant: bool = typer.Option(
        False, "--use-assistant", help="Use assistant endpoint (needs .env key)"
    ),
    speed_floor: float = typer.Option(5.0, "--speed-floor"),
    calm_minutes: int = typer.Option(15, "--calm-minutes", help="Minutes of GPU/CPU calm before full cycle proceeds"),
    check_interval: int = typer.Option(60, "--check-interval", help="Seconds between GPU/CPU checks"),
    all_models: bool = typer.Option(False, "--all", help="Run all models"),
    models: str = typer.Option(None, "--models", help="Comma-separated model indices (e.g., 1,2,5,8)"),
    test_count: int = typer.Option(1, "--test-count", help="Number of tests to run (1=single, 3=full)"),
    detail_level: str = typer.Option("full", "--detail-level", help="Detail level: quick, standard, full, benchmark"),
    overnight: bool = typer.Option(False, "--overnight", help="Run through all selected without interruption"),
    model_detail: str = typer.Option(None, "--model-detail", help="One detail level per --models entry, e.g. --models 1,2,5 --model-detail quick,full,benchmark"),
):
    """Integrated test manager: intelligent ordering, partial results, assistant opt-in."""
    from lm_optimizer.services.test_manager import TestManager
    manager = TestManager(speed_floor=speed_floor, vram_floor_mb=250)
    console.print(f"[green]Test manager started[/green] (interactive={interactive}, assistant={use_assistant}, floor={speed_floor}, calm_minutes={calm_minutes}, check_interval={check_interval})")
    if interactive:
        console.print("[yellow]Interactive mode: will prompt before each major phase.[/yellow]")
    # Full automated cycle (no live model load by default; scheduling logic only)
    try:
        cycle_result = manager.run_cycle(
            model_id="lmstudio-community/NVIDIA-Nemotron-3.5-Bolt-74B-A9B-24GB-GGUF",
            interactive=interactive,
            use_assistant=use_assistant,
            calm_minutes=calm_minutes,
            check_interval=check_interval,
            all_models=all_models,
            models=models,
            test_count=test_count,
            detail_level=detail_level,
            overnight=overnight,
            model_detail=model_detail,
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(2) from None
    per_model = cycle_result.get("per_model_plan") or {}
    if per_model:
        console.print("[bold]Per-model depth[/bold]")
        for key, level in per_model.items():
            console.print(f"  {key}: {level}")
    console.print(f"[dim]Cycle result: {cycle_result}[/dim]")
@app.command("ollama-save-default")
def ollama_save_default(
    run_id: str = typer.Argument(..., help="Run ID with a validated winner"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """Persist the validated winner as Ollama's per-model defaults."""
    from lm_optimizer.database.repositories import run_repo
    from lm_optimizer.services.ollama_defaults import DefaultsError, save_run_ollama_defaults
    run = run_repo.get(run_id)
    if not run:
        console.print(f"[red]Run not found: {run_id}[/red]")
        raise typer.Exit(1)
    try:
        result = save_run_ollama_defaults(run, dry_run=dry_run)
    except DefaultsError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None
    console.print(f"Saved to {result['path']}")
    if dry_run:
        console.print("[yellow]Dry run[/yellow] - no changes written")
@app.command("ollama-diff-default")
def ollama_diff_default(
    run_id: str = typer.Argument(..., help="Run ID with a validated winner"),
):
    """Show how Ollama defaults differ from a run's winner."""
    from lm_optimizer.database.repositories import run_repo
    from lm_optimizer.services.ollama_defaults import diff_ollama_defaults
    run = run_repo.get(run_id)
    if not run:
        console.print(f"[red]Run not found: {run_id}[/red]")
        raise typer.Exit(1)
    best = run.get_best_config()
    if best is None:
        console.print(f"[red]No validated winner in run {run_id}[/red]")
        raise typer.Exit(1)
    config = best.config
    model_id = getattr(getattr(run, "model", None), "id", "") or ""
    diff = diff_ollama_defaults(model_id, config)
    if not diff["changes"]:
        console.print("[green]Defaults are already up to date.[/green]")
    else:
        for c in diff["changes"]:
            console.print(f"{c['key']}: {c['kind']} (current={c.get('current')}, winner={c.get('winner')})")
@app.command("ollama-restore-default")
def ollama_restore_default(
    model: str = typer.Argument(..., help="Model ID whose defaults to restore"),
    backup: str = typer.Option("latest", "--backup"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    yes: bool = typer.Option(False, "--yes", "-y"),
):
    """Restore Ollama defaults from a backup."""
    from lm_optimizer.services.ollama_defaults import DefaultsError, restore_ollama_defaults
    if not yes and not dry_run:
        typer.confirm("Overwrite the current Ollama defaults?", abort=True)
    try:
        result = restore_ollama_defaults(model, backup=backup, dry_run=dry_run)
    except DefaultsError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None
    console.print(f"Restored from {result['restored_from']} (noop={result['noop']}, dry_run={result['dry_run']})")
@app.command("recommend")
def recommend_model(
    model_id: str = typer.Argument(..., help="Model to recommend configs for"),
):
    """Recommend best configuration for a model based on benchmarks."""
    console.print(f"[green]Recommend mode activated for {model_id}[/green]")
@app.command("clean")
@app.command("clean-tests")
def clean_tests(
    dry_run: bool = typer.Option(True, "--dry-run", help="Show what would be cleaned (default)"),
    confirm: bool = typer.Option(False, "--confirm", help="Actually delete failed runs"),
    failed_count: int = typer.Option(2, "--failed-count", help="Consecutive failures before cleanup"),
):
    """Clean failed artifacts and DB entries. Never deletes outside this folder."""
    if confirm:
        dry_run = False
    console.print(
        f"[yellow]Clean (dry_run={dry_run}, threshold={failed_count}) — "
        f"only within project folder.[/yellow]"
    )
    from lm_optimizer.database.repositories import run_repo
    from lm_optimizer.domain.models import ConfigurationStatus
    runs = run_repo.list_all(limit=10000)
    # Group runs by model_id
    from collections import defaultdict
    model_runs: dict[str, list] = defaultdict(list)
    for run in runs:
        model_runs[run.model.id].append(run)
    # Count consecutive failures per model (from most recent)
    to_delete = []
    for model_id, model_run_list in model_runs.items():
        # Sort by created_at descending (most recent first)
        sorted_runs = sorted(model_run_list, key=lambda r: r.created_at or r.id, reverse=True)
        consecutive_failures = 0
        failed_run_ids = []
        for run in sorted_runs:
            if run.status == ConfigurationStatus.FAILED:
                consecutive_failures += 1
                failed_run_ids.append(str(run.id))
            else:
                break  # stop at first non-failed
        if consecutive_failures >= failed_count:
            to_delete.extend(failed_run_ids)
    if dry_run:
        if not to_delete:
            console.print("[green]No failed runs found[/green]")
        else:
            console.print(f"[yellow]Dry run: would delete {len(to_delete)} failed run(s)[/yellow]")
            for run_id in sorted(to_delete):
                console.print(f"  - {run_id}")
    else:
        if not to_delete:
            console.print("[green]No failed runs to clean[/green]")
        else:
            deleted = 0
            for run_id in to_delete:
                if run_repo.delete(run_id):
                    deleted += 1
            console.print(f"[green]Removed {deleted} failed run(s)[/green]")