from pathlib import Path
from typing import Annotated, NewType

import typer

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
            help="Output directory for cab definition. The cab will have the exact same name as the command. ",
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

    # Call core logic
    generate_cabs_core(module, output_dir=output_dir, image=image)
