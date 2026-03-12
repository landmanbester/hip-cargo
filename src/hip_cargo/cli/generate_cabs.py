from pathlib import Path
from typing import Annotated, Literal, NewType

import typer

from hip_cargo import stimela_cab, stimela_output

Directory = NewType("Directory", Path)
File = NewType("File", Path)


@stimela_cab(
    name="generate_cabs",
    info="Generate Stimela cab definition from Python CLI function.",
    image="ghcr.io/landmanbester/hip-cargo:gencabsfixfollowup",
)
@stimela_output(
    dtype="Directory",
    name="output-dir",
    info="Output directory for cab definition. The cab will have the exact same name as the command.",  # noqa: E501
    metadata={"rich_help_panel": "Outputs"},
)
def generate_cabs(
    module: Annotated[
        list[File],
        typer.Option(
            ...,
            parser=Path,
            help="CLI module path. "
            "Use wild card to generate cabs for multiple commands in module. "
            "For example, package/cli/*.",
            rich_help_panel="Inputs",
        ),
    ],
    image: Annotated[
        str | None,
        typer.Option(
            help="Name of container image.",
            rich_help_panel="Inputs",
        ),
    ] = None,
    output_dir: Annotated[
        Directory | None,
        typer.Option(
            parser=Path,
            help="Output directory for cab definition. The cab will have the exact same name as the command.",  # noqa: E501
            rich_help_panel="Outputs",
        ),
    ] = None,
    backend: Annotated[
        Literal["auto", "native", "apptainer", "singularity", "docker", "podman"],
        typer.Option(
            help="Execution backend.",
        ),
        {"stimela": {"skip": True}},
    ] = "auto",
    always_pull_images: Annotated[
        bool,
        typer.Option(
            help="Always pull container images, even if cached locally.",
        ),
        {"stimela": {"skip": True}},
    ] = False,
):
    """
    Generate Stimela cab definition from Python CLI function.
    """
    if backend == "native" or backend == "auto":
        try:
            # Lazy import the core implementation
            from hip_cargo.core.generate_cabs import generate_cabs as generate_cabs_core  # noqa: E402

            # Call the core function with all parameters
            generate_cabs_core(
                module,
                image=image,
                output_dir=output_dir,
            )
            return
        except ImportError:
            if backend == "native":
                raise

    # Fall back to container execution
    from hip_cargo.utils.runner import run_in_container  # noqa: E402

    run_in_container(
        generate_cabs,
        dict(
            module=module,
            image=image,
            output_dir=output_dir,
        ),
        backend=backend,
        always_pull_images=always_pull_images,
    )
