from typing import Annotated, Literal

import typer

from hip_cargo import Directory, File, StimelaMeta, parse_upath, stimela_cab, stimela_output


@stimela_cab(
    name="generate_cabs",
    info="Generate Stimela cab definition from Python CLI function.",
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
            parser=parse_upath,
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
            parser=parse_upath,
            help="Output directory for cab definition. The cab will have the exact same name as the command.",  # noqa: E501
            rich_help_panel="Outputs",
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
    Generate Stimela cab definition from Python CLI function.
    """
    params = dict(
        module=module,
        image=image,
        output_dir=output_dir,
    )

    if backend == "native" or backend == "auto":
        # Only a missing install falls back to the container, so only the
        # imports and the pre-flight are guarded; the core call is not.
        try:
            from hip_cargo.core.generate_cabs import generate_cabs as generate_cabs_core  # noqa: E402
            from hip_cargo.utils.runner import preflight_remote_must_exist  # noqa: E402

            # Pre-flight must_exist for remote URIs before dispatching.
            preflight_remote_must_exist(generate_cabs, params)
        except ImportError:
            if backend == "native":
                raise
        else:
            generate_cabs_core(**params)
            return

    # Resolve container image from installed package metadata
    from hip_cargo.utils.config import get_container_image  # noqa: E402
    from hip_cargo.utils.runner import run_in_container  # noqa: E402

    image = get_container_image("hip-cargo")
    if image is None:
        raise RuntimeError("No Container URL in hip-cargo metadata.")

    run_in_container(
        generate_cabs,
        params,
        image=image,
        backend=backend,
        always_pull_images=always_pull_images,
    )
