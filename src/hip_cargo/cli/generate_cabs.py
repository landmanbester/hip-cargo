"""CLI command for generating Stimela cab definitions."""

from pathlib import Path
from typing import NewType

import typer
from rich import print
from typing_extensions import Annotated

from hip_cargo.utils.decorators import stimela_cab, stimela_output

File = NewType("File", Path)
Directory = NewType("Directory", Path)


@stimela_cab(
    name="generate_cabs",
    info="Generate Stimela cab definition from Python CLI function",
)
@stimela_output(
    dtype="Directory",
    name="output_dir",
    info="Path to output directory where cab definitions will be saved. "
    "The cab will have the exact same name as the command.",
)
def generate_cabs(
    module: Annotated[
        list[File],
        typer.Option(
            ...,
            parser=Path,
            help="CLI module path. "
            "Use wild card to generate cabs for multiple commands in module (e.g. package/cli/*). ",
            rich_help_panel="Inputs",
        ),
    ],
    output_dir: Annotated[
        Directory,
        typer.Option(
            parser=Path,
            help="Output directory for cab definition. The cab will have the exact same name as the command.",
            rich_help_panel="Outputs",
        ),
    ] = None,
    image: Annotated[
        str | None,
        typer.Option(help="Name of container image. ", rich_help_panel="Inputs"),
    ] = None,
):
    """Generate a Stimela cab definition from a Python module.

    The module should contain a single Typer command decorated with
    @stimela_cab and optionally @stimela_output decorators.
    """
    # Lazy imports
    from hip_cargo.core.generate_cabs import generate_cabs as generate_cabs_core  # noqa: E402

    # glob if wildcard in module
    modlist = []
    for modpath in module:
        if "*" in str(modpath):
            base_path = Path(str(modpath).split("*")[0].rstrip("/"))
            modlist.extend([f for f in base_path.glob("*") if f.is_file() and not f.name.startswith("__")])
            if len(modlist) == 0:
                raise RuntimeError(f"No modules found matching {modpath}")
        else:
            if not modpath.is_file():
                raise RuntimeError(f"No module file found at {modpath}")
            modlist.append(modpath)

    # User feedback
    for mod in modlist:
        typer.echo(f"Loading file: {mod}")

    typer.echo(f"Writing cabs to: {output_dir}")

    # Call core logic
    generate_cabs_core(modlist, str(output_dir), image)

    # Success message
    print(f":boom: [green] Successfully generated cabs in: {output_dir} [/green]")
