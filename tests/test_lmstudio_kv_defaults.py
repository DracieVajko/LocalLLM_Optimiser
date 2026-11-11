"""Reading the KV-cache quantization and threads LM Studio will apply."""

from __future__ import annotations

import json
from pathlib import Path

from lm_optimizer.services import lmstudio_defaults as defaults


def _home_with(tmp_path: Path, model: str, fields: list[dict]) -> Path:
    home = tmp_path / "lmstudio"
    internal = home / ".internal"
    (internal / "user-concrete-model-default-config" / "publisher").mkdir(parents=True)
    (internal / "model-data.json").write_text(
        json.dumps({"json": [["publisher/model.gguf", {"uiIdentifier": model}]]}),
        encoding="utf-8",
    )
    (internal / "user-concrete-model-default-config" / "publisher" / "model.gguf.json").write_text(
        json.dumps({"preset": "", "operation": {"fields": []}, "load": {"fields": fields}}),
        encoding="utf-8",
    )
    return home


def _field(key: str, value) -> dict:
    return {"key": key, "value": value}


def test_reads_kv_quantization_and_threads(tmp_path):
    home = _home_with(
        tmp_path,
        "model",
        [
            _field("llm.load.llama.kCacheQuantizationType", {"checked": True, "value": "q8_0"}),
            _field("llm.load.llama.vCacheQuantizationType", {"checked": True, "value": "q8_0"}),
            _field("llm.load.llama.cpuThreadPoolSize", 8),
        ],
    )
    assert defaults.read_load_defaults("model", home=home) == {
        "kv_quant": "q8_0",
        "threads": 8,
    }


def test_reports_split_k_and_v_settings(tmp_path):
    home = _home_with(
        tmp_path,
        "model",
        [
            _field("llm.load.llama.kCacheQuantizationType", {"checked": True, "value": "q8_0"}),
            _field("llm.load.llama.vCacheQuantizationType", {"checked": True, "value": "q4_0"}),
        ],
    )
    assert defaults.read_load_defaults("model", home=home)["kv_quant"] == "k:q8_0/v:q4_0"


def test_disabled_quantization_is_not_reported(tmp_path):
    home = _home_with(
        tmp_path,
        "model",
        [
            _field("llm.load.llama.kCacheQuantizationType", {"checked": False, "value": "q8_0"}),
            _field("llm.load.llama.cpuThreadPoolSize", 8),
        ],
    )
    assert defaults.read_load_defaults("model", home=home) == {"threads": 8}


def test_missing_model_returns_empty(tmp_path):
    assert defaults.read_load_defaults("nope", home=tmp_path / "empty") == {}
