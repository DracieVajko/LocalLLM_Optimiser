"""CLI command: seamless Blender MCP setup."""

from __future__ import annotations

import json
import typer
from rich.console import Console

from lm_optimizer.services.blender_mcp import seamless_setup

console = Console()


def blender_mcp(
    apply: bool = typer.Option(
        False, "--apply", help="Write the MCP config directly into ~/.lmstudio/mcp.json"
    ),
):
    """Detect Blender + MCP-Link + LM Studio and print the MCP config.

    Zero setup: auto-detects everything. With --apply, writes the config
    into LM Studio's mcp.json automatically (no copy-paste needed).
    """
    result = seamless_setup(apply=apply)
    status = result["status"]
    console.print("\n[bold]Blender MCP status[/bold]")
    for step in status["steps"]:
        badge = "[green]OK[/green]" if step["status"] == "ok" else "[red]MISSING[/red]"
        console.print(f"  {step['step']}: {badge} — {step['detail']}")
    console.print()
    if result["ready"]:
        console.print("[green]All dependencies detected. Ready to go.[/green]")
    else:
        console.print("[yellow]Missing dependencies:[/yellow]")
        for inst in result["instructions"]:
            console.print(f"  • {inst}")
    if "apply" in result:
        ap = result["apply"]
        if ap.get("success"):
            console.print(f"\n[green]Wrote config to {ap['path']}[/green]")
            console.print(f"Servers: {ap.get('servers')}")
        else:
            console.print(f"\n[red]Failed to write config: {ap.get('error')}[/red]")
    console.print("\n[bold]MCP config:[/bold]")
    console.print(json.dumps(result["config"], indent=2))
    # (write_config removed: --apply writes directly to ~/.lmstudio/mcp.json)
    console.print("\n[dim]Then start a model and ask it to build a 3D scene.[/dim]")
    console.print("[dim]See docs/BLENDER_MCP.md for details.[/dim]")
