from typing import Annotated, Literal

import typer

from hip_cargo import (
    Directory,
    ListStr,
    StimelaMeta,
    parse_list_str,
    parse_upath,
    stimela_cab,
    stimela_output,
)


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
    params = dict(
        src=src,
        names=names,
        output=output,
    )

    if backend == "native" or backend == "auto":
        # Only a missing install falls back to the container, so only the
        # imports and the pre-flight are guarded; the core call is not.
        try:
            from fixture_pkg.core.wrap_demo import wrap_demo as wrap_demo_core  # noqa: E402

            from hip_cargo.utils.runner import preflight_remote_must_exist  # noqa: E402

            # Pre-flight must_exist for remote URIs before dispatching.
            preflight_remote_must_exist(wrap_demo, params)
        except ImportError as exc:
            # A failed import from this package is a bug, not a missing install.
            if backend == "native" or (exc.name or "").split(".")[0] == "fixture_pkg":
                raise
        else:
            wrap_demo_core(**params)
            return

    # Resolve container image from installed package metadata
    from hip_cargo.utils.config import get_container_image  # noqa: E402
    from hip_cargo.utils.runner import run_in_container  # noqa: E402

    image = get_container_image("fixture-pkg")
    if image is None:
        raise RuntimeError("No Container URL in fixture-pkg metadata.")

    run_in_container(
        wrap_demo,
        params,
        image=image,
        backend=backend,
        always_pull_images=always_pull_images,
    )
