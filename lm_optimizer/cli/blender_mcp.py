"""CLI command: seamless Blender MCP setup."""

from __future__ import annotations

import json
import typer
from rich.console import Console

from lm_optimizer.services.blender_mcp import seamless_setup

console = Console()


def blender_mcp(
    write_config: bool = typer.Option(
        False, "--write-config", help="Write the MCP config snippet to ./blender_mcp.json"
    ),
):
    """Detect Blender + MCP-Link + LM Studio and print the MCP config.

    Zero setup: auto-detects everything and prints a ready-to-paste config.
    """
    result = seamless_setup()
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
    console.print("\n[bold]MCP config (paste into LM Studio):[/bold]")
    console.print(json.dumps(result["config"], indent=2))
    if write_config:
        import pathlib
        out = pathlib.Path("blender_mcp.json")
        out.write_text(json.dumps(result["config"], indent=2), encoding="utf-8")
        console.print(f"\nWrote {out}")
    console.print("\n[dim]Then start a model and ask it to build a 3D scene.[/dim]")
    console.print("[dim]See docs/BLENDER_MCP.md for details.[/dim]")
