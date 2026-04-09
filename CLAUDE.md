# CLAUDE.md - Project Context for Claude Code

## Project Overview

**hip-cargo** is a lightweight tool for generating Stimela cab definitions from Python functions decorated with type hints. The project prioritizes **simplicity and minimalism** over feature completeness. When in doubt, consult the principles outlined in [The Twelve Factor App](https://12factor.net/) for guidance on how to work with this code base.

*Note: Detailed domain logic, Python standards, and CI/CD rules have been modularized into the `.claude/rules/` directory for progressive disclosure.*

## Core Dependencies

* Minimize external dependencies.
* Current allowed dependencies: `typer`, `pyyaml`, `libcst`, `ruff`, `typing-extensions`, `tomli` (Python < 3.11 only).
* **Note on Ruff:** `ruff` is a core dependency (not just dev) because `generate-function` runs `ruff format` and `ruff check --fix` on generated code.

## Mandatory Development Workflow

**Always run linting after adding or modifying any code:**

```bash
uv run ruff format . && uv run ruff check . --fix
```

## Project Structure

```
hip-cargo/
├── src/hip_cargo/
│   ├── __init__.py           # Exports decorators, list types, and parsers
│   ├── _container_image.py   # Container image URL (single source of truth)
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
│   │   ├── onboard_cli.py    # Onboard command CLI template
│   │   ├── onboard_core.py   # Onboard command core template
│   │   ├── pyproject.toml
│   │   ├── tbump.toml
│   │   ├── licenses/         # MIT, Apache-2.0, BSD-3-Clause
│   │   └── workflows/        # GitHub Actions workflow templates
│   └── utils/                # Shared utilities
│       ├── __init__.py
│       ├── cab_to_function.py   # Generate function from cab YAML
│       ├── config.py            # Container image URL from _container_image.py
│       ├── decorators.py        # @stimela_cab, @stimela_output
│       ├── introspector.py      # Extract metadata from functions
│       ├── runner.py            # Container fallback execution
│       ├── yaml_comments.py     # YAML comment extraction/preservation
│       └── types.py             # ListInt, ListFloat, ListStr NewTypes + parsers
├── tests/
└── pyproject.toml
```
