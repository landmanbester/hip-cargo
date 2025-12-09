#!/usr/bin/env python3
"""Update CLI help documentation in README."""

import subprocess
from pathlib import Path

from rich.console import Console

width = 100


def update_help_svg():
    """Generate SVG from cargo --help output."""
    # Run the CLI command
    result = subprocess.run(["cargo", "--help"], capture_output=True, text=True, check=True)

    # Determine the actual width needed by finding the longest line
    lines = result.stdout.split("\n")
    max_width = max(len(line) for line in lines) if lines else 80

    # Add some padding and ensure a reasonable minimum
    console_width = max(max_width + 5, 80)

    # Create console with recording enabled
    console = Console(record=True, width=console_width)
    console.print(result.stdout)

    # Save to docs directory
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)

    output_path = docs_dir / "cli-help.svg"
    console.save_svg(str(output_path), title="hip-cargo CLI")

    print(f"✓ Updated {output_path}")
    return 0


def update_generate_cabs_help_svg():
    """Generate SVG from cargo generate-cabs --help output."""
    # Run the CLI command
    result = subprocess.run(["cargo", "generate-cabs", "--help"], capture_output=True, text=True, check=True)

    # Determine the actual width needed by finding the longest line
    lines = result.stdout.split("\n")
    max_width = max(len(line) for line in lines) if lines else 80

    # Add some padding and ensure a reasonable minimum
    console_width = max(max_width + 5, 80)

    # Create console with recording enabled
    console = Console(record=True, width=console_width)
    console.print(result.stdout)

    # Save to docs directory
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)

    output_path = docs_dir / "generate-cabs-help.svg"
    console.save_svg(str(output_path), title="hip-cargo generate-cabs CLI")

    print(f"✓ Updated {output_path}")
    return 0


def update_generate_function_help_svg():
    """Generate SVG from cargo generate-function --help output."""
    # Run the CLI command
    result = subprocess.run(["cargo", "generate-function", "--help"], capture_output=True, text=True, check=True)

    # Determine the actual width needed by finding the longest line
    lines = result.stdout.split("\n")
    max_width = max(len(line) for line in lines) if lines else 80

    # Add some padding and ensure a reasonable minimum
    console_width = max(max_width + 5, 80)

    # Create console with recording enabled
    console = Console(record=True, width=console_width)
    console.print(result.stdout)

    # Save to docs directory
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)

    output_path = docs_dir / "generate-function-help.svg"
    console.save_svg(str(output_path), title="hip-cargo generate-function CLI")

    print(f"✓ Updated {output_path}")
    return 0


if __name__ == "__main__":
    update_help_svg()
    update_generate_cabs_help_svg()
    update_generate_function_help_svg()
