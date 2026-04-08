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
├── utils/         # Shared utilities (decorators, introspection, conversion, types)
│   ├── config.py  # Container image URL from package metadata
│   └── types.py   # ListInt, ListFloat, ListStr NewTypes + parsers
└── recipes/       # Stimela recipes for running via stimela
```

**Key separation**: CLI modules must stay lightweight. Import heavy dependencies inside function bodies, not at module level. This enables fast CLI startup and lightweight installations.

**Entry point**: `hip-cargo` command (see `pyproject.toml` `[project.scripts]`)

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

### 4. Comma-separated List Types

Typer/Click can't handle variable-length lists as a single option value. `hip-cargo` provides `ListInt`, `ListFloat`, `ListStr` NewTypes in `utils/types.py` with paired parser functions:

```python
from hip_cargo.utils.types import ListInt, parse_list_int

channels: Annotated[
    ListInt,
    typer.Option(parser=parse_list_int, help="Channel indices"),
]
# channels is list[int] at runtime — no manual splitting
```

- Introspector maps `ListInt` → `List[int]` stimela dtype
- Reverse generator maps `List[int]` dtype → `ListInt` + `parse_list_int`
- No stimela metadata dict or manual comma-splitting code needed

### 5. Ruff Working Directory

`ruff` is a core dependency (not just dev) because `generate_function()` runs `ruff format` and `ruff check --fix` on generated code. It runs with `cwd=config_file.parent` so first-party package detection matches the target project, not wherever hip-cargo is invoked from. This is critical for roundtrip correctness against external projects.

### 6. Single vs Multi CLI Mode (`hip-cargo init`)

The `--cli-mode` flag controls how the generated CLI is structured:

- **`multi`** (default): Uses `cli_multi.py` template — creates a Typer app with a callback and named subcommands (e.g., `mycli onboard`). Additional commands are registered with `app.command(name="command-name")`.
- **`single`**: Uses `cli_single.py` template — creates a Typer app with a single `app.command()`. Typer automatically promotes the sole command to the root, so `mycli` directly invokes the function. Running `mycli onboard` would give "unexpected extra argument".

This affects the post-init message in `core/init.py`: single mode prints `uv run <cli_command>`, multi mode prints `uv run <cli_command> onboard`. Do NOT unify these — they must differ because of Typer's command promotion behaviour.

### 7. Lazy Import Pattern

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
3. Cab definitions (via `hip-cargo generate-cabs` CLI)

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
- `src/hip_cargo/utils/cab_to_function.py`: Reverse generation (YAML → Python), generates try/except fallback body
- `src/hip_cargo/utils/runner.py`: Container fallback execution (mount resolution, backend detection, command assembly)
- `src/hip_cargo/utils/config.py`: Reads `[project.urls].Container` from installed package metadata
- `src/hip_cargo/core/generate_cabs.py`: Core cab generation logic (skips `skip: True` params, resolves image from pyproject.toml)
- `src/hip_cargo/core/generate_function.py`: Generates Python CLI functions from cab YAML (emits `backend`, `always_pull_images` when image present)
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

The full container image URL (including tag) is stored in `[project.urls].Container` in `pyproject.toml`. At runtime, `get_container_image()` in `utils/config.py` reads this from installed package metadata via `importlib.metadata`.

The `@stimela_cab` decorator does **not** contain `image=`. Image is resolved at runtime from project metadata. Build/publish automated via `.github/workflows/publish-container.yml`.

**IMPORTANT — Generated cab files in `src/*/cabs/*.yml` will contain branch-specific image tags (e.g., `:feature-branch`) on feature branches. This is expected and correct. Do NOT flag these as issues or suggest changing them to `:latest`. After a PR is merged, the `update-cabs` GitHub Actions workflow automatically regenerates the cab files with the correct `:latest` tag and pushes the update. The branch-specific tags are necessary during development for testing with stimela.**

**`[skip ci]` convention**: The `update-cabs` workflow commits with `[skip ci]` in the message. The CI workflow jobs check for this tag and skip, so only `update-cabs` and `publish-container` run after a cab update push. This pattern must be preserved in both `.github/workflows/ci.yml` and the template at `src/hip_cargo/templates/workflows/ci.yml`.

**Image tag lifecycle**: The `Container` URL in `[project.urls]` of `pyproject.toml` tracks the current image tag. On feature branches, the developer must manually update the `Container` tag to match the branch name and run `uv sync` to refresh the package metadata. On merge to main, the `update-cabs` workflow resets the tag to `latest`, runs `uv sync`, and commits `pyproject.toml`, `uv.lock`, and cab YAML files. During releases, `tbump` updates the tag to the semantic version via its before-commit hooks.

## Questions Before Implementing

1. Can this be done with stdlib?
2. Can this be a simple function?
3. Is this actually needed now?
4. Will this add dependencies?
5. Is this simple enough for the maintainer's taste?

When in doubt, consult `CLAUDE.md` for extended guidance and [The Twelve-Factor App](https://12factor.net/) for architectural decisions.
