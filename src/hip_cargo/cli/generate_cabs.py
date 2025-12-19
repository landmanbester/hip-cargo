from pathlib import Path
from typing import Annotated, NewType

import typer

from hip_cargo.utils.decorators import stimela_cab, stimela_output

Directory = NewType("Directory", Path)
File = NewType("File", Path)


@stimela_cab(
    name="generate_cabs",
    info="Generate Stimela cab definition from Python CLI function.",
)
@stimela_output(
    dtype="Directory",
    name="output_dir",
    info="Output directory for cab definition. The cab will have the exact same name as the command.",
)
def generate_cabs(
    module: Annotated[
        list[File],
        typer.Option(
            ...,
            parser=Path,
            help="CLI module path. "
            "Use wild card to generate cabs for multiple commands in module. "
            "For example, package/cli/*).",
        ),
    ],
    image: Annotated[
        str | None,
        typer.Option(
            help="Name of container image.",
        ),
    ] = None,
    output_dir: Annotated[
        Directory | None,
        typer.Option(
            parser=Path,
            help="Output directory for cab definition. The cab will have the exact same name as the command.",
        ),
    ] = None,
):
    """
    Generate Stimela cab definition from Python CLI function.
    """
    # Lazy import the core implementation
    from hip_cargo.core.generate_cabs import generate_cabs as generate_cabs_core  # noqa: E402

    # Call the core function with all parameters
    generate_cabs_core(
        module,
        image=image,
        output_dir=output_dir,
    )
