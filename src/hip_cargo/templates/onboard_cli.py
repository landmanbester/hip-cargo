from typing import Annotated, Literal

import typer
from hip_cargo import StimelaMeta, stimela_cab


@stimela_cab(
    name="onboard",
    info="Print setup instructions for CI/CD, PyPI publishing, and GitHub configuration.",
)
def onboard(
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
    Print setup instructions for CI/CD, PyPI publishing, and GitHub configuration.
    """
    params = {}

    if backend == "native" or backend == "auto":
        # Only a missing install falls back to the container, so only the
        # imports and the pre-flight are guarded; the core call is not.
        try:
            from hip_cargo.utils.runner import preflight_remote_must_exist  # noqa: E402

            from <PACKAGE_NAME>.core.onboard import onboard as onboard_core  # noqa: E402

            # Pre-flight must_exist for remote URIs before dispatching.
            preflight_remote_must_exist(onboard, params)
        except ImportError as exc:
            # A failed import from this package is a bug, not a missing install.
            if backend == "native" or (exc.name or "").split(".")[0] == "<PACKAGE_NAME>":
                raise
        else:
            onboard_core(**params)
            return

    # Resolve container image from installed package metadata
    from hip_cargo.utils.config import get_container_image  # noqa: E402
    from hip_cargo.utils.runner import run_in_container  # noqa: E402

    image = get_container_image("<PROJECT_NAME>")
    if image is None:
        raise RuntimeError("No Container URL in <PROJECT_NAME> metadata.")

    run_in_container(
        onboard,
        params,
        image=image,
        backend=backend,
        always_pull_images=always_pull_images,
    )
