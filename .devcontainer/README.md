# GitHub Codespace Configuration

This directory contains the configuration for GitHub Codespaces, allowing you to develop hip-cargo in a cloud-based VS Code environment.

## What's Included

- **Python 3.12** base image
- **Git** version control
- **VS Code Extensions:**
  - Python language support with Pylance
  - Ruff linter and formatter
  - TOML and YAML support
  - Python debugger

## Automatic Setup

When you launch a Codespace, it will automatically:
1. Install `uv` package manager
2. Sync all project dependencies (including dev and test extras)
3. Configure the Python interpreter to use the virtual environment
4. Set up pytest for testing
5. Enable format-on-save with Ruff

## Usage

1. Go to your GitHub repository
2. Click the "Code" button
3. Select the "Codespaces" tab
4. Click "Create codespace on main" (or your current branch)

Your development environment will be ready in a few minutes!

## Running Commands

Once your Codespace is ready, you can:

```bash
# Run tests
pytest

# Run the CLI
cargo --help

# Generate a cab
cargo generate-cab mypackage.process output.yaml

# Format code
ruff format .

# Lint code
ruff check .
```
