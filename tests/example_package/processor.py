"""Example processing module for testing cab generation."""

from pathlib import Path

import typer

from hip_cargo import stimela_cab, stimela_output

app = typer.Typer()


@app.command()
@stimela_cab(
    name="example_processor",
    info="Process astronomical data files",
)
@stimela_output(
    name="output_file",
    dtype="File",
    info="{input_file}.processed",
    required=True,
)
@stimela_output(
    name="log_file",
    dtype="File",
    info="{output_dir}/processing.log",
    required=False,
)
def process(
    input_file: Path = typer.Argument(..., help="Input File containing data"),
    output_dir: Path = typer.Option("./output", help="Output Directory for results"),
    threshold: float = typer.Option(0.5, help="Threshold value for processing"),
    iterations: int = typer.Option(10, help="Number of iterations"),
    verbose: bool = typer.Option(False, help="Enable verbose output"),
):
    """
    Process astronomical data with specified parameters.

    Args:
        input_file: Input File containing data
        output_dir: Output Directory for results
        threshold: Threshold value for processing
        iterations: Number of iterations
        verbose: Enable verbose output
    """
    typer.echo(f"Processing {input_file}...")


if __name__ == "__main__":
    app()
