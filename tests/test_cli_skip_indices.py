"""Numbered skip list must match the order shown by `models --full-ids`."""

from types import SimpleNamespace

from lm_optimizer.cli.main import _display_models_small_first, _resolve_skip_indices


def _m(mid: str, size: int | None):
    return SimpleNamespace(id=mid, size_bytes=size)


def test_display_order_is_small_first_with_id_tiebreak():
    models = [_m("big", 30), _m("small", 1), _m("mid-b", 10), _m("mid-a", 10)]
    assert [m.id for m in _display_models_small_first(models)] == [
        "small",
        "mid-a",
        "mid-b",
        "big",
    ]


def test_resolve_indices_uses_the_same_order():
    models = [_m("big", 30), _m("small", 1), _m("mid", 10)]
    # 1 = small, 2 = mid, 3 = big
    terms, errors = _resolve_skip_indices(models, ["1", "3"])
    assert terms == ["small", "big"]
    assert errors == []


def test_resolve_indices_keeps_substrings_and_reports_out_of_range():
    models = [_m("qwen3.6-35b", 20), _m("bonsai", 5)]
    terms, errors = _resolve_skip_indices(models, ["swift", "9"])
    assert terms == ["swift"]
    assert errors == ["9"]


def test_missing_size_sorts_last():
    models = [_m("unknown", None), _m("known", 100)]
    assert [m.id for m in _display_models_small_first(models)] == ["known", "unknown"]
