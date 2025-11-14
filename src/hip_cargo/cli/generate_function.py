"""CLI command for generating Python functions from Stimela cab definitions."""

from pathlib import Path

import typer
from typing_extensions import Annotated

from hip_cargo.utils.decorators import stimela_cab


@stimela_cab(
    name="hip_cargo_generate_function",
    info="Generate Python function from Stimela cab definition",
)
def generate_function(
    cab_file: Annotated[Path, typer.Argument(help="Path to Stimela cab YAML file", rich_help_panel="Inputs")],
    output: Annotated[
        Path,
        typer.Option(
            "--output", "-o", help="Output Python file (prints to stdout if not specified)", rich_help_panel="Outputs"
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
    generate_function_core(str(cab_file), str(output) if output else None)

    # Success message (only if writing to file)
    if output:
        typer.secho(
            f"✓ Successfully generated Python function: {output}",
            fg=typer.colors.GREEN,
        )
