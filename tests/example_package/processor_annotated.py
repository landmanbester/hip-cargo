"""Example processing module using Annotated style."""

from pathlib import Path

import typer
from typing_extensions import Annotated

from hip_cargo import stimela_cab, stimela_output

app = typer.Typer()


@app.command()
@stimela_cab(
    name="example_processor_annotated",
    info="Process astronomical data files (Annotated style)",
)
@stimela_output(
    name="output_file",
    dtype="File",
    info="{input_file}.processed",
    required=True,
)
def process(
    input_file: Annotated[Path, typer.Argument(help="Input File containing data")],
    output_dir: Annotated[Path, typer.Option(help="Output Directory for results")] = Path(
        "./output"
    ),
    threshold: Annotated[float, typer.Option(help="Threshold value")] = 0.5,
    verbose: Annotated[bool, typer.Option(help="Enable verbose output")] = False,
):
    """
    Process astronomical data with specified parameters.

    Args:
        input_file: Input File containing data
        output_dir: Output Directory for results
        threshold: Threshold value for processing
        verbose: Enable verbose output
    """
    typer.echo(f"Processing {input_file}...")


if __name__ == "__main__":
    app()
