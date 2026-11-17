from typing import Annotated, Literal

import typer

from hip_cargo import stimela_cab


@stimela_cab(
    name="choices_demo",
    info="Fixture command exercising optional choices round-trip.",
)
def choices_demo(
    beam_model: Annotated[
        Literal["meerkat-beams", "katbeam"] | None,
        typer.Option(
            help="Which beam model to use.",
        ),
    ] = None,
    mode: Annotated[
        Literal["fast", "slow"],
        typer.Option(
            help="Processing mode.",
        ),
    ] = "fast",
    precision: Annotated[
        Literal["single", "double"] | None,
        typer.Option(
            help="Floating point precision.",
        ),
    ] = "double",
):
    """
    Fixture command exercising optional choices round-trip.
    """
    params = dict(
        beam_model=beam_model,
        mode=mode,
        precision=precision,
    )

    from fixture_pkg.core.choices_demo import choices_demo as choices_demo_core  # noqa: E402

    from hip_cargo.utils.runner import preflight_remote_must_exist  # noqa: E402

    # Pre-flight must_exist for remote URIs before dispatching.
    preflight_remote_must_exist(choices_demo, params)
    choices_demo_core(**params)
