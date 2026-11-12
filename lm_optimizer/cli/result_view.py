"""Rich console view for an optimization run result."""



from __future__ import annotations
from typing import Any





from rich.console import Console

from rich.panel import Panel

from rich.table import Table



from lm_optimizer.logging_config import get_logger

from lm_optimizer.services.best_effort import log_best_effort

from lm_optimizer.services.generation_defaults import lookup as generation_lookup



console = Console()

logger = get_logger(__name__)





def _generation_for(model_id: str, architecture: str | None = None) -> dict:

    """Sourced generation settings dict for .md reports (settings + source)."""

    found = generation_lookup(model_id, architecture)

    return {**found["settings"], "source": found["source"]}





def _phase_transparency_table(run, best):

    """PHASE A/B TRANSPARENCY table (None for legacy runs without phase_ab)."""

    pab = (run.benchmark_params or {}).get("phase_ab") or {}

    if not pab:

        return None

    phase = Table(title="PHASE A/B TRANSPARENCY")

    phase.add_column("Item", style="cyan")

    phase.add_column("Value", style="yellow")

    phase.add_row(

        "Contexts (frozen)",

        f"speed={pab.get('speed_context', '?')} "

        f"quality={pab.get('quality_context', '?')} "

        f"budget={pab.get('budget_class', '?')}",

    )

    raw_id = str(pab.get("raw_fastest_id") or "")

    raw = next((c for c in run.configurations if str(c.id) == raw_id), None)

    if raw is not None:

        q = f"{raw.quality_score.overall:.3f}" if raw.quality_score else "N/A"

        phase.add_row(

            "Raw fastest",

            f"ctx {raw.context_length} "

            f"{raw.get_avg_generation_tok_s():.1f} tok/s quality {q} "

            f"status={raw.status.value}",

        )

    phase.add_row(

        "Quality-safe",

        f"ctx {best.context_length} "

        f"{best.get_avg_generation_tok_s():.1f} tok/s "

        f"(highest acceptable speed above threshold)",

    )

    for entry in pab.get("recovery_log") or []:

        if isinstance(entry, dict) and entry.get("suspect"):

            phase.add_row(

                "Recovery",

                f"{entry.get('suspect')} "

                f"{entry.get('old_value')}->{entry.get('new_value')} "

                f"passed={entry.get('recheck_passed')}",

            )

    for note in pab.get("excluded_notes") or []:

        phase.add_row("Not auto-tuned", str(note)[:100])

    if pab.get("phase_b_enabled"):

        pb = pab.get("phase_b_result") or {}

        phase.add_row(

            "Phase B",

            f"GPU-only max={pb.get('gpu_only_max', '?')} "

            f"system max={pb.get('system_max', '?')} "

            f"final={pb.get('final_capacity', '?')}",

        )

    return phase





