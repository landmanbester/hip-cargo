from pathlib import Path
from typing import Annotated, NewType

import typer

from hip_cargo.utils.decorators import stimela_cab, stimela_output

File = NewType("File", Path)


@stimela_cab(
    name="generate_function",
    info="Generate Python function from Stimela cab definition.",
)
@stimela_output(
    dtype="File",
    name="output-file",
    info="Name of output CLI function (prints to stdout if not specified).",
    required=True,
)
def generate_function(
    cab_file: Annotated[
        File,
        typer.Option(
            ...,
            parser=Path,
            help="Path to Stimela cab YAML file.",
        ),
    ],
    output_file: Annotated[
        File,
        typer.Option(
            ...,
            parser=Path,
            help="Name of output CLI function (prints to stdout if not specified).",
        ),
    ],
    config_file: Annotated[
        File | None,
        typer.Option(
            parser=Path,
            help="Optional path to ruff config file to use when generating function.",
        ),
    ] = None,
):
    """
    Generate Python function from Stimela cab definition.
    """
    # Lazy import the core implementation
    from hip_cargo.core.generate_function import generate_function as generate_function_core  # noqa: E402

    # Call the core function with all parameters
    generate_function_core(
        cab_file,
        config_file=config_file,
        output_file=output_file,
    )
