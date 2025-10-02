# hip-cargo

Tools for generating Stimela cab definitions from Python functions with type hints.

## Installation

```bash
pip install hip-cargo
```

Or for development:

```bash
git clone https://github.com/landmanbester/hip-cargo.git
cd hip-cargo
uv sync
```

## Usage

### 1. Decorate your Python function

```python
import typer
from pathlib import Path
from hip_cargo import stimela_cab, stimela_output

app = typer.Typer()

@app.command()
@stimela_cab(
    name="my_processor",
    info="Process data files",
)
@stimela_output(
    name="output_file",
    dtype="File",
    info="{input_file}.processed",
    required=True,
)
def process(
    input_file: Path = typer.Argument(..., help="Input File to process"),
    output_dir: Path = typer.Option("./output", help="Output Directory for results"),
    threshold: float = typer.Option(0.5, help="Threshold value"),
):
    """
    Process a data file.
    
    Args:
        input_file: Input File to process
        output_dir: Output Directory for results
        threshold: Threshold value for processing
    """
    # Your implementation here
    pass
```

### 2. Generate the Stimela cab definition

```bash
cargo generate-cab mypackage.mymodule /path/to/output.yaml
```

## Type Inference

hip-cargo automatically infers Stimela data types from:

1. **Python type hints**: `str`, `int`, `float`, `bool`, `Path`, `List[T]`
2. **Help string keywords**:
   - "File" → `File`
   - "Directory" or "Dir" → `Directory`
   - "MS" or "Measurement Set" → `MS`
   - "URL" → `URL`
   - "URI" → `URI`

## Decorators

### `@stimela_cab`

Marks a function as a Stimela cab.

- `name`: Cab name
- `info`: Description
- `policies`: Optional dict of cab-level policies

### `@stimela_output`

Defines an output (can be used multiple times).

- `name`: Output name
- `dtype`: Data type (File, Directory, MS, etc.)
- `info`: Description (supports f-string formatting with input parameters)
- `required`: Whether output is required (default: False)

## Features

- ✅ Automatic type inference from Python type hints
- ✅ Parse Google-style docstrings for parameter descriptions
- ✅ Support for Typer Arguments (positional) and Options
- ✅ Multiple outputs with f-string formatting
- ✅ List types with automatic `repeat: list` policy
- ✅ Proper handling of default values and required parameters

## Development

This project uses:
- [uv](https://github.com/astral-sh/uv) for dependency management
- [ruff](https://github.com/astral-sh/ruff) for linting and formatting
- [typer](https://typer.tiangolo.com/) for the CLI

## License

MIT License