def display_optimization_result(run) -> None:
    """Display optimization results with baseline comparison and score breakdown.



    Zero-pass runs show an explicit failure state (never a fake N/A winner and

    never an Apply offer). Partial runs are labeled and only PASSED configs

    may win. Successful runs show exactly ONE primary + ALTERNATIVES crowns.

    """

    from lm_optimizer.services.orchestration.run_summary import (

        alternatives,

        classify_run,

        failure_reason_text,

        why_text,

    )



    state, info = classify_run(list(run.configurations), run)

    if state == "FAILED":

        console.print(Panel.fit("[bold red]Optimization unsuccessful[/bold red]"))

        console.print("No valid configurations were successfully benchmarked.")

        console.print(f"\nReason:\n{failure_reason_text(run)}")

        fb = info.get("failure_classes", {})

        table = Table(title="Failures")

        table.add_column("Class", style="cyan")

        table.add_column("Count", justify="right")

        for k in ("load_failures", "oom", "timeouts", "quality_rejected", "unsupported_parameters"):

            table.add_row(k, str(fb.get(k, 0)))

        console.print(table)

        base = run.get_baseline_config()

        if base is not None:

            console.print(

                f"Last successful baseline: ctx {base.context_length} "

                f"{base.get_avg_generation_tok_s():.1f} tok/s"

            )

        else:

            console.print("[dim]No successful baseline available.[/dim]")

        # Show every tested config so a failed run is still fully inspectable.

        configs = list(run.configurations or [])

        if configs:

            tbl = Table(title="Tested configurations")

            tbl.add_column("Ctx", justify="right", style="cyan")

            tbl.add_column("Gen tok/s", justify="right")

            tbl.add_column("Quality", justify="right")

            tbl.add_column("Checks", justify="right")

            tbl.add_column("Status", style="yellow")

            tbl.add_column("Error", style="dim")

            for c in configs:

                q = c.quality_score.overall if c.quality_score else None

                checks = (

                    f"{c.quality_score.checks_passed}/{c.quality_score.checks_total}"

                    if c.quality_score and c.quality_score.checks_total

                    else "-"

                )

                tbl.add_row(

                    str(c.context_length),

                    f"{c.get_avg_generation_tok_s():.1f}",

                    f"{q:.3f}" if q is not None else "N/A",

                    checks,

                    str(getattr(c.status, "value", c.status)),

                    str(c.error or "")[:60],

                )

            console.print(tbl)

        return  # never offer Apply



    from lm_optimizer.services.orchestration.run_summary import final_recommendation



    best = final_recommendation(list(run.configurations), run)

    if best is None:

        console.print("[yellow]No successful configuration found[/yellow]")

        return

    bc = best.config

    if state == "NO_WINNER":

        console.print(

            Panel.fit(

                "[bold yellow]Optimization completed — no quality-validated winner[/bold yellow]"

            )

        )

        console.print(

            "The model generated usable output, but no configuration met the "

            f"quality threshold ({run.quality_threshold}). Best diagnostic candidate below."

        )

    else:

        console.print(Panel.fit(f"[bold green]Optimization Complete: {run.model.id}[/bold green]"))

    console.print(f"[dim]Run state: {state} (status={run.status.value})[/dim]")



    # ---- FINAL RECOMMENDATION: exactly one primary ----

    try:

        gen = _generation_for(run.model.id, getattr(run.model, "architecture", None))

    except Exception:

        gen = {}

    rec = Table(title="FINAL RECOMMENDATION")

    rec.add_column("Field", style="cyan")

    rec.add_column("Value", style="green")

    rec.add_row("Model", str(run.model.id))

    rec.add_row("Profile", str(run.profile.value))

    rec.add_row("Context", str(best.context_length))

    rec.add_row("GPU Offload", f"{bc.gpu_ratio:.2f}" if bc.gpu_ratio is not None else "Auto")

    rec.add_row("KV Cache", "GPU" if bc.offload_kv_cache_to_gpu else "CPU")

    rec.add_row("Flash Attention", "Enabled" if bc.flash_attention else "Disabled")

    rec.add_row("Eval Batch", str(bc.eval_batch_size) if bc.eval_batch_size else "Auto")

    rec.add_row("CPU Threads", f"{run.hardware.cpu_cores_logical} recommended (REST cannot set)")

    rec.add_row("Generation", f"temperature={gen.get('temperature', 'suite default')}")

    rec.add_row("Prefill", f"{best.get_avg_prompt_tok_s():.0f} tok/s")

    rec.add_row("Estimated TTFT", f"{best.get_avg_estimated_ttft_ms():.0f} ms (estimated)")

    rec.add_row("VRAM", f"{best.peak_vram_gb:.1f} GB" if best.peak_vram_gb else "N/A")

    rec.add_row("RAM", f"{best.peak_ram_gb:.1f} GB" if best.peak_ram_gb else "N/A")

    if best.quality_score:

        rec.add_row(

            "Correctness",

            f"{best.quality_score.overall:.3f} "

            f"({best.quality_score.checks_passed}/{best.quality_score.checks_total} checks)",

        )

    else:

        rec.add_row("Correctness", "N/A")

    rec.add_row("Stability", f"{best.stability_score:.3f}")

    if run.baseline_metrics and run.baseline_metrics.get("generation_tok_s"):

        try:

            base = run.baseline_metrics["generation_tok_s"]

            cur = best.get_avg_generation_tok_s()

            pct = (cur - base) / base * 100 if base else 0

            rec.add_row("Baseline improvement", f"{pct:+.1f}% ({base:.1f} -> {cur:.1f} tok/s)")

        except Exception:

            rec.add_row("Baseline improvement", "N/A")

    else:

        rec.add_row("Baseline improvement", "N/A (no baseline)")

    rec.add_row("Why", why_text(best, run.baseline_metrics, run.profile.value))

    try:

        from lm_optimizer.services.reporting import _identical_configs, _median



        _same = _identical_configs(list(run.configurations), best)

        if len(_same) > 1:

            _med = _median([c.get_avg_generation_tok_s() for c in _same])

            rec.add_row(

                "Typical (identical runs)",

                f"{_med:.1f} tok/s median of {len(_same)} "

                f"(stored repeat {best.get_avg_generation_tok_s():.1f})",

            )

    except Exception as exc:

        log_best_effort("best-effort operation failed", exc)

    console.print(rec)



    ctx_speed = (best.generation or {}).get("context_speed")

    if isinstance(ctx_speed, dict) and ctx_speed.get("results"):

        cs = Table(title="CONTEXT SPEED (winner config)")

        cs.add_column("Context", justify="right", style="cyan")

        cs.add_column("Gen tok/s", justify="right")

        cs.add_column("Status", style="green")

        for r in ctx_speed["results"]:

            ok = bool(r.get("ok"))

            cs.add_row(

                str(r.get("ctx")),

                f"{float(r.get('tok_s') or 0):.2f}" if ok else "-",

                "PASS" if ok else f"FAIL: {str(r.get('error') or '')[:50]}",

            )

        console.print(cs)



    # ---- PHASE A/B transparency: raw fastest (even if rejected) ----

    phase_table = _phase_transparency_table(run, best)

    if phase_table is not None:

        console.print(phase_table)



    # ---- ALTERNATIVES crowns ----

    crowns = alternatives(list(run.configurations), best)

    if crowns:

        alt = Table(title="ALTERNATIVES")

        alt.add_column("Crown", style="cyan")

        alt.add_column("Context", justify="right")

        alt.add_column("Gen tok/s", justify="right")

        alt.add_column("Quality", justify="right")

        alt.add_column("VRAM", justify="right")

        for label, key in (

            ("Best Speed", "best_speed"),

            ("Best Context", "best_context"),

            ("Best Quality", "best_quality"),

            ("Best Memory", "best_memory"),

        ):

            c = crowns.get(key)

            if c is None:

                continue

            q = f"{c.quality_score.overall:.3f}" if c.quality_score else "N/A"

            alt.add_row(

                label,

                str(c.context_length),

                f"{c.get_avg_generation_tok_s():.1f}",

                q,

                f"{c.peak_vram_gb:.1f}" if c.peak_vram_gb else "N/A",

            )

        console.print(alt)



    # Winner score line (FINAL RECOMMENDATION above is authoritative).

    console.print(

        f"[dim]Primary winner score={best.score:.3f}; "

        "failed configurations never enter the winner set.[/dim]"

    )

    try:

        from lm_optimizer.services.orchestration.run_summary import speed_range as _speed_range



        _range = _speed_range(list(run.configurations))

        if _range is not None:

            _fastest_cfg, _slowest_cfg = _range

            console.print(

                "[dim]Run speed range (passed configs): "

                f"best {_fastest_cfg.get_avg_generation_tok_s():.1f} tok/s "

                f"(ctx {_fastest_cfg.context_length}) / worst "

                f"{_slowest_cfg.get_avg_generation_tok_s():.1f} tok/s "

                f"(ctx {_slowest_cfg.context_length}).[/dim]"

            )

    except Exception as exc:

        log_best_effort("best-effort operation failed", exc)

    # Metrics with baseline comparison (percentage changes from actual measurements)

    metrics_table = Table(title="Performance Metrics")

    metrics_table.add_column("Metric", style="cyan")

    metrics_table.add_column("Optimized", style="green")

    if run.baseline_metrics:

        metrics_table.add_column("Baseline", style="yellow")

        metrics_table.add_column("Change", style="magenta")



    def fmt_change(new, old) -> str:
        if old and old != 0:

            pct = (new - old) / old * 100

            sign = "+" if pct >= 0 else ""

            return f"{sign}{pct:.1f}%"

        return "-"



    # Gather baseline if available

    baseline = run.baseline_metrics or {}

    if baseline:

        metrics_table.add_row(

            "Generation Speed",

            f"{best.get_avg_generation_tok_s():.1f} tok/s",

            f"{baseline.get('generation_tok_s', 0):.1f} tok/s",

            fmt_change(best.get_avg_generation_tok_s(), baseline.get("generation_tok_s")),

        )

        metrics_table.add_row(

            "Prompt Processing",

            f"{best.get_avg_prompt_tok_s():.0f} tok/s",

            f"{baseline.get('prompt_tok_s', 0):.0f} tok/s",

            fmt_change(best.get_avg_prompt_tok_s(), baseline.get("prompt_tok_s")),

        )

        metrics_table.add_row(

            "Est. TTFT",

            f"{best.get_avg_estimated_ttft_ms():.0f} ms",

            f"{baseline.get('estimated_ttft_ms', 0):.0f} ms",

            fmt_change(best.get_avg_estimated_ttft_ms(), baseline.get("estimated_ttft_ms")),

        )

        if best.quality_score:

            qs = best.quality_score

            checks = (

                f"{qs.checks_passed}/{qs.checks_total} checks"

                if hasattr(qs, "checks_passed")

                else ""

            )

            baseline_q = baseline.get("quality_overall", 0)

            metrics_table.add_row(

                "Correctness / Quality",

                f"{qs.overall:.3f} ({checks})",

                f"{baseline_q:.3f}" if baseline_q else "N/A",

                fmt_change(qs.overall, baseline_q),

            )

        else:

            metrics_table.add_row("Correctness / Quality", "N/A", "N/A", "-")

        metrics_table.add_row(

            "Stability Score",

            f"{best.stability_score:.3f}",

            f"{baseline.get('stability', 0):.3f}" if baseline.get("stability") else "N/A",

            "-",

        )

        metrics_table.add_row(

            "Context Length",

            str(best.context_length),

            str(baseline.get("context_length", "N/A")),

            fmt_change(best.context_length, baseline.get("context_length")),

        )

        metrics_table.add_row(

            "VRAM",

            f"{best.peak_vram_gb:.1f} GB" if best.peak_vram_gb else "not measured",

            f"{baseline.get('peak_vram_gb', 0):.1f} GB" if baseline.get("peak_vram_gb") else "-",

            fmt_change(best.peak_vram_gb or 0, baseline.get("peak_vram_gb") or 0),

        )

        metrics_table.add_row(

            "RAM",

            f"{best.peak_ram_gb:.1f} GB" if best.peak_ram_gb else "not measured",

            "-",

            "-",

        )

        metrics_table.add_row("Optimization Time", f"{run.duration_seconds:.1f} s", "-", "-")

    else:

        metrics_table.add_row("Generation Speed", f"{best.get_avg_generation_tok_s():.1f} tok/s")

        metrics_table.add_row("Prompt Processing", f"{best.get_avg_prompt_tok_s():.0f} tok/s")

        metrics_table.add_row("Est. TTFT", f"{best.get_avg_estimated_ttft_ms():.0f} ms (estimated)")

        if best.quality_score:

            qs = best.quality_score

            checks = (

                f"{qs.checks_passed}/{qs.checks_total} checks passed"

                if hasattr(qs, "checks_passed")

                else ""

            )

            metrics_table.add_row(

                "Correctness / Quality",

                f"{qs.overall:.3f} ({checks}, heuristic checks)",

            )

        metrics_table.add_row("Stability Score", f"{best.stability_score:.3f}")

        metrics_table.add_row("Context Length", str(best.context_length))

        metrics_table.add_row(

            "VRAM", f"{best.peak_vram_gb:.1f} GB" if best.peak_vram_gb else "not measured"

        )

        metrics_table.add_row(

            "RAM", f"{best.peak_ram_gb:.1f} GB" if best.peak_ram_gb else "not measured"

        )

        metrics_table.add_row("Optimization Time", f"{run.duration_seconds:.1f} s")



    console.print(metrics_table)



    # Score breakdown explainability

    if best.score_breakdown:

        console.print("\n[bold]Score Breakdown (why this config won):[/bold]")

        bd_table = Table(title=f"{run.profile.value.capitalize()} score: {best.score:.3f}")

        bd_table.add_column("Component", style="cyan")

        bd_table.add_column("Normalized", justify="right")

        bd_table.add_column("Weight", justify="right")

        bd_table.add_column("Contribution", justify="right")

        # Actual weights used for this config's phase (Phase A zeroes

        # context); profile defaults only as fallback for legacy data.

        weights = (best.generation or {}).get("score_weights") or (

            run.profile_weights if hasattr(run, "profile_weights") else {}

        )

        for comp, norm in best.score_breakdown.items():

            w = weights.get(comp, 0)

            contrib = norm * w

            bd_table.add_row(comp, f"{norm:.3f}", f"{w:.2f}", f"{contrib:.3f}")

        console.print(bd_table)

        console.print(

            "[dim]Normalization: speeds/TTFT run-relative, context model-relative, memory hardware-relative. See docs/OPTIMIZATION_METHOD.md[/dim]"

        )



    # Pareto frontier

    pareto = run.get_pareto_configs()

    if pareto:

        console.print("\n[bold]Pareto Frontier:[/bold]")

        pf_table = Table()

        pf_table.add_column("Profile", style="cyan")

        pf_table.add_column("Context", justify="right")

        pf_table.add_column("GPU", justify="right")

        pf_table.add_column("KV", style="yellow")

        pf_table.add_column("Batch", justify="right")

        pf_table.add_column("Gen tok/s", justify="right")

        pf_table.add_column("VRAM (GB)", justify="right")

        pf_table.add_column("Quality", justify="right")



        for r in pareto:

            rc = r.config

            pf_table.add_row(

                "Custom",

                str(r.context_length),

                f"{rc.gpu_ratio:.0%}" if rc.gpu_ratio else "N/A",

                "GPU" if rc.offload_kv_cache_to_gpu else "CPU",

                str(rc.eval_batch_size) if rc.eval_batch_size else "N/A",

                f"{r.get_avg_generation_tok_s():.1f}",

                f"{r.peak_vram_gb:.1f}" if r.peak_vram_gb else "N/A",

                f"{r.quality_score.overall:.3f}" if r.quality_score else "N/A",

            )



        console.print(pf_table)




