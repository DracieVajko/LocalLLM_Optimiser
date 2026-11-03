#!/usr/bin/env python3
"""Web UI entry point for LM Studio Optimizer."""

import os

import uvicorn

from lm_optimizer.config import config
from lm_optimizer.logging_config import setup_logging

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _check_host_exposure() -> None:
    """Refuse a non-loopback bind unless remote mode and a token are set.

    The API has no user login. A non-loopback bind is allowed only with
    ``LM_OPTIMIZER_ALLOW_REMOTE=1`` and ``LM_OPTIMIZER_API_TOKEN``; the token
    middleware then requires the token on mutating requests from non-loopback
    clients.
    """
    host = config.web_ui.host
    if host in _LOOPBACK_HOSTS:
        return
    if os.environ.get("LM_OPTIMIZER_ALLOW_REMOTE") != "1":
        raise SystemExit(
            f"Refusing to bind the unauthenticated web UI to {host!r}. "
            "Use 127.0.0.1, or set LM_OPTIMIZER_ALLOW_REMOTE=1 to accept the risk."
        )
    if not os.environ.get("LM_OPTIMIZER_API_TOKEN"):
        raise SystemExit(
            "Refusing a remote bind without LM_OPTIMIZER_API_TOKEN. "
            "Set a token so mutating API calls from non-loopback clients are authenticated."
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
