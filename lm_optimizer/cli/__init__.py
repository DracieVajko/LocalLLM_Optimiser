"""Command-line interface package.

Import the Typer app from ``lm_optimizer.cli.main`` directly; this package
deliberately does not re-export it so importing a CLI submodule does not
initialize the whole command tree (and does not create an import cycle).
"""
