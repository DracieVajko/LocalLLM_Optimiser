"""Context-speed ladder: planning, measurement, resume and formatting."""

import pytest

from lm_optimizer.services.context_speed import (
    STANDARD_CONTEXT_LADDER,
    format_context_speed,
    measure_context_speed,
    plan_context_speed_ladder,
)


def test_plan_uses_every_standard_rung_when_limit_is_large():
    assert plan_context_speed_ladder(262144) == list(STANDARD_CONTEXT_LADDER)
    assert plan_context_speed_ladder(1_000_000) == list(STANDARD_CONTEXT_LADDER)


def test_plan_clamps_to_the_model_limit():
    assert plan_context_speed_ladder(32768) == [2048, 4096, 8192, 16384, 32768]


def test_plan_keeps_a_tiny_model_limit_as_its_only_rung():
    assert plan_context_speed_ladder(1024) == [1024]


def test_plan_without_a_limit_uses_the_full_ladder():
    assert plan_context_speed_ladder(None) == list(STANDARD_CONTEXT_LADDER)


@pytest.mark.asyncio
async def test_measure_stops_at_first_failure_and_reports_last_pass():
    calls = []

    async def probe(ctx):
        calls.append(ctx)
        if ctx >= 8192:
            return {"ok": False, "tok_s": 0.0, "error": "OOM"}
        return {"ok": True, "tok_s": 1200 / ctx, "ttft_ms": 10}

    report = await measure_context_speed(probe, [2048, 4096, 8192, 16384])

    assert calls == [2048, 4096, 8192]
    assert report["last_passing_context"] == 4096
    assert report["failed_context"] == 8192
    assert report["complete"] is True
    assert report["max_speed_context"] == 2048
    assert len(report["results"]) == 3


@pytest.mark.asyncio
async def test_measure_marks_complete_when_the_whole_ladder_passes():
    async def probe(ctx):
        return {"ok": True, "tok_s": 100.0}

    report = await measure_context_speed(probe, [2048, 4096])

    assert report["complete"] is True
    assert report["failed_context"] is None
    assert report["last_passing_context"] == 4096


@pytest.mark.asyncio
async def test_resume_reuses_completed_rungs_without_reloading():
    calls = []

    async def probe(ctx):
        calls.append(ctx)
        return {"ok": True, "tok_s": 50.0}

    completed = {2048: {"ctx": 2048, "ok": True, "tok_s": 80.0}}
    report = await measure_context_speed(probe, [2048, 4096], completed=completed)

    assert calls == [4096]
    assert [r["ctx"] for r in report["results"]] == [2048, 4096]
    assert report["results"][0]["tok_s"] == 80.0


@pytest.mark.asyncio
async def test_a_recorded_failure_terminates_the_ladder_on_resume():
    calls = []

    async def probe(ctx):
        calls.append(ctx)
        return {"ok": True, "tok_s": 50.0}

    completed = {2048: {"ctx": 2048, "ok": True, "tok_s": 80.0},
                 4096: {"ctx": 4096, "ok": False, "tok_s": 0.0}}
    report = await measure_context_speed(
        probe, [2048, 4096, 8192], completed=completed
    )

    assert calls == []
    assert report["complete"] is True
    assert report["failed_context"] == 4096


@pytest.mark.asyncio
async def test_on_rung_fires_for_each_new_measurement():
    seen = []

    async def probe(ctx):
        return {"ok": True, "tok_s": 10.0}

    async def on_rung(entry, results):
        seen.append((entry["ctx"], len(results)))

    await measure_context_speed(probe, [2048, 4096], on_rung=on_rung)

    assert seen == [(2048, 1), (4096, 2)]


@pytest.mark.asyncio
async def test_probe_crash_is_recorded_as_a_failure_not_raised():
    async def probe(ctx):
        raise RuntimeError("boom")

    report = await measure_context_speed(probe, [2048, 4096])

    assert report["results"][0]["ok"] is False
    assert "boom" in report["results"][0]["error"]
    assert report["complete"] is True


@pytest.mark.asyncio
async def test_retryable_internal_failure_is_reprobed_on_resume():
    calls = []

    async def probe(ctx):
        calls.append(ctx)
        return {"ok": True, "tok_s": 50.0}

    completed = {
        2048: {
            "ctx": 2048,
            "ok": False,
            "tok_s": 0.0,
            "error": "AttributeError: 'BenchmarkService' object has no attribute 'speed_probe'",
        }
    }
    report = await measure_context_speed(probe, [2048, 4096], completed=completed)

    assert calls == [2048, 4096]
    assert report["last_passing_context"] == 4096
    assert report["results"][0]["ok"] is True


@pytest.mark.asyncio
async def test_retryable_exception_is_marked_in_the_report():
    async def probe(ctx):
        raise AttributeError("broken code path")

    report = await measure_context_speed(probe, [2048])

    assert report["results"][0]["retryable"] is True


def test_format_context_speed_lists_speeds_and_failures():
    report = {
        "results": [
            {"ctx": 2048, "ok": True, "tok_s": 25.53},
            {"ctx": 4096, "ok": False, "error": "OOM"},
        ]
    }
    text = "\n".join(format_context_speed(report))
    assert "2048" in text and "25.53 tok/s" in text
    assert "4096" in text and "FAIL" in text
