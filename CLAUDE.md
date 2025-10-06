# CLAUDE.md - Project Context for Claude Code

## Project Overview

**hip-cargo** is a lightweight tool for generating Stimela cab definitions from Python functions decorated with type hints. The project prioritizes **simplicity and minimalism** over feature completeness.

## Core Philosophy

### 1. **Simplicity First**
- Keep implementations straightforward and readable
- Avoid over-engineering solutions
- Prefer explicit over implicit behavior
- Don't add features "just in case" - wait for actual need

### 2. **Lightweight Dependencies**
- Minimize external dependencies
- Only add dependencies when absolutely necessary
- Current dependencies: `typer`, `pyyaml`, `typing-extensions`
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
│   ├── __init__.py          # Exports decorators
│   ├── cli.py               # Typer CLI application
│   ├── decorators.py        # @stimela_cab, @stimela_output
│   ├── introspector.py      # Extract info from functions
│   └── yaml_generator.py    # Generate YAML output
├── tests/
│   └── example_package/     # Example test cases
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

# Run tests manually
python tests/test_decorators.py
```

## Coding Standards

### Type Hints
- Always use type hints for function signatures
- Use `from typing import Any` for generic types
- Use `typing_extensions.Annotated` when needed for forward compatibility

### Functions Over Classes
- Prefer pure functions where possible
- Use functions for transformations and data processing
- Only use classes when:
  - State management is truly necessary
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
- Add comments only when code intent isn't obvious

## What NOT to Do

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
# Good: Simple and clear
def extract_name(func: Any) -> str:
    return func.__name__

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
- Inferring Stimela dtypes from Python type hints and help strings
- Supporting both old-style (`= typer.Option()`) and new-style (`Annotated`) Typer syntax
- Generating YAML cab definitions with inputs and outputs
- Multiple `@stimela_output` decorators for multi-output cabs
- **Reverse generation**: Creating Python function signatures from existing Stimela cab YAML files
- Automatic sanitization of parameter names (hyphens → underscores)
- F-string reference sanitization in output definitions

## Tool Architecture

### Core Modules

```
hip-cargo/
├── src/hip_cargo/
│   ├── decorators.py          # @stimela_cab, @stimela_output
│   ├── introspector.py        # Extract metadata from decorated functions
│   ├── type_mapper.py         # Python types ↔ Stimela dtypes (embedded in introspector)
│   ├── yaml_generator.py      # Generate cab YAML from function metadata
│   ├── cab_to_function.py     # NEW: Generate function from cab YAML (reverse)
│   └── cli.py                 # Typer CLI with two commands
└── tests/
```

### CLI Commands

**`cargo generate-cab`**: Function → YAML cab definition
```bash
cargo generate-cab mypackage.module /path/to/cab.yaml
```

**`cargo generate-function`**: YAML cab → Python function (NEW)
```bash
cargo generate-function /path/to/cab.yaml -o function.py
```

## Target Package Structure

Packages using hip-cargo should follow this structure:

```
scientific-package/
├── src/
│   └── package/
│       ├── operators/         # Heavy algorithms
│       ├── workers/          # Original implementations (optional)
│       └── cli/              # Lightweight CLI wrappers
│           ├── __init__.py   # Main Typer app, registers commands
│           └── command.py    # Individual @stimela_cab decorated functions
├── cabs/                     # Generated cabs at ROOT level (not in src/)
│   ├── __init__.py
│   └── *.yaml
├── scripts/
│   └── generate_cabs.py      # Automation
└── pyproject.toml            # Split dependencies: base vs [full]
```

### Key Patterns

**CLI module structure** (`src/package/cli/__init__.py`):
```python
import typer

app = typer.Typer(name="package", help="...", no_args_is_help=True)

from package.cli.command import command_func
app.command(name="command")(command_func)
```

**Individual command** (`src/package/cli/command.py`):
```python
from typing_extensions import Annotated
import typer
from hip_cargo import stimela_cab, stimela_output

@stimela_cab(name="pkg_cmd", info="...")
@stimela_output(name="output", dtype="File", info="...")
def command_func(
    param: Annotated[Type, typer.Option(help="...")] = default,
):
    """Command description."""
    # Lazy import heavy dependencies
    from package.operators import algorithm
    return algorithm(param)
```

**pyproject.toml pattern**:
```toml
[project]
dependencies = ["typer>=0.12.0", "hip-cargo>=0.1.0"]

[project.optional-dependencies]
full = ["numpy", "jax", ...]  # Heavy scientific stack

[project.scripts]
package = "package.cli:app"
```

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

When adding features, ask:
1. Is this feature explicitly requested?
2. Can it be implemented in <50 lines?
3. Does it require new dependencies?
4. Is there a simpler alternative?

Only proceed if answers align with project philosophy.

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