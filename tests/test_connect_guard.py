"""Connect sequencing: load-free handshake, clean host, then echo probe."""

import asyncio

import httpx
import pytest

from lm_optimizer.cli import host_lifecycle
from lm_optimizer.cli import main as cli_main
from lm_optimizer.services.host.hostguard import HostUnreachableError


class _FakeClient:
    def __init__(self, fail_echo: bool = False):
        self.base_url = "http://127.0.0.1:1234"
        self.fail_echo = fail_echo
        self.calls: list[bool] = []

    async def connect(self, echo_probe: bool = True) -> None:
        self.calls.append(echo_probe)
        if echo_probe and self.fail_echo and len(self.calls) > 1:
            raise RuntimeError("probe load refused")


def test_connect_is_load_free_before_host_cleanup(monkeypatch):
    events: list[tuple[str, object]] = []

    client = _FakeClient()

    async def fake_prepare(c, **kwargs):
        events.append(("prepare", client.calls[-1]))
        return {"verified_empty": True}

    monkeypatch.setattr(host_lifecycle, "prepare_host", fake_prepare)

    snap = asyncio.run(cli_main._connect_guarded(client, "optimize"))

    assert snap == {"verified_empty": True}
    # The echo probe must run only after prepare_host evicted leftovers.
    assert client.calls == [False, True]
    assert events == [("prepare", False)]


def test_echo_probe_failure_is_logged_not_fatal(monkeypatch):
    client = _FakeClient(fail_echo=True)

    async def fake_prepare(c, **kwargs):
        return {"verified_empty": True}

    monkeypatch.setattr(host_lifecycle, "prepare_host", fake_prepare)

    snap = asyncio.run(cli_main._connect_guarded(client, "auto"))

    assert snap == {"verified_empty": True}
    assert client.calls == [False, True]


def test_connection_failure_is_wrapped(monkeypatch):
    class _Down:
        base_url = "http://127.0.0.1:1234"

        async def connect(self, echo_probe: bool = True):
            raise httpx.ConnectError("refused")

    async def fake_prepare(c, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("prepare_host must not run when connect fails")

    monkeypatch.setattr(host_lifecycle, "prepare_host", fake_prepare)

    with pytest.raises(HostUnreachableError):
        asyncio.run(cli_main._connect_guarded(_Down(), "optimize"))
