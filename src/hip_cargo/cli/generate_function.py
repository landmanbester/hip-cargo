"""CLI command for generating Python functions from Stimela cab definitions."""

from pathlib import Path
from typing import NewType

import typer
from typing_extensions import Annotated

from hip_cargo.utils.decorators import stimela_cab, stimela_output

File = NewType("File", Path)


@stimela_cab(
    name="hip_cargo_generate_function",
    info="Generate Python function from Stimela cab definition",
)
@stimela_output(
    dtype="File",
    name="output-file",
    info="Name of output CLI function",
    required=True,
)
def generate_function(
    cab_file: Annotated[
        File, typer.Option(..., parser=Path, help="Path to Stimela cab YAML file", rich_help_panel="Inputs")
    ],
    output_file: Annotated[
        File,
        typer.Option(
            parser=Path,
            help="Name of output CLI function (prints to stdout if not specified)",
            rich_help_panel="Outputs",
        ),
    ] = None,
    config_file: Annotated[
        File | None,
        typer.Option(
            parser=Path,
            help="Optional path to ruff config file to use when generating function",
            rich_help_panel="Inputs",
        ),
    ] = None,
):
    """Generate a Python function from a Stimela cab definition.

    This reverse-engineers a cab YAML file to create a Python function
    with @stimela_cab decorators. Useful for migrating existing cabs
    to the hip-cargo pattern.
    """
    # Lazy import core logic
    from hip_cargo.core.generate_function import generate_function as generate_function_core  # noqa: E402

    # Validate input
    if not cab_file.exists():
        typer.secho(
            f"✗ Error: Cab file not found: {cab_file}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    # User feedback
    typer.echo(f"Reading cab definition from: {cab_file}")

    # Call core logic
    generate_function_core(cab_file, output_file, config_file)
