# AI Agent Instructions for hip-cargo

## Project Overview

**hip-cargo** generates Stimela cab YAML definitions from Python functions decorated with `@stimela_cab`. It enables bidirectional conversion: Python CLI → YAML cab → Python CLI with full comment preservation.

**Core philosophy**: Simplicity over features. Functional programming preferred. Minimize dependencies. Explicit over implicit.

## Communication Guidelines

**Response style**: Professional but friendly. Keep responses concise (1-3 sentences unless complex work). Explain reasoning when non-obvious, but avoid unnecessary fluff.

**Implementation approach**: Always ask before making changes. Propose edits but wait for confirmation before implementing.

**File references**: Use backticks for file/path mentions: `src/hip_cargo/utils/decorators.py` or `src/hip_cargo/utils/decorators.py:42` for line numbers.

**Formatting**: No emojis. Use clear technical language.

## Architecture

```
src/hip_cargo/
├── cli/           # Lightweight CLI wrappers (lazy imports only)
├── core/          # Core implementations (heavy dependencies here)
├── cabs/          # Generated YAML cab definitions (git-tracked, auto-updated)
├── utils/         # Shared utilities (decorators, introspection, conversion)
└── recipes/       # Stimela recipes for running via stimela
```

**Key separation**: CLI modules must stay lightweight. Import heavy dependencies inside function bodies, not at module level. This enables fast CLI startup and lightweight installations.

**Entry point**: `cargo` command (see `pyproject.toml` `[project.scripts]`)

## Critical Patterns

### 1. Typer Syntax (NEVER use None as positional arg)

```python
# ✅ CORRECT
param: Annotated[str | None, typer.Option(help="...")] = None

# ❌ WRONG - causes AttributeError
param: Annotated[str | None, typer.Option(None, help="...")] = None
```

### 2. Comment Preservation with LibCST

The project uses **LibCST** (Concrete Syntax Tree) for full roundtrip comment preservation:
- Inline comments detected via `r'\s{2,}#'` (PEP 8: 2+ spaces before #)
- Comments stored as YAML trailing comments: `field: value  # comment`
- Wide YAML width (`YAML_MAX_WIDTH = 10000`) prevents line wrapping that would break comments

**Never** use `ast` module for parsing decorated functions - it strips comments. Always use LibCST functions in `src/hip_cargo/utils/introspector.py`.

### 3. Parameter Name Sanitization

Stimela cabs use hyphens (`model-name`), but Python requires underscores (`model_name`):
- All parameter names: hyphens → underscores automatically
- F-string references in outputs: `{current.output-filename}` → `{current.output_filename}`
- Handled by `src/hip_cargo/utils/cab_to_function.py`

### 4. Lazy Import Pattern

```python
# In cli/mycommand.py
def mycommand(...):
    """Docstring."""
    from hip_cargo.core.mycommand import mycommand as core_impl  # noqa: E402
    return core_impl(...)
```

## Development Workflow

**Setup**:
```bash
uv sync --group dev --group test
uv run pre-commit install
```

**Pre-commit hooks auto-update**:
1. CLI help SVGs (`scripts/update_cli_help.py`)
2. README code snippets (`scripts/update_readme.py`)
3. Cab definitions (`scripts/generate_cabs.py`)

**Note**: Pre-commit "fails" when hooks modify files. This is expected - review changes, then `git add -u && git commit` again.

**Run tests**:
```bash
python -m pytest tests/ -v
# With coverage:
python -m pytest tests/ --cov=hip_cargo --cov-report=html
```

**Format/lint**:
```bash
uv run ruff format .
uv run ruff check . --fix
```

## Testing Standards

- Use `tempfile.TemporaryDirectory()` - never write to repo directories
- Test comment preservation through multiple roundtrips (CLI → YAML → CLI)
- All generated code must compile: `compile(code, filename, "exec")`
- Tests follow pytest conventions (see `[tool.pytest.ini_options]` in `pyproject.toml`)

## Key Files Reference

- `src/hip_cargo/utils/decorators.py`: `@stimela_cab`, `@stimela_output` decorators
- `src/hip_cargo/utils/introspector.py`: LibCST-based metadata extraction (comment-preserving)
- `src/hip_cargo/utils/cab_to_function.py`: Reverse generation (YAML → Python)
- `src/hip_cargo/core/generate_cabs.py`: Core cab generation logic
- `CLAUDE.md`: Extended philosophy and anti-patterns

## What NOT to Do

- ❌ Add dependencies without strong justification
- ❌ Use `ast` module for decorated functions (strips comments)
- ❌ Create classes when functions suffice (maintainer prefers functional style)
- ❌ Add abstractions speculatively - wait for actual need
- ❌ Delete tests without explicit request
- ❌ Write test artifacts to repository directories
- ❌ Optimize prematurely - simplicity > performance

## Container Workflow

Image tagging strategy:
- Releases: semantic version (e.g., `0.1.2`)
- Main branch: `latest`
- Feature branches: `branch-name`

Build/publish automated via `.github/workflows/publish-container.yml`.

## Questions Before Implementing

1. Can this be done with stdlib?
2. Can this be a simple function?
3. Is this actually needed now?
4. Will this add dependencies?
5. Is this simple enough for the maintainer's taste?

When in doubt, consult `CLAUDE.md` for extended guidance and [The Twelve-Factor App](https://12factor.net/) for architectural decisions.
