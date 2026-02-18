from pathlib import Path
from typing import Annotated, Literal, NewType

import typer

from hip_cargo.utils.decorators import stimela_cab, stimela_output

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
)
def init(
    project_name: Annotated[
        str,
        typer.Option(
            ...,
            help="Hyphenated project name (e.g. my-project).",
        ),
    ],
    github_user: Annotated[
        str,
        typer.Option(
            ...,
            help="GitHub username or organization.",
        ),
    ],
    description: Annotated[
        str,
        typer.Option(
            help="Short project description.",
        ),
    ] = "A Python project",
    author_name: Annotated[
        str | None,
        typer.Option(
            help="Author name (auto-detected from git config if omitted).",
        ),
    ] = None,
    author_email: Annotated[
        str | None,
        typer.Option(
            help="Author email (auto-detected from git config if omitted).",
        ),
    ] = None,
    cli_command: Annotated[
        str | None,
        typer.Option(
            help="CLI entry point name (derived from project-name if omitted).",
        ),
    ] = None,
    initial_version: Annotated[
        str,
        typer.Option(
            help="Starting version string.",
        ),
    ] = "0.0.0",
    license_type: Annotated[
        Literal["MIT", "Apache-2.0", "BSD-3-Clause"],
        typer.Option(
            help="License type.",
        ),
    ] = "MIT",
    cli_mode: Annotated[
        Literal["single", "multi"],
        typer.Option(
            help="CLI mode: single (one command) or multi (subcommands).",
        ),
    ] = "multi",
    default_branch: Annotated[
        str,
        typer.Option(
            help="Default git branch name.",
        ),
    ] = "main",
    project_dir: Annotated[
        Directory | None,
        typer.Option(
            parser=Path,
            help="Output directory for the generated project.",
        ),
        {
            "stimela": {
                "must_exist": True,
            },
        },
    ] = None,
):
    """
    Initialize a new hip-cargo project with scaffolding and Stimela cab support.
    """
    from hip_cargo.core.init import init as init_core  # noqa: E402

    init_core(
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
        project_dir=project_dir,
    )
