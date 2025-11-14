"""Core logic for generating Python functions from Stimela cab definitions."""

from pathlib import Path

from hip_cargo.utils.cab_to_function import cab_to_function_cli


def generate_function(cab_path: str, output_path: str | None = None) -> None:
    """Generate a Python function from a Stimela cab definition.

    Args:
        cab_path: Path to the YAML cab definition file
        output_path: Optional path where the Python function should be written.
                    If None, prints to stdout.

    Raises:
        FileNotFoundError: If the cab file doesn't exist
        ValueError: If the cab file is invalid
    """
    cab_file = Path(cab_path)

    if not cab_file.exists():
        raise FileNotFoundError(f"Cab file not found: {cab_file}")

    output_file = Path(output_path) if output_path else None
    cab_to_function_cli(cab_file, output_file)
