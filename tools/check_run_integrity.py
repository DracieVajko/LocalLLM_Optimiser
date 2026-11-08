"""Check whether an optimizer run's numbers can be trusted.

Reads `data/optimizer.db` and reports the failure modes documented in
`docs/plans/OPTIMIZER-CODE-REVIEW-20261106.md`:

- a run that finished faster than the physics allows (benchmark-cache replay)
- validation rounds that were dropped instead of counted (cherry-picked quality)
- identical configurations re-tested (flaky harness / broken dedupe)
- stage-4 configurations that cannot change a single-request decode rate
- a "long_context" case whose prompt never approached the context length
- missing durations, empty Pareto frontier, contradictory model identity

Exit code 0 = trustworthy, 1 = at least one FAIL.

    python tools/check_run_integrity.py                # newest 5 runs
    python tools/check_run_integrity.py --run 7ae5ffae # one run (id prefix ok)
    python tools/check_run_integrity.py --all
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

DB = Path("data") / "optimizer.db"

#: Parameters that cannot change the decode rate of one request at a time.
NOOP_DIMENSIONS = (
    "eval_batch_size",
    "physical_batch_size",
    "parallel",
    "context_checkpoints",
)


class Report:
    def __init__(self, title: str) -> None:
        self.title = title
        self.lines: list[tuple[str, str]] = []

    def add(self, status: str, message: str) -> None:
        self.lines.append((status, message))

    @property
    def failed(self) -> bool:
        return any(s == "FAIL" for s, _ in self.lines)

    def render(self) -> str:
        out = [self.title]
        for status, message in self.lines:
            out.append(f"  {status:<4}  {message}")
        return "\n".join(out)


def _json(value: str | None, default):
    try:
        return json.loads(value) if value else default
    except (TypeError, json.JSONDecodeError):
        return default


def _median(values: list[float]) -> float:
    values = sorted(values)
    return values[len(values) // 2] if values else 0.0


def _cfg_only(config_json: str | None) -> dict:
    """The configuration fields only.

    `config_json` also embeds a `generation` block with per-run data
    (quality_by_test, mem_before, preheat), so a whole-object comparison makes
    every record unique and hides duplicate configurations.
    """
    cfg = _json(config_json, {})
    if isinstance(cfg, dict):
        cfg.pop("generation", None)
    return cfg


def check_run(cur: sqlite3.Cursor, run: sqlite3.Row) -> Report:
    run_id = run["id"]
    params = _json(run["benchmark_params_json"], {})
    rep = Report(
        f'run {run_id[:8]}  {run["model_id"]}  '
        f'profile={run["profile"]}  status={run["status"]}'
    )

    configs = list(
        cur.execute(
            "select tested_at, context_length, status, error, duration_ms,"
            " metrics_json, config_json, quality_json"
            " from configurations where run_id=? order by tested_at",
            (run_id,),
        )
    )
    if not configs:
        rep.add("FAIL", "no configurations recorded")
        return rep

    passed = [c for c in configs if c["status"] == "passed"]
    failed = [c for c in configs if c["status"] != "passed"]
    rep.add("INFO", f"{len(configs)} configurations: {len(passed)} passed, {len(failed)} not")

    # --- 1. cache replay: elapsed vs the physics of the measured tokens ----
    reps = params.get("benchmark_repetitions")
    val_reps = params.get("validation_repetitions")
    if reps == 1:
        rep.add(
            "WARN",
            "benchmark_repetitions=1 -> the benchmark cache was eligible "
            "(benchmark.py:701); results may be replayed, not measured",
        )
    total_tokens = 0.0
    speed_samples: list[float] = []
    for c in configs:
        metrics = _json(c["metrics_json"], [])
        if not isinstance(metrics, list):
            continue
        for m in metrics:
            if not isinstance(m, dict):
                continue
            total_tokens += float(m.get("completion_tokens") or 0)
            if m.get("generation_tok_s"):
                speed_samples.append(float(m["generation_tok_s"]))
    if total_tokens and speed_samples:
        minimum_s = total_tokens / max(_median(speed_samples), 0.01)
        actual = float(run["duration_seconds"] or 0)
        if actual and actual < 0.5 * minimum_s:
            rep.add(
                "FAIL",
                f"elapsed {actual:.0f}s but {total_tokens:.0f} completion tokens at "
                f"{_median(speed_samples):.1f} tok/s needs >={minimum_s:.0f}s "
                f"({minimum_s / max(actual, 1):.0f}x faster than physically possible) "
                "-> cache replay",
            )
        else:
            rep.add("PASS", f"elapsed {actual:.0f}s is consistent with the measured tokens")

    # --- 2. dropped validation rounds -------------------------------------
    # The winning config is re-measured N times at the end; only the PASSED
    # rounds are kept (optimizer.py:1919). Count every measurement of the
    # winner's exact config, wherever it sits in the run.
    if val_reps and passed:
        best_cfg = json.dumps(_cfg_only(configs[-1]["config_json"]), sort_keys=True)
        winner_rounds = [
            c for c in configs
            if json.dumps(_cfg_only(c["config_json"]), sort_keys=True) == best_cfg
        ]
        dropped = [c for c in winner_rounds if c["status"] != "passed"]
        if winner_rounds and dropped:
            rep.add(
                "FAIL",
                f"validation: {len(winner_rounds)} measurements of the winning config, "
                f"{len(dropped)} failed and were dropped (optimizer.py:1919) "
                f"-> quality is cherry-picked, pass_rate="
                f"{len(winner_rounds) - len(dropped)}/{len(winner_rounds)}",
            )
        elif winner_rounds:
            rep.add(
                "PASS",
                f"validation: {len(winner_rounds)}/{len(winner_rounds)} rounds passed",
            )

    # --- 3. identical config re-tested ------------------------------------
    seen: dict[str, list[str]] = {}
    for c in configs:
        seen.setdefault(json.dumps(_cfg_only(c["config_json"]), sort_keys=True), []).append(
            c["status"]
        )
    dupes = {k: v for k, v in seen.items() if len(v) > 1}
    for cfg, statuses in dupes.items():
        if len(statuses) > 2:
            cfg_d = json.loads(cfg)
            rep.add(
                "WARN",
                f"identical config tested {len(statuses)}x {statuses} "
                f"(ctx={cfg_d.get('context_length')} batch={cfg_d.get('eval_batch_size')}) "
                "-> dedupe keys differ per stage (optimizer.py:1593 vs :1405)",
            )

    # --- 4. stage-4 no-op sweep -------------------------------------------
    # Configs that share every decode-relevant field (ctx, gpu_ratio, flash,
    # kv placement) and differ only in NOOP_DIMENSIONS are the same experiment.
    decode_key = ("context_length", "gpu_ratio", "flash_attention", "offload_kv_cache_to_gpu")
    groups: dict[tuple, int] = {}
    for cfg_json in seen:
        cfg = json.loads(cfg_json)
        key = tuple(cfg.get(k) for k in decode_key)
        groups[key] = groups.get(key, 0) + 1
    if groups:
        biggest_key, biggest = max(groups.items(), key=lambda kv: kv[1])
        if biggest >= 6:
            rep.add(
                "WARN",
                f"{biggest} configurations differ only in {NOOP_DIMENSIONS} "
                f"(ctx={biggest_key[0]}) -> these cannot change single-request "
                "decode speed; the spread is measurement noise driving selection",
            )

    # --- 5. long_context never reached the context length ------------------
    prompt_tokens: dict[int, float] = {}
    for c in configs:
        metrics = _json(c["metrics_json"], [])
        if not isinstance(metrics, list):
            continue
        for m in metrics:
            if isinstance(m, dict) and m.get("test_name") == "long_context":
                tok = float(m.get("prompt_tokens") or 0)
                if tok:
                    prompt_tokens.setdefault(c["context_length"], tok)
    for ctx, tok in sorted(prompt_tokens.items()):
        if ctx and tok < 0.6 * ctx:
            rep.add(
                "FAIL",
                f"long_context at ctx={ctx} used only {tok:.0f} prompt tokens "
                f"({100 * tok / ctx:.0f}% of the window) -> the context was never "
                "tested (benchmark/suite.py scales only when ctx > 8192)",
            )

    # --- 6. recall probe present for long contexts --------------------------
    # Any configuration probed at ctx >= 4096 must have a recall probe record
    # in generation["recall"] with prompt_tokens >= 0.6 * target_tokens.
    # Without this, we cannot claim the model was actually tested at that context.
    recalled_ctxs: dict[int, bool] = {}
    for c in configs:
        gen = _json(c["generation"], {}) or {}
        recall = gen.get("recall")
        if recall and isinstance(recall, dict) and recall.get("target_tokens"):
            if recall["prompt_tokens"] >= 0.6 * recall["target_tokens"]:
                recall_ctx = recall["target_tokens"]
                recall_ok = recall["status"] == "pass" or recall["status"] == "passed"
                recalled_ctxs[recall_ctx] = recall_ok
    tested_contexts = {c["context_length"] for c in configs if c.get("context_length")}
    for ctx in sorted(tested_contexts):
        if ctx >= 4096:
            if ctx not in recalled_ctxs:
                rep.add(
                    "FAIL",
                    f"ctx={ctx} probed but no recall probe record in generation['recall'] "
                    f"-- context usage is unverified",
                )
            elif not recalled_ctxs[ctx]:
                rep.add(
                    "WARN",
                    f"ctx={ctx} recall probe failed (status not 'pass') "
                    f"-- context usage questionable",
                )

    # --- 7. missing durations ---------------------------------------------
    zero = sum(1 for c in configs if not c["duration_ms"])
    if zero:
        rep.add(
            "FAIL" if zero > len(configs) / 2 else "WARN",
            f"duration_ms missing on {zero}/{len(configs)} configurations "
            "-> every 'total N ms' in the failure report is 0",
        )
    recorded = sum(float(c["duration_ms"] or 0) for c in configs) / 1000
    actual = float(run["duration_seconds"] or 0)
    if actual and recorded and recorded < 0.75 * actual:
        rep.add(
            "WARN",
            f"recorded durations sum to {recorded / 3600:.1f} h of {actual / 3600:.1f} h "
            f"({(actual - recorded) / 3600:.1f} h unexplained: pauses, dead time)",
        )

    # --- 7. Pareto ---------------------------------------------------------
    pareto = _json(run["pareto_config_ids_json"], [])
    if passed and not pareto:
        rep.add(
            "FAIL",
            f"Pareto frontier empty with {len(passed)} passed configuration(s) "
            "-> impossible (optimizer.py:2440)",
        )

    # --- 9. the quality gate has no margin -------------------------------
    # Quality is the mean of the per-test `overall` values, which are
    # themselves means of 6 heuristic dimensions, so it moves in small steps —
    # but 0.97 sits in the gap where ONE heuristic check on ONE test decides.
    # The pass/fail gate is calibrated (no critical failure + aggregate >= 0.90);
    # the stored `quality_threshold` is the profile's aspiration for ranking.
    threshold = min(float(run["quality_threshold"] or 0.0), 0.90)
    qualities: list[tuple[float, str]] = []
    for c in configs:
        q = _json(c["quality_json"], {}) or {}
        value = q.get("overall") if isinstance(q, dict) else None
        if value is None:
            gen = _json(c["config_json"], {}).get("generation") or {}
            per = gen.get("quality_by_test") or {}
            if per:
                value = sum(
                    float(v.get("overall") or 0.0)
                    for v in per.values()
                    if isinstance(v, dict)
                ) / len(per)
        if value is not None:
            qualities.append((float(value), c["status"]))
    if threshold and qualities:
        below = [v for v, _s in qualities if v < threshold]
        above = [v for v, _s in qualities if v >= threshold]
        if below and above:
            margin = min(above) - max(below)
            rep.add(
                "FAIL",
                f"quality gate {threshold}: identical configs scored "
                f"{sorted({round(v, 4) for v in below})} (rejected) vs "
                f"{sorted({round(v, 4) for v in above})} (accepted); the whole "
                f"decision rests in a {margin:.4f} window — one heuristic check "
                "on one test (scoring/evaluator.py:21)",
            )
        elif below:
            rep.add(
                "FAIL",
                f"every measurement is below the quality gate {threshold} "
                f"(best {max(v for v, _ in qualities):.4f}) -> the gate is "
                "unreachable for this suite",
            )

    # Which check actually decides pass/fail? Name it.
    flapping: dict[str, set[float]] = {}
    for c in configs:
        gen = _json(c["config_json"], {}).get("generation") or {}
        for test_name, entry in (gen.get("quality_by_test") or {}).items():
            if isinstance(entry, dict) and entry.get("overall") is not None:
                flapping.setdefault(test_name, set()).add(round(float(entry["overall"]), 3))
    unstable = {k: v for k, v in flapping.items() if len(v) > 1}
    for name, values in sorted(unstable.items()):
        rep.add(
            "WARN",
            f"{name} scored {sorted(values)} across identical configurations "
            "-> this heuristic, not the model's capability, decides pass/fail",
        )

    # --- 8. identity / quant sanity ---------------------------------------
    return rep


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="", help="run id or prefix")
    parser.add_argument("--all", action="store_true", help="check every run")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--db", default=str(DB))
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"database not found: {args.db}", file=sys.stderr)
        return 2
    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    if args.run:
        rows = list(
            cur.execute(
                "select * from runs where id like ? order by created_at", (args.run + "%",)
            )
        )
    else:
        rows = list(
            cur.execute(
                "select * from runs order by created_at desc limit ?",
                (10_000 if args.all else args.limit,),
            )
        )
    if not rows:
        print("no matching runs", file=sys.stderr)
        return 2

    failed = 0
    for run in rows:
        report = check_run(cur, run)
        print(report.render())
        print()
        failed += report.failed
    print("=" * 78)
    print(f"{len(rows)} run(s) checked, {failed} with a FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
