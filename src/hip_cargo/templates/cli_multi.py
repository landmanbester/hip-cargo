"""CLI for <PROJECT_NAME>."""

import typer

app = typer.Typer(
    name="<CLI_COMMAND>",
    help="<DESCRIPTION>",
    no_args_is_help=True,
)


@app.callback()
def callback() -> None:
    """<DESCRIPTION>"""
    pass


# Register subcommands below. Imports go here (bottom) to avoid circular imports.
from <PACKAGE_NAME>.cli.onboard import onboard  # noqa: E402

app.command(name="onboard")(onboard)

__all__ = ["app"]
