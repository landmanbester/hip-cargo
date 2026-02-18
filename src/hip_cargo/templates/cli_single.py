"""CLI for <PROJECT_NAME>."""

import typer

app = typer.Typer(no_args_is_help=True)

# Import command at bottom to avoid circular imports.
from <PACKAGE_NAME>.cli.onboard import onboard  # noqa: E402

app.command()(onboard)

__all__ = ["app"]
