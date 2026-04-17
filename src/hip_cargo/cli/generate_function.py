from pathlib import Path
from typing import Annotated, Literal, NewType

import typer

from hip_cargo import StimelaMeta, stimela_cab, stimela_output

File = NewType("File", Path)


@stimela_cab(
    name="generate_function",
    info="Generate Python function from Stimela cab definition.",
)
@stimela_output(
    dtype="File",
    name="output-file",
    info="Name of output CLI function.",
    required=True,
    policies={"positional": True},
    metadata={"rich_help_panel": "Outputs"},
)
def generate_function(
    cab_file: Annotated[
        File,
        typer.Option(
            ...,
            parser=Path,
            help="Path to Stimela cab YAML file.",
            rich_help_panel="Inputs",
        ),
    ],
    output_file: Annotated[
        File,
        typer.Option(
            ...,
            parser=Path,
            help="Name of output CLI function.",
            rich_help_panel="Outputs",
        ),
    ],
    config_file: Annotated[
        File | None,
        typer.Option(
            parser=Path,
            help="Optional path to ruff config file to use when generating function.",
            rich_help_panel="Inputs",
        ),
    ] = None,
    backend: Annotated[
        Literal["auto", "native", "apptainer", "singularity", "docker", "podman"],
        typer.Option(
            help="Execution backend.",
        ),
        StimelaMeta(
            skip=True,
        ),
    ] = "auto",
    always_pull_images: Annotated[
        bool,
        typer.Option(
            help="Always pull container images, even if cached locally.",
        ),
        StimelaMeta(
            skip=True,
        ),
    ] = False,
):
    """
    Generate Python function from Stimela cab definition.
    """
    if backend == "native" or backend == "auto":
        try:
            # Lazy import the core implementation
            from hip_cargo.core.generate_function import generate_function as generate_function_core  # noqa: E402

            # Call the core function with all parameters
            generate_function_core(
                cab_file,
                output_file,
                config_file=config_file,
            )
            return
        except ImportError:
            if backend == "native":
                raise

    # Resolve container image from installed package metadata
    from hip_cargo.utils.config import get_container_image  # noqa: E402
    from hip_cargo.utils.runner import run_in_container  # noqa: E402

    image = get_container_image("hip-cargo")
    if image is None:
        raise RuntimeError("No Container URL in hip-cargo metadata.")

    run_in_container(
        generate_function,
        dict(
            cab_file=cab_file,
            config_file=config_file,
            output_file=output_file,
        ),
        image=image,
        backend=backend,
        always_pull_images=always_pull_images,
    )
