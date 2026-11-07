"""CLI host lifecycle: guarded connect, busy/unreachable messages.
These helpers were previously embedded in ``cli/main.py``. They are kept in
the CLI layer (not services) because they render user-facing messages, but
they no longer live in the 5.7k-LOC command module.
"""
from __future__ import annotations
import sys
from rich.console import Console
from lm_optimizer.config import config
from lm_optimizer.logging_config import get_logger
from lm_optimizer.services.host.hostguard import (
    HostBusyTimeout,
    HostUnreachableError,
    is_connection_error,
    prepare_host,
)
console = Console()
logger = get_logger(__name__)
def client_base_url(client) -> str:
    """Backend URL for messages (never raises)."""
    return getattr(client, "base_url", None) or config.lm_studio.base_url
def handle_connection_error(url: str, error: Exception) -> None:
    """User-friendly connection error without exposing secrets."""
    console.print("\n[red]Cannot connect to LM Studio at:[/red]")
    console.print(f"  {url}")
    console.print("\n[bold]Check:[/bold]")
    console.print("  - LM Studio is running")
    console.print("  - Developer API is enabled (LM Studio -> Settings -> Developer)")
    console.print("  - URL/port is correct")
    console.print("  - Network access is allowed (firewall/VPN)")
    console.print(f"\n[dim]Details: {type(error).__name__}[/dim]")
def busy_blockers(exc: HostBusyTimeout) -> str:
    """Blocker model ids for messages (never empty)."""
    return ", ".join(str(b) for b in (exc.blocker or [])) or "unknown model"
def print_host_busy_abort(exc: HostBusyTimeout) -> None:
    """Clear abort message for a persistently busy host."""
    console.print(f"[red]Host busy: {busy_blockers(exc)} still loaded; aborting.[/red]")
    console.print(f"  {exc}")
    console.print("Unload the model in LM Studio (disable Keep Model in Memory) and retry.")
def print_host_busy_paused(model: str, exc: HostBusyTimeout) -> None:
    """Pause-framed busy message for optimize, with a resume hint."""
    console.print(
        f"[yellow]Host busy: {busy_blockers(exc)} still loaded "
        "- pausing before start.[/yellow]"
    )
    console.print(f"  {exc}")
    console.print("Nothing was started, so no checkpoint was needed.")
    console.print("Unload the model in LM Studio (disable Keep Model in Memory),")
    console.print(f"then re-run: lm-optimizer optimize {model}")
    console.print("In-progress runs resume with: lm-optimizer resume <run-id>")
    console.print("  (list them with: lm-optimizer checkpoints)")
async def connect_guarded(
    client, purpose: str, wait_interval_s: float = 60.0, max_waits: int = 30
):
    """Connect + exclusive-access guard with typed failures."""
    try:
        # Load-free first: a leftover/foreign model blocks the echo-probe load
        # behind it (observed live 2026-11-03: a stale Bonsai kept the probe
        # waiting until the load timeout). Clean the host, then probe.
        await client.connect(echo_probe=False)
    except Exception as e:
        if is_connection_error(e):
            raise HostUnreachableError(
                f"Cannot reach backend at {client_base_url(client)}", cause=e
            ) from e
        raise
    snapshot = await prepare_host(
        client,
        purpose=purpose,
        wait_interval_s=wait_interval_s,
        max_waits=max_waits,
    )
    try:
        # Upgrade to the echo probe only on a clean host. The run's own loads
        # verify configs too, so a probe failure is logged, never fatal.
        await client.connect()
    except Exception as e:
        logger.warning("Echo probe after host cleanup failed", error=str(e)[:160])
    return snapshot
async def connect_guarded_or_abort(
    client, purpose: str, wait_interval_s: float = 60.0, max_waits: int = 30
):
    """connect_guarded that aborts (exit 1) with a clear message."""
    try:
        return await connect_guarded(client, purpose, wait_interval_s, max_waits)
    except HostBusyTimeout as e:
        print_host_busy_abort(e)
        sys.exit(1)
    except HostUnreachableError as e:
        handle_connection_error(client_base_url(client), e.cause or e)
        sys.exit(1)
__all__ = [
    "busy_blockers",
    "client_base_url",
    "connect_guarded",
    "connect_guarded_or_abort",
    "handle_connection_error",
    "print_host_busy_abort",
    "print_host_busy_paused",
]