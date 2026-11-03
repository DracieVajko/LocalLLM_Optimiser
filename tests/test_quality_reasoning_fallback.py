"""Quality-gate protection: truncated answers get one reasoning-on retry.

Reasoning-first models asked with thinking off can stop mid-sentence. The
quality gate must judge the model's best answer, not a truncated one, so the
benchmark retries that single case once with thinking enabled.
"""

import pytest

from lm_optimizer.domain.models import BenchmarkCase
from lm_optimizer.services.benchmark import BenchmarkService


class _FakeClient:
    """Records calls and replays scripted responses in order."""

    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def model_known_no_reasoning(self, model_id: str) -> bool:
        return False

    async def chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def _reply(text: str = "", thinking: str = "") -> dict:
    return {
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "choices": [{"message": {"content": text}}],
        "thinking_text": thinking,
        "_stats": {},
    }


def _case(name: str = "medium_reasoning", category: str = "reasoning") -> BenchmarkCase:
    return BenchmarkCase(
        name=name,
        category=category,
        prompt="Why is the sky blue?",
        max_tokens=100,
    )


@pytest.mark.asyncio
async def test_truncated_quality_answer_retries_with_reasoning():
    client = _FakeClient(
        [
            _reply("Because of Rayleigh"),  # cut off mid-sentence
            _reply("Because of Rayleigh scattering.", thinking="step 1..."),
        ]
    )
    service = BenchmarkService(client)

    metrics = await service._run_single_case("m", _case(), reasoning="off")

    assert len(client.calls) == 2
    assert client.calls[0]["reasoning"] == "off"
    assert client.calls[1]["reasoning"] == "on"
    # Retry gets headroom for the thinking trace.
    assert client.calls[1]["max_output_tokens"] == 200
    assert metrics.output_text.endswith("scattering.")
    assert "step 1" in metrics.thinking_text


@pytest.mark.asyncio
async def test_complete_answer_is_not_retried():
    client = _FakeClient([_reply("Because of Rayleigh scattering.")])
    service = BenchmarkService(client)

    metrics = await service._run_single_case("m", _case(), reasoning="off")

    assert len(client.calls) == 1
    assert metrics.output_text.endswith("scattering.")


@pytest.mark.asyncio
async def test_incomplete_retry_that_stays_incomplete_keeps_first_answer():
    client = _FakeClient([_reply("Because of Rayleigh"), _reply("Still think")])
    service = BenchmarkService(client)

    metrics = await service._run_single_case("m", _case(), reasoning="off")

    assert len(client.calls) == 2
    assert metrics.output_text == "Because of Rayleigh"


@pytest.mark.asyncio
async def test_fallback_can_be_disabled():
    client = _FakeClient([_reply("Because of Rayleigh")])
    service = BenchmarkService(client, quality_reasoning_fallback=False)

    await service._run_single_case("m", _case(), reasoning="off")

    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_speed_category_is_never_retried_for_incompleteness():
    client = _FakeClient([_reply("Token stream without closing punctuation")])
    service = BenchmarkService(client)

    await service._run_single_case("m", _case("speed_probe", "speed"), reasoning="off")

    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_empty_answer_still_retries_with_reasoning():
    client = _FakeClient([_reply(""), _reply("Answer with reasoning.", thinking="t")])
    service = BenchmarkService(client)

    metrics = await service._run_single_case("m", _case(), reasoning="off")

    assert len(client.calls) == 2
    assert client.calls[1]["reasoning"] == "on"
    assert metrics.output_text == "Answer with reasoning."


@pytest.mark.asyncio
async def test_known_no_reasoning_model_is_not_retried():
    class _NoReasoningClient(_FakeClient):
        def model_known_no_reasoning(self, model_id: str) -> bool:
            return True

    client = _NoReasoningClient([_reply("Because of Rayleigh")])
    service = BenchmarkService(client)

    await service._run_single_case("m", _case(), reasoning="off")

    assert len(client.calls) == 1
