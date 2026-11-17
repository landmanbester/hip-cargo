from typing import Annotated

import typer

from hip_cargo import StimelaMeta, stimela_cab


@stimela_cab(
    name="tunable_demo",
    info="Fixture command exercising tunable parameter round-trip.",
)
def tunable_demo(
    n_iter: Annotated[
        int,
        typer.Option(
            help="Number of iterations.",
            rich_help_panel="Tuning",
        ),
        StimelaMeta(
            metadata={
                "tunable": True,
            },
        ),
    ] = 10,
    threshold: Annotated[
        float,
        typer.Option(
            help="Convergence threshold.",
            rich_help_panel="Tuning",
        ),
        StimelaMeta(
            metadata={
                "tunable": True,
            },
        ),
    ] = 0.001,
    label: Annotated[
        str,
        typer.Option(
            help="Run label.",
            rich_help_panel="Inputs",
        ),
    ] = "default",
):
    """
    Fixture command exercising tunable parameter round-trip.
    """
    params = dict(
        n_iter=n_iter,
        threshold=threshold,
        label=label,
    )

    from fixture_pkg.core.tunable_demo import tunable_demo as tunable_demo_core  # noqa: E402

    from hip_cargo.utils.runner import preflight_remote_must_exist  # noqa: E402

    # Pre-flight must_exist for remote URIs before dispatching.
    preflight_remote_must_exist(tunable_demo, params)
    tunable_demo_core(**params)
