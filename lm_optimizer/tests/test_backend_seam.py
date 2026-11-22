"""Backend seam conformance tests (Task 1) + factory tests (Task 5)."""

from lm_optimizer.backends.base import assert_conforms
from lm_optimizer.backends.llamacpp.client import LlamaCppClient
from lm_optimizer.backends.ollama.client import OllamaClient
from lm_optimizer.cli.main import get_backend_client
from lm_optimizer.config import config
from lm_optimizer.services.host.lm_studio import LMStudioClient


def test_lm_studio_conforms_to_backend_client():
    assert_conforms(LMStudioClient())


def test_backend_factory_defaults_lm_studio():
    assert isinstance(get_backend_client("lm-studio"), LMStudioClient)


def test_backend_factory_ollama():
    assert isinstance(get_backend_client("ollama"), OllamaClient)


def test_backend_factory_llama_cpp_returns_client():
    client = get_backend_client("llama-cpp")
    assert isinstance(client, LlamaCppClient)
    assert client.base_url == config.llamacpp_base_url


def test_backend_factory_llama_cpp_respects_explicit_base_url():
    client = get_backend_client("llama-cpp", base_url="http://127.0.0.1:9999")
    assert isinstance(client, LlamaCppClient)
    assert client.base_url == "http://127.0.0.1:9999"


def test_backend_factory_explicit_arg_beats_global_config(monkeypatch):
    monkeypatch.setattr(config, "backend", "ollama")
    assert isinstance(get_backend_client("lm-studio"), LMStudioClient)
    assert isinstance(get_backend_client(), OllamaClient)


def test_config_backend_defaults():
    from lm_optimizer.config import Config

    cfg = Config()
    assert cfg.backend == "lm-studio"
    assert cfg.ollama_base_url == "http://127.0.0.1:11434"
    assert cfg.llamacpp_base_url == "http://127.0.0.1:8080"
