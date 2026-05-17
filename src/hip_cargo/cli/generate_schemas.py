from pathlib import Path
from typing import Annotated, Literal, NewType

import typer

from hip_cargo import StimelaMeta, parse_upath, stimela_cab, stimela_output

Directory = NewType("Directory", Path)
File = NewType("File", Path)


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
    if backend == "native" or backend == "auto":
        try:
            # Pre-flight must_exist for remote URIs before dispatching.
            from hip_cargo.utils.runner import preflight_remote_must_exist  # noqa: E402

            preflight_remote_must_exist(
                generate_schemas,
                dict(
                    module=module,
                    output_dir=output_dir,
                ),
            )

            # Lazy import the core implementation
            from hip_cargo.core.generate_schemas import generate_schemas as generate_schemas_core  # noqa: E402

            # Call the core function with all parameters
            generate_schemas_core(
                module,
                output_dir=output_dir,
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
        generate_schemas,
        dict(
            module=module,
            output_dir=output_dir,
        ),
        image=image,
        backend=backend,
        always_pull_images=always_pull_images,
    )
