from pathlib import Path
from typing import Annotated, Literal, NewType

import typer

from hip_cargo import (
    ListStr,
    StimelaMeta,
    parse_list_str,
    parse_upath,
    stimela_cab,
    stimela_output,
)

Directory = NewType("Directory", Path)


@stimela_cab(
    name="wrap_demo",
    info="Render a dataset to an image.",
)
@stimela_output(
    dtype="Directory",
    name="output",
    info="Output image.",
    policies={"positional": True},
)
def wrap_demo(
    src: Annotated[
        Directory,
        typer.Option(
            ...,
            parser=parse_upath,
            help="Input dataset.",
        ),
    ],
    names: Annotated[
        ListStr,
        typer.Option(
            parser=parse_list_str,
            help="Variables to render.",
        ),
    ] = ["a", "b"],
    output: Annotated[
        Directory | None,
        typer.Option(
            parser=parse_upath,
            help="Output image.",
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
    Render a dataset to an image.
    """
    if backend == "native" or backend == "auto":
        try:
            # Pre-flight must_exist for remote URIs before dispatching.
            from hip_cargo.utils.runner import preflight_remote_must_exist  # noqa: E402

            preflight_remote_must_exist(
                wrap_demo,
                dict(
                    src=src,
                    names=names,
                    output=output,
                ),
            )

            # Lazy import the core implementation
            from fixture_pkg.core.wrap_demo import wrap_demo as wrap_demo_core  # noqa: E402

            # Call the core function with all parameters
            wrap_demo_core(
                src,
                output,
                names=names,
            )
            return
        except ImportError:
            if backend == "native":
                raise

    # Resolve container image from installed package metadata
    from hip_cargo.utils.config import get_container_image  # noqa: E402
    from hip_cargo.utils.runner import run_in_container  # noqa: E402

    image = get_container_image("fixture-pkg")
    if image is None:
        raise RuntimeError("No Container URL in fixture-pkg metadata.")

    run_in_container(
        wrap_demo,
        dict(
            src=src,
            names=names,
            output=output,
        ),
        image=image,
        backend=backend,
        always_pull_images=always_pull_images,
    )
