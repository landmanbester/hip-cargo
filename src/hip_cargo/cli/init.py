from pathlib import Path
from typing import Annotated, Literal, NewType

import typer

from hip_cargo import stimela_cab, stimela_output

Directory = NewType("Directory", Path)


@stimela_cab(
    name="init",
    info="Initialize a new hip-cargo project with scaffolding and Stimela cab support.",
)
@stimela_output(
    dtype="Directory",
    name="project-dir",
    info="Output directory for the generated project.",
    must_exist=True,
    metadata={"rich_help_panel": "Outputs"},
)
def init(
    project_name: Annotated[
        str,
        typer.Option(
            ...,
            help="Hyphenated project name (e.g. my-project).",
            rich_help_panel="Inputs",
        ),
    ],
    github_user: Annotated[
        str,
        typer.Option(
            ...,
            help="GitHub username or organization.",
            rich_help_panel="Inputs",
        ),
    ],
    description: Annotated[
        str,
        typer.Option(
            help="Short project description.",
            rich_help_panel="Inputs",
        ),
    ] = "A Python project",
    author_name: Annotated[
        str | None,
        typer.Option(
            help="Author name (auto-detected from git config if omitted).",
            rich_help_panel="Inputs",
        ),
    ] = None,
    author_email: Annotated[
        str | None,
        typer.Option(
            help="Author email (auto-detected from git config if omitted).",
            rich_help_panel="Inputs",
        ),
    ] = None,
    cli_command: Annotated[
        str | None,
        typer.Option(
            help="CLI entry point name (derived from project-name if omitted).",
            rich_help_panel="Inputs",
        ),
    ] = None,
    initial_version: Annotated[
        str,
        typer.Option(
            help="Starting version string.",
            rich_help_panel="Inputs",
        ),
    ] = "0.0.0",
    license_type: Annotated[
        Literal["MIT", "Apache-2.0", "BSD-3-Clause"],
        typer.Option(
            help="License type.",
            rich_help_panel="Inputs",
        ),
    ] = "MIT",
    cli_mode: Annotated[
        Literal["single", "multi"],
        typer.Option(
            help="CLI mode: single (one command) or multi (subcommands).",
            rich_help_panel="Inputs",
        ),
    ] = "multi",
    default_branch: Annotated[
        str,
        typer.Option(
            help="Default git branch name.",
            rich_help_panel="Inputs",
        ),
    ] = "main",
    auto_changelog: Annotated[
        bool,
        typer.Option(
            help="Enable git-cliff changelog generation and conventional commit enforcement via pre-commit.",
            rich_help_panel="Inputs",
        ),
    ] = False,
    project_dir: Annotated[
        Directory | None,
        typer.Option(
            parser=Path,
            help="Output directory for the generated project.",
            rich_help_panel="Outputs",
        ),
        {
            "stimela": {
                "must_exist": True,
            },
        },
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
    Initialize a new hip-cargo project with scaffolding and Stimela cab support.
    """
    if backend == "native" or backend == "auto":
        try:
            # Lazy import the core implementation
            from hip_cargo.core.init import init as init_core  # noqa: E402

            # Call the core function with all parameters
            init_core(
                project_name,
                github_user,
                description=description,
                author_name=author_name,
                author_email=author_email,
                cli_command=cli_command,
                initial_version=initial_version,
                license_type=license_type,
                cli_mode=cli_mode,
                default_branch=default_branch,
                auto_changelog=auto_changelog,
                project_dir=project_dir,
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
        init,
        dict(
            project_name=project_name,
            github_user=github_user,
            description=description,
            author_name=author_name,
            author_email=author_email,
            cli_command=cli_command,
            initial_version=initial_version,
            license_type=license_type,
            cli_mode=cli_mode,
            default_branch=default_branch,
            auto_changelog=auto_changelog,
            project_dir=project_dir,
        ),
        image=image,
        backend=backend,
        always_pull_images=always_pull_images,
    )
