#!/usr/bin/env python3
"""Web UI entry point for LM Studio Optimizer."""

import os

import uvicorn

from lm_optimizer.config import config
from lm_optimizer.logging_config import setup_logging

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _check_host_exposure() -> None:
    """Refuse a non-loopback bind unless the operator opted in explicitly.

    The API has no authentication, so exposing it on a LAN interface must be
    a deliberate choice rather than a config side effect.
    """
    host = config.web_ui.host
    if host in _LOOPBACK_HOSTS:
        return
    if os.environ.get("LM_OPTIMIZER_ALLOW_REMOTE") == "1":
        return
    raise SystemExit(
        f"Refusing to bind the unauthenticated web UI to {host!r}. "
        "Use 127.0.0.1, or set LM_OPTIMIZER_ALLOW_REMOTE=1 to accept the risk."
    )


if __name__ == "__main__":
    _check_host_exposure()
    setup_logging()
    uvicorn.run(
        "lm_optimizer.api.main:app",
        host=config.web_ui.host,
        port=config.web_ui.port,
        log_level="info",
        reload=False,
    )
