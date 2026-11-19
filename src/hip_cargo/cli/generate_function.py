from typing import Annotated, Literal

import typer

from hip_cargo import File, StimelaMeta, parse_upath, stimela_cab, stimela_output


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
            parser=parse_upath,
            help="Path to Stimela cab YAML file.",
            rich_help_panel="Inputs",
        ),
    ],
    output_file: Annotated[
        File,
        typer.Option(
            ...,
            parser=parse_upath,
            help="Name of output CLI function.",
            rich_help_panel="Outputs",
        ),
    ],
    config_file: Annotated[
        File | None,
        typer.Option(
            parser=parse_upath,
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
    params = dict(
        cab_file=cab_file,
        config_file=config_file,
        output_file=output_file,
    )

    if backend == "native" or backend == "auto":
        # Only a missing install falls back to the container, so only the
        # imports and the pre-flight are guarded; the core call is not.
        try:
            from hip_cargo.core.generate_function import generate_function as generate_function_core  # noqa: E402
            from hip_cargo.utils.runner import preflight_remote_must_exist  # noqa: E402

            # Pre-flight must_exist for remote URIs before dispatching.
            preflight_remote_must_exist(generate_function, params)
        except ImportError as exc:
            # A failed import from this package is a bug, not a missing install.
            if backend == "native" or (exc.name or "").split(".")[0] == "hip_cargo":
                raise
            typer.echo(f"Cannot run natively ({exc!r}); falling back to a container.", err=True)
        else:
            generate_function_core(**params)
            return

    # Resolve container image from installed package metadata
    from hip_cargo.utils.config import get_container_image  # noqa: E402
    from hip_cargo.utils.runner import run_in_container  # noqa: E402

    image = get_container_image("hip-cargo")
    if image is None:
        raise RuntimeError("No Container URL in hip-cargo metadata.")

    run_in_container(
        generate_function,
        params,
        image=image,
        backend=backend,
        always_pull_images=always_pull_images,
    )
