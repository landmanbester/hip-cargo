from pathlib import Path
from typing import Annotated, Literal, NewType

import typer

from hip_cargo import StimelaMeta, parse_upath, stimela_cab, stimela_output

Directory = NewType("Directory", Path)
File = NewType("File", Path)


@stimela_cab(
    name="transpile",
    info="Transpile a restricted-subset stimela recipe into a Ray runner package.",
)
@stimela_output(
    dtype="Directory",
    name="output-dir",
    info="Directory the generated package is written into.",
    metadata={"rich_help_panel": "Outputs"},
)
def transpile(
    recipe: Annotated[
        File,
        typer.Option(
            ...,
            parser=parse_upath,
            help="Recipe YAML file to transpile. "
            "The cab package referenced by its _include entries must be importable "
            "(a lightweight install suffices).",
            rich_help_panel="Inputs",
        ),
    ],
    output_dir: Annotated[
        Directory,
        typer.Option(
            ...,
            parser=parse_upath,
            help="Directory the generated package (tasks/runner/cli) is written into.",
            rich_help_panel="Outputs",
        ),
    ],
    package: Annotated[
        str | None,
        typer.Option(
            help="Dotted import path of the emitted package. "
            "Defaults to <cab root package>.<output dir name>, e.g. stokify.transpiled.",
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
    Transpile a restricted-subset stimela recipe into a Ray runner package.
    """
    if backend == "native" or backend == "auto":
        try:
            # Pre-flight must_exist for remote URIs before dispatching.
            from hip_cargo.utils.runner import preflight_remote_must_exist  # noqa: E402

            preflight_remote_must_exist(
                transpile,
                dict(
                    recipe=recipe,
                    output_dir=output_dir,
                ),
            )

            # Lazy import the core implementation
            from hip_cargo.core.transpile import TranspileRefusedError, transpile_recipe  # noqa: E402

            try:
                written = transpile_recipe(recipe, output_dir, out_package=package)
            except TranspileRefusedError as exc:
                typer.echo(f"Recipe is outside the transpilable subset ({len(exc.errors)} problem(s)):", err=True)
                for error in exc.errors:
                    typer.echo(f"  - {error}", err=True)
                raise typer.Exit(code=1) from exc
            if written:
                for path in written:
                    typer.echo(f"wrote {path}")
            else:
                typer.echo("output already up to date")
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
        transpile,
        dict(
            recipe=recipe,
            output_dir=output_dir,
            package=package,
        ),
        image=image,
        backend=backend,
        always_pull_images=always_pull_images,
    )
