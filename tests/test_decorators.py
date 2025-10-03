"""Quick test of decorators and introspection."""

from pathlib import Path

import typer
from typing_extensions import Annotated

from hip_cargo import stimela_cab, stimela_output
from hip_cargo.introspector import extract_cab_info, extract_inputs, extract_outputs
from hip_cargo.yaml_generator import generate_cab_yaml


@stimela_cab(name="test_processor", info="A test processing function")
@stimela_output(name="output_file", dtype="File", info="{input_file}.processed")
def process_old_style(
    input_file: Path = typer.Argument(..., help="Input File to process"),
    threshold: float = typer.Option(0.5, help="Threshold value"),
):
    """
    Process a data file (old style).

    Args:
        input_file: Input File to process
        threshold: Threshold value for processing
    """
    pass


@stimela_cab(name="test_processor_annotated", info="A test processing function")
@stimela_output(name="output_file", dtype="File", info="{input_file}.processed", required=True)
def process_annotated(
    input_file: Annotated[Path, typer.Argument(help="Input File to process")],
    threshold: Annotated[float, typer.Option(0.5, help="Threshold value")] = 0.5,
):
    """
    Process a data file (Annotated style).

    Args:
        input_file: Input File to process
        threshold: Threshold value for processing
    """
    pass


if __name__ == "__main__":
    print("=== OLD STYLE (default value) ===\n")
    cab_info = extract_cab_info(process_old_style)
    inputs = extract_inputs(process_old_style)
    outputs = extract_outputs(process_old_style)
    yaml_content = generate_cab_yaml("test_processor", cab_info, inputs, outputs)
    print(yaml_content)

    print("\n=== NEW STYLE (Annotated) ===\n")
    cab_info = extract_cab_info(process_annotated)
    inputs = extract_inputs(process_annotated)
    outputs = extract_outputs(process_annotated)
    yaml_content = generate_cab_yaml("test_processor_annotated", cab_info, inputs, outputs)
    print(yaml_content)
