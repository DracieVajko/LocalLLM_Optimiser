"""CLI command: check (and optionally apply) GitHub updates."""

from __future__ import annotations

import typer
from rich.console import Console

from lm_optimizer.services.updater import apply_update, check_update

console = Console()


def update(
    apply: bool = typer.Option(False, "--apply", help="Download and apply the update."),
    target: str = typer.Option(".", "--target", help="Project root to update."),
):
    """Check GitHub for a newer version of LM Studio Optimizer."""
    info = check_update()
    console.print(f"Current version: [bold]{info.current}[/bold]")
    if info.error:
        console.print(f"[red]Error: {info.error}[/red]")
        return
    console.print(f"Latest version:  [bold]{info.latest or 'unknown'}[/bold] ({info.source})")
    if not info.update_available:
        console.print("[green]You are up to date.[/green]")
        return
    console.print(f"[yellow]UPDATE AVAILABLE: {info.current} -> {info.latest}[/yellow]")
    console.print(f"URL: {info.url}")
    if info.notes:
        console.print(f"Notes: {info.notes[:400]}")
    if apply:
        console.print("\n[bold]Applying update...[/bold]")
        result = apply_update(target_dir=target)
        if result.get("success"):
            console.print(f"[green]Updated {result['from']} -> {result['to']}[/green]")
            console.print(f"Backup: {result.get('backup')}")
        else:
            console.print(f"[red]Update failed: {result.get('reason')}[/red]")
    else:
        console.print("\nRun with --apply to download and install.")
