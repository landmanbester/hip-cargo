"""CLI application for hip-cargo."""

from pathlib import Path

import typer

from hip_cargo.introspector import (
    extract_cab_info,
    extract_inputs,
    extract_outputs,
    get_function_from_module,
)
from hip_cargo.yaml_generator import generate_cab_yaml, write_cab_yaml

app = typer.Typer(
    name="cargo",
    help="Tools for generating Stimela cab definitions from Python functions",
    no_args_is_help=True,
)


@app.callback()
def callback():
    """hip-cargo: Generate Stimela cab definitions from Python functions."""
    pass


@app.command()
def generate_cab(
    module: str = typer.Argument(
        ...,
        help="Python module path (e.g., package.module)",
    ),
    output: Path = typer.Argument(
        ...,
        help="Output YAML file path (e.g., /path/to/cab.yaml)",
    ),
):
    """
    Generate a Stimela cab definition from a Python module.

    The module should contain a single Typer command decorated with
    @stimela_cab and optionally @stimela_output decorators.
    """
    try:
        # Import the module and find the decorated function
        typer.echo(f"Loading module: {module}")
        func, module_path = get_function_from_module(module)

        # Extract cab information
        typer.echo(f"Found decorated function: {func.__name__}")
        cab_config = func.__stimela_cab_config__
        cab_name = cab_config["name"]

        typer.echo(f"Extracting cab definition for: {cab_name}")
        cab_info = extract_cab_info(func)
        inputs = extract_inputs(func)
        outputs = extract_outputs(func)

        # Generate YAML
        typer.echo("Generating YAML...")
        yaml_content = generate_cab_yaml(cab_name, cab_info, inputs, outputs)

        # Write to file
        typer.echo(f"Writing to: {output}")
        write_cab_yaml(yaml_content, output)

        typer.secho(f"✓ Successfully generated cab definition: {output}", fg=typer.colors.GREEN)

    except ImportError as e:
        typer.secho(
            f"✗ Error: Could not import module '{module}': {e}", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(code=1)
    except ValueError as e:
        typer.secho(f"✗ Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"✗ Unexpected error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
