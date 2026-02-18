# CLAUDE.md - Project Context for Claude Code

## Project Overview

**hip-cargo** is a lightweight tool for generating Stimela cab definitions from Python functions decorated with type hints. The project prioritizes **simplicity and minimalism** over feature completeness. When in doubt, consult the principles outlined in [The Twelve Factor App](https://12factor.net/) for guidance on how to work with this code base.

## Core Philosophy

### 1. **Simplicity First**
- Keep implementations straightforward and readable
- Avoid over-engineering solutions
- Prefer explicit over implicit behavior
- Don't add features "just in case" - wait for actual need

### 2. **Lightweight Dependencies**
- Minimize external dependencies
- Only add dependencies when absolutely necessary
- Current dependencies: `typer`, `pyyaml`, `libcst`, `typing-extensions`
- Question: "Can this be done with stdlib?" before adding a dependency

### 3. **Modern Python Best Practices**
- Python 3.10+ features are allowed and encouraged
- Use type hints consistently
- Follow PEP 8 style (enforced by ruff)
- Prefer functional approaches over classes when possible (aligns with maintainer's preference)

## Project Structure

```
hip-cargo/
├── src/hip_cargo/
│   ├── __init__.py           # Exports decorators
│   ├── cabs/                 # Generated cab definitions (YAML)
│   │   ├── __init__.py
│   │   ├── generate_cabs.yml
│   │   ├── generate_function.yml
│   │   └── init.yml
│   ├── cli/                  # Lightweight CLI wrappers
│   │   ├── __init__.py       # Main Typer app, registers commands
│   │   ├── generate_cabs.py
│   │   ├── generate_function.py
│   │   └── init.py           # hip-cargo init command
│   ├── core/                 # Core implementations (lazy-loaded)
│   │   ├── __init__.py
│   │   ├── generate_cabs.py
│   │   ├── generate_function.py
│   │   └── init.py           # Project scaffolding logic
│   ├── recipes/              # Stimela recipes for running via stimela
│   │   ├── __init__.py
│   │   └── gen_cabs.yml
│   ├── templates/            # Template files for hip-cargo init
│   │   ├── __init__.py
│   │   ├── cli_multi.py      # Multi-command CLI template
│   │   ├── cli_single.py     # Single-command CLI template
│   │   ├── Dockerfile
│   │   ├── generate_cabs.py  # Template generate_cabs script
│   │   ├── onboard_cli.py    # Onboard command CLI template
│   │   ├── onboard_core.py   # Onboard command core template
│   │   ├── pyproject.toml
│   │   ├── tbump.toml
│   │   ├── licenses/         # MIT, Apache-2.0, BSD-3-Clause
│   │   └── workflows/        # GitHub Actions workflow templates
│   └── utils/                # Shared utilities
│       ├── __init__.py
│       ├── cab_to_function.py   # Generate function from cab YAML
│       ├── decorators.py        # @stimela_cab, @stimela_output
│       └── introspector.py      # Extract metadata from functions
├── scripts/                  # Automation scripts
│   └── generate_cabs.py
├── tests/
└── pyproject.toml
```

## Development Tools

- **Package Manager**: `uv` (Astral)
- **Linting/Formatting**: `ruff`
- **CLI Framework**: `typer`

### Running Tools

```bash
# Format code
uv run ruff format .

# Check and auto-fix issues
uv run ruff check . --fix

# Run tests
python -m pytest tests/ -v

# Run the CLI
hip-cargo --help
```

### Test Infrastructure

- All tests use `tempfile.TemporaryDirectory()` for isolated temporary file handling
- No test artifacts written to the repository directory
- Tests automatically clean up after themselves
- Comment preservation tested through multiple roundtrip scenarios

## Coding Standards

### Type Hints
- Always use type hints for function signatures
- Use `from typing import Any` for generic types
- Use `typing_extensions.Annotated` when needed for forward compatibility but assume the project only supports python 3.10+. Do not import from `typing_extensions` unless required.

### Functions Over Classes
- Prefer pure functions where possible
- Use functions for transformations and data processing
- Only use classes when:
  - State management is truly beneficial
  - You need inheritance or polymorphism
  - The maintainer explicitly requests it

### Error Handling
- Be explicit about error cases
- Provide helpful error messages
- Let exceptions propagate unless there's a good reason to catch them
- Use `typer.Exit(code=1)` for CLI errors

### Documentation
- Use Google-style docstrings
- Document Args, Returns, and Raises
- Keep docstrings concise but informative
- Add comments when code intent isn't obvious, don't add long unnecessary comments if the intent is clear, prefer short inline comments in this case

## What NOT to Do

- Never delete a test unless instructed
- Never keep unnecessary dependencies hanging around
- Don't add one level deep utility functions like the following, rather just access the object method directly:
```python
def extract_name(func: Any) -> str:
    return func.__name__
```

❌ **Don't add these without explicit request:**
- Complex abstractions or frameworks
- Configuration systems beyond what exists
- Extensive plugin architectures
- Over-engineered validation frameworks
- Async/await unless performance demands it
- ORM-style patterns
- Custom metaclasses or descriptors
- Clever magic methods


❌ **Don't optimize prematurely:**
- Keep code simple first
- Only optimize if there's a measured performance problem
- Readability > performance in most cases

## What TO Do

✅ **Simple, direct implementations:**
```python
# Avoid: Over-engineered
class FunctionMetadataExtractor:
    def __init__(self, strategy: ExtractionStrategy):
        self._strategy = strategy

    def extract(self, func: Any) -> Metadata:
        return self._strategy.apply(func)
```

✅ **Explicit over implicit:**
```python
# Good: Clear what's happening
def infer_dtype(type_hint: Any, help_text: str) -> str:
    if "Directory" in help_text:
        return "Directory"
    return "File"

# Avoid: Magic inference
def infer_dtype(type_hint: Any, help_text: str) -> str:
    return DtypeInferenceEngine.infer(type_hint, help_text)
```

✅ **Functional style:**
```python
# Good: Pure function
def generate_yaml(data: dict) -> str:
    return yaml.safe_dump(data, sort_keys=False)

# Avoid unless needed: Stateful class
class YamlGenerator:
    def __init__(self):
        self._config = {...}

    def generate(self, data: dict) -> str:
        return yaml.safe_dump(data, **self._config)
```

## Current Feature Set

hip-cargo currently supports:
- Extracting function metadata from `@stimela_cab` decorator
- Parsing Google-style docstrings for parameter descriptions
- Inferring Stimela dtypes from Python type hints
- Only new-style (`Annotated`) Typer syntax
- Generating YAML cab definitions with inputs and outputs
- Multiple `@stimela_output` decorators for multi-output cabs
- **Reverse generation**: Creating Python function signatures from existing Stimela cab YAML files
- Automatic sanitization of parameter names (hyphens → underscores)
- F-string reference sanitization in output definitions
- **Comment preservation**: Full roundtrip preservation of inline comments (e.g., `# noqa: E501`)
- **Stimela metadata dictionary**: Optional `{"stimela": {...}}` dict in `Annotated` type hints for explicit dtype overrides and Stimela-specific fields
- **Project scaffolding**: `hip-cargo init` creates a complete project with CI/CD, containerisation, pre-commit hooks, and an onboarding command

### Init Command (`hip-cargo init`)

Scaffolds a new project with:
- src layout with `cli/`, `core/`, `cabs/` directories
- GitHub Actions workflows (CI, publish, container, update-cabs)
- Pre-commit hooks (ruff + cab generation)
- Dockerfile, tbump config, license
- An `onboard` command that prints CI/CD setup instructions

Templates live in `src/hip_cargo/templates/` and use `<PLACEHOLDER>` substitution (e.g. `<PROJECT_NAME>`, `<PACKAGE_NAME>`, `<GITHUB_USER>`).

Post-generation steps in `core/init.py`: `uv sync` → `pytest` → `hip-cargo generate-cabs` → `ruff format/check` → `git init/add/commit` → `pre-commit install`.

## Implementation Details

### LibCST-based Parsing (Current)

The project uses [LibCST](https://libcst.readthedocs.io/) (Concrete Syntax Tree) for parsing Python code. This preserves all formatting details including comments, whitespace, and formatting tokens.

**Key advantages:**
- Preserves inline comments through full roundtrip (CLI → YAML → CLI)
- Maintains code formatting and style
- Provides native `.evaluated_value` for string literals
- Avoids risky `eval()` calls

**Key functions:**
- `parse_decorator_libcst()`: Extract decorator metadata including inline comments
- `extract_input_libcst()`: Parse function parameters with comment preservation
- `parse_annotated_libcst()`: Parse `Annotated[Type, metadata]` directly from CST nodes
- `get_cst_value()`: Recursively extract Python values from CST nodes without eval

**Comment handling:**
- Inline comments detected via regex pattern `r'\s{2,}#'` (PEP 8: 2+ spaces before #)
- Comments stored in YAML as trailing YAML comments (e.g., `field: value  # comment`)
- Multi-line info fields format each sentence on a new line, comment on last line
- `format_info_fields()` ensures proper YAML formatting with comment preservation

### Stimela Metadata Dictionary (Recommended for Dtype Overrides)

Input parameters can optionally include a `stimela` metadata dict in their `Annotated` type hints to specify Stimela-specific cab metadata that can't be inferred from type hints or typer.Option(). This is the **recommended and current way** to override dtypes and add Stimela-specific fields:

**Syntax:**
```python
from pathlib import Path
from typing import Annotated, NewType
import typer

File = NewType("File", Path)

def process_data(
    input_file: Annotated[
        File,
        typer.Option(..., parser=Path, help="Input file"),
        {"stimela": {
            "must_exist": True,           # File must exist before task runs
            "policies": {"io": "copy"},   # Custom policies beyond positional/repeat
        }}
    ],
    output_dir: Annotated[
        Path | None,
        typer.Option(parser=Path, help="Output directory"),
        {"stimela": {
            "dtype": "Directory",  # Override inferred dtype (Path -> Directory)
            "mkdir": True,         # Create directory if it doesn't exist
        }}
    ] = None,
):
    """Process data files."""
    pass
```

**Behavior:**
- **Completely optional**: Dict can be omitted entirely
- **All fields optional**: Any subset of fields can be specified
- **Namespaced**: Use `{"stimela": {...}}` to avoid conflicts
- **Explicit override**: Values in stimela dict always override inference
- **Policies merge**: Inferred policies (positional, repeat) + explicit policies combine
- **Arbitrary fields**: Any field allowed (forward-compatible, no validation yet)
- **Full roundtrip**: CLI → YAML → CLI preserves all stimela metadata

**Handled automatically (don't need stimela dict):**
- `dtype`: Inferred from type hint (File, Directory, str, int, etc.)
- `required`: Inferred from `...` vs default value
- `default`: From function default value
- `info`: From typer.Option(help="...")
- `choices`: From Literal[...] type
- `policies.positional`: Auto-added for required params
- `policies.repeat`: Auto-added for List types

**When to use stimela dict:**
- Override dtype (e.g., Path → Directory, or str → List[int] for comma-separated values)
- Add Stimela-specific fields: `must_exist`, `mkdir`, `implicit`
- Add custom policies: `io`, `skip`, `copy_to_output`
- Add arbitrary metadata for future Stimela features
- **Note**: For List[int] and List[float] dtypes, the type hint should be `str` (for comma-separated input) and the stimela dict should specify `{"stimela": {"dtype": "List[int]"}}` to preserve the dtype during roundtrip

**Implementation:**
- Parsed by `extract_stimela_metadata_libcst()` in `introspector.py`
- Merged with inferred metadata in `extract_input_libcst()`
- Generated in roundtrip by `generate_parameter_signature()` in `cab_to_function.py`

## Critical Implementation Details

### Typer Option/Argument Syntax (IMPORTANT)

**NEVER** use `None` as a positional argument to `typer.Option()`:
```python
# WRONG - causes AttributeError
param: Annotated[str | None, typer.Option(None, help="...")] = None

# CORRECT
param: Annotated[str | None, typer.Option(help="...")] = None
```

**Pattern Summary:**
- Required: `Annotated[Type, typer.Option(..., help="...")]` (no `= default`)
- Optional with default: `Annotated[Type, typer.Option(help="...")] = default`
- Optional None: `Annotated[Type | None, typer.Option(help="...")] = None`

### Parameter Name Sanitization

- Python identifiers cannot contain hyphens
- All parameter names: hyphens → underscores (`model-name` → `model_name`)
- F-string references in outputs: `{current.output-filename}` → `{current.output_filename}`
- This is handled automatically by `cab_to_function.py`

### Lazy Imports Pattern

CLI modules should be lightweight. Import heavy dependencies only when executing:

```python
def process(...):
    """Process data."""
    # Import here, not at top of file
    from mypackage.operators import heavy_algorithm
    return heavy_algorithm(...)
```

This keeps CLI startup fast and allows lightweight installation for cab definitions only.

## Examples of Good Changes

✅ **Adding support for a new Stimela dtype:**
- Small, focused change
- Clear use case
- Minimal code addition

✅ **Improving error messages:**
- Better user experience
- No new dependencies
- Simple implementation

✅ **Supporting a new docstring format:**
- Requested feature
- Can use stdlib or existing deps
- Contained to one module

## Examples of Changes to Avoid

❌ **Adding a plugin system for custom type mappers:**
- Over-engineered for current needs
- Adds complexity
- No explicit request

❌ **Creating an abstract base class for extractors:**
- Premature abstraction
- Functional approach works fine
- Adds mental overhead

❌ **Implementing a custom validation DSL:**
- Way too complex
- Use Python's existing features
- Not requested

## Questions to Ask Before Implementing

1. **Can this be done with stdlib?** → Use stdlib
2. **Can this be a simple function?** → Make it a function
3. **Is this actually needed now?** → If no, defer
4. **Will this add dependencies?** → Probably avoid
5. **Would the maintainer call this simple?** → If no, simplify

## Maintainer Preferences

- **Background**: Senior scientific software developer
- **Experience**: Python, NumPy, Numba, JAX, Ray, Dask
- **Style**: Functional programming preferred
- **Philosophy**: Simple, explicit, lightweight

When in doubt, prefer the simpler solution.
