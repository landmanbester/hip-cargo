# hip-cargo

A guide to designing self-documenting CLI interfaces using Typer + conversion utilities

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

## Quick Start

### 1. Decorate your Python function

```python
import typer
from pathlib import Path
from typing_extensions import Annotated
from hip_cargo import stimela_cab, stimela_output

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
    input_file: Annotated[Path, typer.Argument(help="Input File to process")],
    output_dir: Annotated[Path, typer.Option(help="Output Directory for results")] = Path("./output"),
    threshold: Annotated[float, typer.Option(help="Threshold value")] = 0.5,
):
    """
    Process a data file.
    """
    # Your implementation here
    pass
```

### 2. Generate the Stimela cab definition

```bash
cargo generate-cab mypackage.mymodule /path/to/output.yaml
```

### 3. Generate Python function from existing cab (reverse)

```bash
cargo generate-function /path/to/existing_cab.yaml -o myfunction.py
```

## Project Structure for hip-cargo Packages

Packages following the hip-cargo pattern should be structured to enable both lightweight cab definitions and full execution environments:

```
my-scientific-package/
├── src/
│   └── mypackage/
│       ├── __init__.py
│       ├── operators/           # Heavy algorithms
│       │   ├── __init__.py
│       │   └── core_algorithm.py
│       ├── workers/             # Original implementations (optional)
│       └── cli/                 # Lightweight CLI layer
│           ├── __init__.py      # Main Typer app
│           ├── process.py       # Individual commands
│           └── analyze.py
├── cabs/                        # Generated cab definitions (at root)
│   ├── __init__.py
│   ├── process.yaml
│   └── analyze.yaml
├── scripts/
│   └── generate_cabs.py        # Automation script
├── Dockerfile                   # For containerization
├── pyproject.toml
└── README.md
```

### Key Principles

1. **Separate CLI from implementation**: Keep CLI modules lightweight with lazy imports
2. **Cabs at root level**: Place generated cab definitions in `cabs/` directory at project root
3. **Single app, multiple commands**: Use one Typer app that registers all commands
4. **Lazy imports**: Import heavy dependencies (NumPy, JAX, Dask) only when executing

### Example Structure

**`src/mypackage/cli/__init__.py`:**
```python
"""Lightweight CLI for mypackage."""

import typer

app = typer.Typer(
    name="mypackage",
    help="Scientific computing package",
    no_args_is_help=True,
)

# Register commands
from mypackage.cli.process import process
from mypackage.cli.analyze import analyze

app.command(name="process")(process)
app.command(name="analyze")(analyze)

__all__ = ["app"]
```

**`src/mypackage/cli/process.py`:**
```python
"""Process command - lightweight wrapper."""

from pathlib import Path
from typing_extensions import Annotated
import typer
from hip_cargo import stimela_cab, stimela_output

@stimela_cab(name="mypackage_process", info="Process data")
@stimela_output(name="output", dtype="File", info="{input_file}.out")
def process(
    input_file: Annotated[Path, typer.Argument(help="Input File")],
    param: Annotated[float, typer.Option(help="Parameter")] = 1.0,
):
    """Process data files."""
    # Lazy import - only loaded when executing
    from mypackage.operators.core_algorithm import process_data
    
    return process_data(input_file, param)
```

**`pyproject.toml`:**
```toml
[project]
name = "mypackage"
dependencies = [
    "typer>=0.12.0",
    "hip-cargo>=0.1.0",
]

[project.optional-dependencies]
# Full scientific stack
full = [
    "numpy>=1.24.0",
    "jax>=0.4.0",
    # ... heavy dependencies
]

# For cab definitions only (lightweight)
cabs = [
    "hip-cargo>=0.1.0",
]

[project.scripts]
mypackage = "mypackage.cli:app"
```

**`scripts/generate_cabs.py`:**
```python
"""Generate all cab definitions."""
import subprocess
from pathlib import Path

CLI_MODULES = [
    "mypackage.cli.process",
    "mypackage.cli.analyze",
]

CABS_DIR = Path("cabs")
CABS_DIR.mkdir(exist_ok=True)

for module in CLI_MODULES:
    cmd_name = module.split(".")[-1]
    output = CABS_DIR / f"{cmd_name}.yaml"
    
    print(f"Generating {output}...")
    subprocess.run([
        "cargo", "generate-cab",
        module,
        str(output)
    ], check=True)

print("✓ All cabs generated")
```

### Installation Modes

Users can install your package in different ways:

```bash
# Lightweight (just CLI and cab definitions)
pip install mypackage

# Full (with all scientific dependencies)
pip install mypackage[full]

# Development
pip install -e "mypackage[full,dev]"
```

### Integration with cult-cargo

For integration with Stimela's cult-cargo:

1. **Make cabs discoverable:**
```python
# cabs/__init__.py
from pathlib import Path

CAB_DIR = Path(__file__).parent
AVAILABLE_CABS = [p.stem for p in CAB_DIR.glob("*.yml")]

def get_cab_path(name: str) -> Path:
    """Get path to a cab definition."""
    return CAB_DIR / f"{name}.yml"
```

2. **cult-cargo imports lightweight version:**
```toml
# In cult-cargo's pyproject.toml
[tool.poetry.dependencies]
mypackage = "^1.0.0"  # Not mypackage[full]
```

3. **Users run with Stimela:**
```bash
# Native: requires full installation
pip install mypackage[full]
stimela run recipe.yml

# Singularity: uses container (lightweight install sufficient)
pip install mypackage
stimela run recipe.yml -S
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