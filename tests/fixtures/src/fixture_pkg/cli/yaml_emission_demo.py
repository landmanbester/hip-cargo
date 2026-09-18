from typing import Annotated

import typer

from hip_cargo import StimelaMeta, stimela_cab


@stimela_cab(
    name="yaml_emission_demo",
    info="Fixture command exercising signed defaults and colons in info fields.",
)
def yaml_emission_demo(
    neg_int: Annotated[
        int,
        typer.Option(
            help="A negative integer default.",
        ),
        StimelaMeta(
            metadata={"tunable": True},
        ),
    ] = -1,
    neg_float: Annotated[
        float,
        typer.Option(
            help="A negative float default.",
        ),
    ] = -1.5,
    pos_int: Annotated[
        int,
        typer.Option(
            help="A positive integer default.",
        ),
    ] = 7,
    colon_single: Annotated[
        str,
        typer.Option(
            help="Antenna 1: plot only this antenna.",
        ),
    ] = "a",
    colon_multi: Annotated[
        str,
        typer.Option(
            help="Antenna 1: plot only this antenna. Defaults to all of them.",
        ),
    ] = "b",
    apostrophe_colon: Annotated[
        str,
        typer.Option(
            help="Note: don't quote this. It has a second sentence.",
        ),
    ] = "c",
):
    """
    Fixture command exercising signed defaults and colons in info fields.
    """
    # Lazy import the core implementation
    from fixture_pkg.core.yaml_emission_demo import yaml_emission_demo as yaml_emission_demo_core  # noqa: E402

    # Call the core function with all parameters
    yaml_emission_demo_core(
        neg_int=neg_int,
        neg_float=neg_float,
        pos_int=pos_int,
        colon_single=colon_single,
        colon_multi=colon_multi,
        apostrophe_colon=apostrophe_colon,
    )
