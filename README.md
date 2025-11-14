# hip-cargo

A guide to designing auto-documenting CLI interfaces using Typer + conversion utilities.
If you are creating a new package the instructions below will guide you on how to structure it.
The `generate-function` utility is available to assist in converting an existing package to the `hip-cargo` format but there will be some manual steps involved.
The philosophy behind this design is to allow having a lightweight version of the package that only installs the bits required to generate `--help` from the CLI and the cab definitions that can then be used with `stimela`. 
The full package should be available as a container image that can be used with `stimela`.
The image should be tagged with the package version so that `stimela` will automatically pull the image that matches the cab configuration.   

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

### 1. Decorate your Python CLI

Something like the following goes in `src/mypackage/cli/process.py`
```python
import typer
from pathlib import Path
from typing import NewType
from typing_extensions import Annotated
from hip_cargo import stimela_cab, stimela_output

# custom types (stimela has e.g. File, URI, MS and Directory)
File = NewType("File", Path)
URI = NewType("URI", Path)
MS = NewType("MS", Path)
Directory = NewType("Directory", Path)

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
    input_ms: Annotated[MS, typer.Argument(parser=MS, help="Input MS to process")],  # note the parser=MS bit. This is required for non-standard types
    output_dir: Annotated[Directory, typer.Option(parser=Directory, help="Output Directory for results")] = Path("./output"),
    threshold: Annotated[float, typer.Option(help="Threshold value")] = 0.5,
):
    """
    Process a data file.
    """
    # All your manual parameter wrangling here
    from mypackage.core.process import process as process_core
    return process_core(*args, **kwargs)
```
Note that `*args` and `**kwargs` need to passed explicitly. 
Then register the command in the `src/mypackage/cli/__init__.py` with something like the following
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

app.command(name="process")(process)

__all__ = ["app"]
```
That's it, if you have something like the following
```toml
[project.scripts]
mypackage = "mypackage.cli:app"
```
in your `pyproject.toml` you should now be able to run
```bash
app --help
```
and
```bash
app process --help
```
from the command line and have a beautifully formatted CLI for your package.
Note that you can register multiple commands under `app`. 

### 2. Generate the Stimela cab definition

If you have the CLI definition you can convert it to a can using e.g.

```bash
cargo generate-cab mypackage.process src/mypackage/cabs/process.yaml
```

This should be automated using `scrips/generate_cabs.py`, but the above command is useful for testing.

### 3. Generate Python function from existing cab (reverse)

If you are converting an existing package to the `hip-cargo` format there is a utility function available viz.

```bash
cargo generate-function /path/to/existing_cab.yaml -o myfunction.py
```

Currently, this won't add things like `rich_output_panel`, but it should help to get you started.
The program should recognize custom types and add the 
```
from pathlib import Path
from typing import NewType

MS = NewType("MS", Path)
```
bit for you. It should also add the `parser=MS` in the `typer.Option()` bit for you.

## Project Structure for hip-cargo Packages

Packages following the hip-cargo pattern should be structured to enable both lightweight cab definitions and full execution environments:

```
my-scientific-package/
├── src/
│   └── mypackage/
│       ├── __init__.py
│       ├── utils/               # Utilities used by core algorithms
│       │   ├── __init__.py
│       │   └── operator.py
│       ├── core/                # Core implementations with standard python type hints (no Annotated or custom types)
│       │   ├── __init__.py
│       │   ├── process.py
│       │   └── analyze.py
│       ├── cli/                 # Lightweight CLI layer
│       │   ├── __init__.py      # Main Typer app
│       │   ├── process.py       # Individual commands
│       │   └── analyze.py
│       └── cabs/                # Generated cab definitions (inside mypackage)
│           ├── __init__.py
│           ├── process.yaml
│           └── analyze.yaml
├── scripts/
│   └── generate_cabs.py        # Automation script
├── Dockerfile                   # For containerization
├── pyproject.toml
└── README.md
```

### Key Principles

1. **Separate CLI from implementation**: Keep CLI modules lightweight with lazy imports. Keep them all in the `src/mypackage/cli` directory and define the CLI for each command in a separate file. Construct the main Typer app in `src/mypackage/cli/__init__.py` and register commands there. 
2. **Separate cabs directory at same level as `cli`**: Use `hip-cargo` to auto-generate cabs into in `src/mypackage/cabs/` directory with the `generate_cabs.py` script. There should be a separate file for each cab. 
3. **Single app, multiple commands**: Use one Typer app that registers all commands. If you need a separate app you might as well create a separate repository for it.
4. **Lazy imports**: Import heavy dependencies (NumPy, JAX, Dask) only when executing
5. **Linked GitHub package with container image**: Maintain an up to date `Dockerfile` that installs the full package and use **Docker** (or **Podman**) to upload the image to the GitHub Container registry. Link this to your GitHub repository.  

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
from typing import NewType
from typing_extensions import Annotated
import typer
from hip_cargo import stimela_cab, stimela_output

MS = NewType("MS", Path)

@stimela_cab(name="mypackage_process", info="Process data")
@stimela_output(name="output", dtype="File", info="{input_file}.out")
def process(
    input_ms: Annotated[MS, typer.Argument(parser=MS, help="Input File")],
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

CABS_DIR = Path("src/mypackage/cabs")
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
# src/mypackage/cabs/__init__.py
from pathlib import Path

CAB_DIR = Path(__file__).parent
AVAILABLE_CABS = [p.stem for p in CAB_DIR.glob("*.yml")]

def get_cab_path(name: str) -> Path:
    """Get path to a cab definition."""
    return CAB_DIR / f"{name}.yml"
```

2. **cult-cargo imports lightweight version:**

We have to decide whether we want to add this kind of thing to `cult-cargo`:

