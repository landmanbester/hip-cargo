"""CLI command for generating Stimela cab definitions."""

from pathlib import Path

import typer
from rich import print
from typing_extensions import Annotated

from hip_cargo.utils.decorators import stimela_cab, stimela_output


@stimela_cab(
    name="hip_cargo_generate_cab",
    info="Generate Stimela cab definition from Python CLI function",
)
@stimela_output(
    dtype="File",
    name="output_name",
    info="Path to output Stimela cab YAML file",
    required=True,
)
def generate_cab(
    module: Annotated[
        str,
        typer.Argument(
            help="Python module path (e.g., package.module)",
            rich_help_panel="Inputs",
        ),
    ],
    output_name: Annotated[
        Path,
        typer.Argument(help="Output YAML file path (e.g., /path/to/cab.yaml)", rich_help_panel="Outputs"),
    ],
    end_message: Annotated[str, typer.Option(hidden=True)] = "✓ Successfully generated cab definition",
):
    """Generate a Stimela cab definition from a Python module.

    The module should contain a single Typer command decorated with
    @stimela_cab and optionally @stimela_output decorators.
    """
    # Lazy import core logic
    from hip_cargo.core.generate_cab import generate_cab as generate_cab_core  # noqa: E402

    # User feedback
    typer.echo(f"Loading module: {module}")

    # Import module to get function name for better user feedback
    from hip_cargo.utils.introspector import get_function_from_module  # noqa: E402

    func, _ = get_function_from_module(module)
    cab_name = func.__stimela_cab_config__["name"]

    typer.echo(f"Found decorated function: {func.__name__}")
    typer.echo(f"Extracting cab definition for: {cab_name}")
    typer.echo("Generating YAML...")
    typer.echo(f"Writing to: {output_name}")

    # Call core logic
    generate_cab_core(module, str(output_name))

    # Success message
    print(f":boom: [green] {end_message}: {output_name} [/green]")
