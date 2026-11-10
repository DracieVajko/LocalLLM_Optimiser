"""Tests for the sandbox/duel matrix CLI helpers (no server needed)."""

from __future__ import annotations

import json

import pytest

from lm_optimizer.cli.lab import (
    _load_prompt_overrides,
    _resolve_duel_task_ids,
    _resolve_models,
    _resolve_tasks,
)


class TestResolveTasks:
    def test_all_returns_every_known_task(self):
        available = ["a", "b", "c"]
        assert _resolve_tasks("all", available) == ["a", "b", "c"]

    def test_none_means_all(self):
        assert _resolve_tasks(None, ["x", "y"]) == ["x", "y"]

    def test_comma_list_preserved(self):
        assert _resolve_tasks("b,c", ["a", "b", "c"]) == ["b", "c"]

    def test_glob(self):
        assert _resolve_tasks("company_*", ["company_website", "email_write"]) == [
            "company_website"
        ]


class TestResolveModels:
    def test_comma_list_does_not_need_a_server(self):
        assert _resolve_models("a,b,c") == ["a", "b", "c"]

    def test_single_id(self):
        assert _resolve_models("qwen3.8-9b-distill") == ["qwen3.8-9b-distill"]

    def test_empty_spec_falls_back_to_all(self):
        # "all" hits LM Studio; monkeypatch the lister to keep this offline.
        import lm_optimizer.cli.lab as lab

        original = lab._available_model_ids
        lab._available_model_ids = lambda: ["m1", "m2"]
        try:
            assert _resolve_models("all") == ["m1", "m2"]
            assert _resolve_models("") == ["m1", "m2"]
        finally:
            lab._available_model_ids = original


class TestPromptOverrides:
    def test_missing_file_returns_empty(self):
        assert _load_prompt_overrides(None) == {}

    def test_valid_mapping(self, tmp_path):
        path = tmp_path / "prompts.json"
        path.write_text(json.dumps({"company_website": "Build X"}), encoding="utf-8")
        assert _load_prompt_overrides(path) == {"company_website": "Build X"}

    def test_non_object_rejected(self, tmp_path):
        path = tmp_path / "prompts.json"
        path.write_text(json.dumps(["not", "a", "map"]), encoding="utf-8")
        with pytest.raises(ValueError):
            _load_prompt_overrides(path)

    def test_invalid_json_rejected(self, tmp_path):
        path = tmp_path / "prompts.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(ValueError):
            _load_prompt_overrides(path)


class TestResolveDuelTasks:
    def test_default_uses_type_set(self):
        dt, ids = _resolve_duel_task_ids("micro_quality", None)
        assert dt.value == "micro_quality"
        assert ids == ["instruction_list_three", "reasoning_arithmetic"]

    def test_explicit_tasks_override(self):
        _dt, ids = _resolve_duel_task_ids("micro_quality", "company_website,email_write")
        assert ids == ["company_website", "email_write"]

    def test_unknown_type_rejected(self):
        with pytest.raises(ValueError):
            _resolve_duel_task_ids("nope", None)