```toml
# In cult-cargo's pyproject.toml
[tool.poetry.dependencies]
mypackage = "^1.0.0"  # Not mypackage[full]
```

However, it should be possible to just 
```bash
uv pip install mypackage==x.x.x
```
without any dependency conflicts. If not we have to think about ephemeral virtual environments.

3. **Users run with Stimela:**
```bash
# Native: requires full installation
pip install mypackage[full]
stimela run recipe.yml

# Singularity: uses container (lightweight install sufficient)
pip install mypackage
stimela run recipe.yml -S
```

## Container Images and GitHub Actions

For Stimela to use your package in containerized environments, you should publish OCI container images to GitHub Container Registry (ghcr.io). This section shows how to automate this with GitHub Actions.

### 1. Create a Dockerfile

Add a `Dockerfile` at the root of your repository:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install uv for fast package installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy package files
COPY pyproject.toml README.md ./
COPY src/ src/

# Install package with full dependencies using uv (much faster than pip)
RUN uv pip install --system --no-cache .

# Make CLI available
ENTRYPOINT ["mypackage"]
CMD ["--help"]
```

### 2. Set up GitHub Actions Workflow

Create `.github/workflows/publish-container.yml`:

```yaml
name: Build and Publish Container

on:
  push:
    tags:
      - 'v*.*.*'  # Trigger on version tags (e.g., v1.0.0)
  workflow_dispatch:  # Allow manual triggering

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Log in to Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata (tags, labels)
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=semver,pattern={{major}}
            type=sha,prefix={{branch}}-

      - name: Build and push Docker image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
```

### 3. Link Container to GitHub Package

To associate the container image with your repository:

1. **Automatic linking**: If your workflow pushes to `ghcr.io/username/repository-name`, GitHub automatically creates a package linked to the repository.

2. **Manual linking** (if needed):
   - Go to your repository on GitHub
   - Navigate to the "Packages" section
   - Click on your container package
   - Click "Connect repository" in the sidebar
   - Select your repository from the dropdown

3. **Set package visibility**:
   - In the package settings, set visibility to "Public" for open-source projects
   - This allows Stimela to pull images without authentication

### 4. Version Tagging Best Practices

The workflow above creates multiple tags for each release:

```bash
# For release v1.2.3, creates:
ghcr.io/username/mypackage:1.2.3    # Full version
ghcr.io/username/mypackage:1.2      # Minor version
ghcr.io/username/mypackage:1        # Major version
ghcr.io/username/mypackage:main-sha123456  # Branch + commit SHA
```

This allows users to pin to specific versions or track latest minor/major releases.

### 5. Triggering a Build

**Automated (recommended):**
```bash
# Create and push a version tag
git tag v1.0.0
git push origin v1.0.0
```

The GitHub Action will automatically build and publish the container.

**Manual:**
- Go to "Actions" tab in GitHub
- Select "Build and Publish Container"
- Click "Run workflow"

### 6. Using the Container with Stimela

Once published, users can reference your container in Stimela recipes:

```yaml
cabs:
  - name: mypackage
    image: ghcr.io/username/mypackage:1.0.0
```

Stimela will automatically pull the matching version based on the cab configuration.

### 7. Local Testing

Test your container locally before pushing:

```bash
# Build
docker build -t mypackage:test .

# Run
docker run --rm mypackage:test --help
docker run --rm mypackage:test process --help

# Test with mounted data
docker run --rm -v $(pwd)/data:/data mypackage:test process /data/input.ms
```

## Type Inference

`hip-cargo` automatically recognizes custom `stimela` types. The `generate-cab` command should add
```python
from pathlib import Path
from typing import NewType

MS = NewType("MS", Path)
Directory = NewType("Directory", Path)
URI = NewType("URI", Path)
File = NewType("File", Path)
```

to the preamble of functions generated from cabs that use these types.
It should also add the `parser` bit to the type hint Annotation e.g. for the custom `MS` dtype we need  
```
def process(input_ms: Annotated[MS, typer.Option(parser=MS)]):
    pass
```
One quirk of this approach is that parameters which have `None` as the default need to be defined as e.g.
```
def process(input_ms: Annotated[MS | None, typer.Option(parser=MS)]) = None:
    pass
```
Python then parses this as `Optional[MS]` which is just an alias for `Union[MS | None]`. This should be handled correctly such that the `generate-cab` command places `dtype: MS` in the cab definition and the `generate-function` command correctly generates the function signature above. These custom types are currently limited to only two possible types in the `Union` and should be specified using the newer `dtype1 | dtype2` format in the function definition (one of which may be `None`). All standard python types should just work.

## Decorators

### `@stimela_cab`

Marks a function as a Stimela cab.

- `name`: Cab name
- `info`: Description
- `policies`: Optional dict of cab-level policies

### `@stimela_output`

Defines a `stimela` output. When defining functions from cabs the `generate-function` command should check for the following parameter fields

- `name`: Output name (top level, one below `cabs`)
- `dtype`: Data type (File, Directory, MS, etc.)
- `info`: Help string
- `required`: Whether output is required (default: False)
- `implicit`: If implicit is `True` the parameter should not be placed in the function definition. If implicit is `False` (the default), the parameter needs to be added to the function signature.

## Features

- ✅ Automatic type inference from Python type hints
- ✅ Support for Typer Arguments (positional) and Options
- ✅ Multiple outputs automatically added to function signature if they are not implicit  
- ✅ List types with automatic `repeat: list` policy
- ✅ Proper handling of default values and required parameters

## Development

This project uses:
- [uv](https://github.com/astral-sh/uv) for dependency management
- [ruff](https://github.com/astral-sh/ruff) for linting and formatting
- [typer](https://typer.tiangolo.com/) for the CLI

## License

MIT License