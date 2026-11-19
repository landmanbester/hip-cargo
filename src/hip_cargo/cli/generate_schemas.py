from typing import Annotated, Literal

import typer

from hip_cargo import Directory, File, StimelaMeta, parse_upath, stimela_cab, stimela_output


@stimela_cab(
    name="generate_schemas",
    info="Generate Pydantic schemas of tunable parameters from Python CLI modules.",
)
@stimela_output(
    dtype="Directory",
    name="output-dir",
    info="Output directory for generated schemas. One file per command with tunable parameters.",
    metadata={"rich_help_panel": "Outputs"},
)
def generate_schemas(
    module: Annotated[
        list[File],
        typer.Option(
            ...,
            parser=parse_upath,
            help="CLI module path. "
            "Use wild card to generate schemas for multiple commands in module. "
            "For example, package/cli/*.",
            rich_help_panel="Inputs",
        ),
    ],
    output_dir: Annotated[
        Directory | None,
        typer.Option(
            parser=parse_upath,
            help="Output directory for generated schemas. One file per command with tunable parameters.",
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
    Generate Pydantic schemas of tunable parameters from Python CLI modules.
    """
    params = dict(
        module=module,
        output_dir=output_dir,
    )

    if backend == "native" or backend == "auto":
        # Only a missing install falls back to the container, so only the
        # imports and the pre-flight are guarded; the core call is not.
        try:
            from hip_cargo.core.generate_schemas import generate_schemas as generate_schemas_core  # noqa: E402
            from hip_cargo.utils.runner import preflight_remote_must_exist  # noqa: E402

            # Pre-flight must_exist for remote URIs before dispatching.
            preflight_remote_must_exist(generate_schemas, params)
        except ImportError as exc:
            # A failed import from this package is a bug, not a missing install.
            if backend == "native" or (exc.name or "").split(".")[0] == "hip_cargo":
                raise
            import typer  # a parameter may be named typer

            typer.echo(f"Cannot run natively ({exc!r}); falling back to a container.", err=True)
        else:
            generate_schemas_core(**params)
            return

    # Resolve container image from installed package metadata
    from hip_cargo.utils.config import get_container_image  # noqa: E402
    from hip_cargo.utils.runner import run_in_container  # noqa: E402

    image = get_container_image("hip-cargo")
    if image is None:
        raise RuntimeError("No Container URL in hip-cargo metadata.")

    run_in_container(
        generate_schemas,
        params,
        image=image,
        backend=backend,
        always_pull_images=always_pull_images,
    )
