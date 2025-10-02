"""Quick test of decorators and introspection."""

from pathlib import Path

import typer

from hip_cargo import stimela_cab, stimela_output
from hip_cargo.introspector import extract_cab_info, extract_inputs, extract_outputs
from hip_cargo.yaml_generator import generate_cab_yaml


@stimela_cab(name="test_processor", info="A test processing function")
@stimela_output(name="output_file", dtype="File", info="{input_file}.processed")
def process(
    input_file: Path = typer.Argument(..., help="Input File to process"),
    threshold: float = typer.Option(0.5, help="Threshold value"),
):
    """
    Process a data file.

    Args:
        input_file: Input File to process
        threshold: Threshold value for processing
    """
    pass


if __name__ == "__main__":
    print("=== Generated YAML ===\n")

    cab_info = extract_cab_info(process)
    inputs = extract_inputs(process)
    outputs = extract_outputs(process)

    yaml_content = generate_cab_yaml("test_processor", cab_info, inputs, outputs)
    print(yaml_content)
