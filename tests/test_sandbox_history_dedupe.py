from __future__ import annotations

import json
from pathlib import Path

from lm_optimizer.services import sandbox_history as sh


def test_cli_and_bakeoff_settings_fingerprint_identically():
    cli = sh.settings_from_reasoning("off", context_length=8192, max_output_tokens=2048)
    bakeoff = sh.normalize_settings(
        temperature=0.0,
        max_output_tokens=2048,
        thinking=False,
        reasoning_effort="on",
        context_length=8192,
    )
    assert sh.fingerprint("m", "email_write", "do it", cli) == sh.fingerprint(
        "m", "email_write", "do it", bakeoff
    )


def test_fingerprint_changes_with_every_setting():
    base = sh.normalize_settings(context_length=8192)
    variants = [
        sh.normalize_settings(context_length=4096),
        sh.normalize_settings(context_length=8192, thinking=True),
        sh.normalize_settings(context_length=8192, reasoning_effort="high"),
        sh.normalize_settings(context_length=8192, kv_ram=True),
        sh.normalize_settings(context_length=8192, safe=True),
        sh.normalize_settings(context_length=8192, temperature=0.2),
    ]
    keys = {sh.fingerprint("m", "t", "p", s) for s in variants}
    assert len(keys) == len(variants)
    assert sh.fingerprint("m", "t", "p", base) not in keys
    assert sh.fingerprint("m", "t", "other", base) != sh.fingerprint("m", "t", "p", base)


def _result(score=1.0, status="measured"):
    return {
        "status": status,
        "first_pass_success": score == 1.0,
        "final_success": score == 1.0,
        "repair_count": 0,
        "final_score": score if status == "measured" else None,
        "penalized_score": score if status == "measured" else None,
        "artifacts": ["out.txt"],
        "critical_failures": [],
        "error": "",
    }


def test_measured_rerun_replaces_and_deletes_old_workdir(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "RESULTS_ROOT", tmp_path)
    history = tmp_path / "runs.jsonl"
    old = tmp_path / "sandbox" / "email_write" / "old"
    new = tmp_path / "sandbox" / "email_write" / "new"
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    settings = sh.normalize_settings(context_length=8192)

    sh.record_run(
        "m", "email_write", _result(), workdir=str(old), duration_s=1,
        path=history, prompt="p", settings=settings,
    )
    sh.record_run(
        "m", "email_write", _result(0.5), workdir=str(new), duration_s=1,
        path=history, prompt="p", settings=settings,
    )

    rows = sh.list_runs(10, path=history)
    assert len(rows) == 1
    assert rows[0]["final_score"] == 0.5
    assert not old.exists()
    assert new.exists()


def test_not_measured_rerun_keeps_the_old_record(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "RESULTS_ROOT", tmp_path)
    history = tmp_path / "runs.jsonl"
    settings = sh.normalize_settings()
    sh.record_run("m", "t", _result(1.0), path=history, prompt="p", settings=settings)
    sh.record_run(
        "m", "t", _result(status="not_measured"), path=history,
        prompt="p", settings=settings,
    )
    assert [r["status"] for r in sh.list_runs(10, path=history)] == [
        "not_measured",
        "measured",
    ]


def test_different_settings_or_prompt_coexist(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "RESULTS_ROOT", tmp_path)
    history = tmp_path / "runs.jsonl"
    sh.record_run(
        "m", "t", _result(), path=history, prompt="p",
        settings=sh.normalize_settings(context_length=8192),
    )
    sh.record_run(
        "m", "t", _result(), path=history, prompt="p",
        settings=sh.normalize_settings(context_length=4096),
    )
    sh.record_run(
        "m", "t", _result(), path=history, prompt="different",
        settings=sh.normalize_settings(context_length=8192),
    )
    assert len(sh.list_runs(10, path=history)) == 3


def test_workdir_outside_results_is_never_deleted(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "RESULTS_ROOT", tmp_path / "results")
    outside = tmp_path / "precious"
    outside.mkdir()
    history = tmp_path / "runs.jsonl"
    settings = sh.normalize_settings()
    sh.record_run(
        "m", "t", _result(), workdir=str(outside), path=history,
        prompt="p", settings=settings,
    )
    sh.record_run("m", "t", _result(), workdir="", path=history, prompt="p", settings=settings)
    assert outside.exists()


def test_malformed_line_survives_rewrite(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "RESULTS_ROOT", tmp_path)
    history = tmp_path / "runs.jsonl"
    settings = sh.normalize_settings()
    sh.record_run("m", "t", _result(), path=history, prompt="p", settings=settings)
    with history.open("a", encoding="utf-8") as handle:
        handle.write("not json\n")
    sh.record_run("m", "t", _result(), path=history, prompt="p", settings=settings)
    text = history.read_text(encoding="utf-8")
    assert "not json" in text
    assert sum(1 for line in text.splitlines() if line.startswith("{")) == 1


def _row(model, task, *, key=None, status="measured", score=1.0,
         ts="2026-01-01T00:00:00", workdir=""):
    return {
        "model": model,
        "task": task,
        "run_key": key,
        "status": status,
        "final_score": score if status == "measured" else None,
        "ts": ts,
        "workdir": workdir,
    }


def test_cli_settings_include_the_effective_context():
    settings = sh.settings_from_reasoning(
        "off", context_length=8192, max_output_tokens=2048
    )
    assert settings["thinking"] is False
    assert settings["context_length"] == 8192
    assert settings["reasoning_effort"] is None
    high = sh.settings_from_reasoning(
        "high", context_length=8192, max_output_tokens=2048
    )
    assert high["thinking"] is True
    assert high["reasoning_effort"] == "high"


def test_prune_dry_run_does_not_touch_the_file(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "RESULTS_ROOT", tmp_path)
    path = tmp_path / "runs.jsonl"
    rows = [_row("m", "t", ts="1"), _row("m", "t", ts="2")]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    report = sh.prune_history(path, apply=False)
    assert report["removed"] == 1
    assert path.read_text(encoding="utf-8") == before


def test_prune_apply_keeps_newest_measured_per_group(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "RESULTS_ROOT", tmp_path)
    path = tmp_path / "runs.jsonl"
    rows = [
        _row("m", "t", key="rk1:a", ts="1"),
        _row("m", "t", key="rk1:a", ts="2", status="not_measured"),
        _row("m", "t", key="rk1:a", ts="3"),
        _row("m", "t", key="rk1:b", ts="4"),
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    report = sh.prune_history(path, apply=True)
    kept = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert report["removed"] == 2
    assert [(r["run_key"], r["ts"]) for r in kept] == [("rk1:a", "3"), ("rk1:b", "4")]


def test_prune_keeps_load_and_crash_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "RESULTS_ROOT", tmp_path)
    path = tmp_path / "runs.jsonl"
    rows = [
        _row("m", "(load)", ts="1"),
        _row("m", "(load)", ts="2"),
        _row("m", "(crash)", ts="3"),
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert sh.prune_history(path, apply=True)["removed"] == 0


def test_prune_drops_legacy_rows_once_a_keyed_row_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "RESULTS_ROOT", tmp_path)
    path = tmp_path / "runs.jsonl"
    rows = [_row("m", "t", ts="1"), _row("m", "t", key="rk1:a", ts="2")]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    sh.prune_history(path, apply=True)
    kept = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [r["run_key"] for r in kept] == ["rk1:a"]
