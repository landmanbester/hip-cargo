# Code Review Instructions for hip-cargo

You are an expert code reviewer for the `hip-cargo` project. Your primary role is to review pull requests, identify anti-patterns, and ensure architectural consistency. Keep your reviews concise, direct, and pragmatic. Point out specific violations without unnecessary fluff.

**Important Context:** "hip-cargo" is the exact name of the project. Never expand "hip" into a fabricated acronym (such as Hierarchical Imaging Pipeline) in your reviews or comments.

## 1. Architectural & Dependency Checks
* **Keep it simple:** Flag any speculative abstractions or unnecessary classes. The project strictly prefers functional programming and solutions that just work reliably without over-engineering.
* **Lazy Imports:** In `src/hip_cargo/cli/`, flag any heavy module-level imports. Heavy dependencies must be imported inside function bodies to ensure fast CLI startup.
* **Zero New Dependencies:** Flag any added dependencies for strict justification.

## 2. Critical Syntax & Implementation Rules to Enforce

* **Typer Syntax:** Flag `None` passed as a positional argument to `typer.Option`.
    * ❌ `param: Annotated[str | None, typer.Option(None, help="...")] = None`
    * ✅ `param: Annotated[str | None, typer.Option(help="...")] = None`
* **Comment Preservation (LibCST vs AST):** Flag any use of the `ast` module for parsing decorated functions (it strips comments). The codebase must use LibCST (via `src/hip_cargo/utils/introspector.py`).
* **List Parsing:** Flag manual comma-splitting logic for CLI inputs. Suggest using `ListInt`, `ListFloat`, or `ListStr` from `utils/types.py` paired with their respective parsers.
* **CLI Mode Logic:** Ensure any modifications to `core/init.py` maintain distinct post-init messages for `--cli-mode multi` vs `single`. Typer command promotion behaviors differ between these modes; do not let a PR unify them.

## 3. Container & CI/CD Rules (DO NOT FLAG THESE)

* **Branch-Specific Image Tags:** Generated cab files in `src/*/cabs/*.yml` and `_container_image.py` will often contain branch-specific image tags (e.g., `:feature-branch`). **This is correct.** Do not flag these as bugs or suggest changing them to `:latest`. The CI pipeline handles the conversion to `:latest` upon merge.
* **Workflow Skip Logic:** Workflows use `[skip checks]`, not `[skip ci]`. Ensure that any edits to GitHub Actions workflows maintain the evaluation of this tag via `if: env.SKIP_CHECKS != 'true'`.

## 4. Testing Standards
* Flag tests that write to repository directories instead of using `tempfile.TemporaryDirectory()`.
* Ensure tests for code generation actually compile the output using `compile(code, filename, "exec")`.

## 5. Review Output Format
When providing your review summary, you must strictly format your response using the following categories. If a category has no items, omit it entirely.

```
src/hip_cargo/
├── cli/           # Lightweight CLI wrappers (lazy imports only)
│   └── monitor.py # hip-cargo monitor command (needs monitoring extra)
├── core/          # Core implementations (heavy dependencies here)
├── cabs/          # Generated YAML cab definitions (git-tracked, auto-updated)
├── monitoring/    # Pipeline monitoring (optional, needs hip-cargo[monitoring])
│   ├── cab_resolver.py    # Resolve _include to cab schemas
│   ├── config.py          # MonitorSettings (pydantic-settings, HIPCARGO_ prefix)
│   ├── dispatcher.py      # Centralised WebSocket event fan-out
│   ├── ray_backend.py     # ProgressAggregator actor + RayProgressBackend
│   ├── recipe_discovery.py # Find recipe YAML files in project
│   ├── recipe_parser.py   # Parse stimela recipe DAG structure
│   └── server.py          # FastAPI app (REST + WebSocket, uses Ray Jobs SDK)
├── utils/         # Shared utilities (decorators, introspection, conversion, types)
│   ├── config.py  # pyproject.toml [tool.hip-cargo] reader
│   ├── progress.py        # ProgressEvent, EventType, ProgressBackend protocol (stdlib only)
│   ├── progress_context.py # track_progress() context manager
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

`generate_function()` runs ruff with `cwd=config_file.parent` so first-party package detection matches the target project, not wherever hip-cargo is invoked from. This is critical for roundtrip correctness against external projects.

### 6. Lazy Import Pattern

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

# For monitoring development:
uv sync --group monitoring-dev --group dev --group test
```

**Pre-commit hooks auto-update**:
1. CLI help SVGs (`scripts/update_cli_help.py`)
2. README code snippets (`scripts/update_readme.py`)
3. Cab definitions (via `hip-cargo generate-cabs` CLI)

**Note**: Pre-commit "fails" when hooks modify files. This is expected - review changes, then `git add -u && git commit` again.

**Run tests**:
```bash
# Fast — excludes Ray tests
uv run pytest tests/ -v -m "not slow"
# All tests including Ray integration
uv run pytest tests/ -v
# With coverage:
uv run pytest tests/ --cov=hip_cargo --cov-report=html
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
- `src/hip_cargo/utils/config.py`: Reads `[tool.hip-cargo].image` from nearest `pyproject.toml`
- `src/hip_cargo/utils/progress.py`: ProgressEvent protocol (stdlib only, no monitoring deps needed)
- `src/hip_cargo/utils/progress_context.py`: `track_progress()` context manager
- `src/hip_cargo/core/generate_cabs.py`: Core cab generation logic (skips `skip: True` params, resolves image from pyproject.toml)
- `src/hip_cargo/core/generate_function.py`: Generates Python CLI functions from cab YAML (emits `backend`, `always_pull_images` when image present)
- `src/hip_cargo/monitoring/server.py`: FastAPI server (uses Ray Jobs SDK, not httpx proxy)
- `src/hip_cargo/monitoring/ray_backend.py`: ProgressAggregator Ray actor
- `src/hip_cargo/monitoring/dispatcher.py`: Centralised WebSocket fan-out
- `src/hip_cargo/monitoring/cab_resolver.py`: Resolve _include entries to cab parameter schemas
- `src/hip_cargo/monitoring/recipe_parser.py`: Parse stimela recipe YAML into DAG structure
- `tests/mocks.py`: Shared FakeJobClient, FakeAggregator for testing without Ray
- `CLAUDE.md`: Extended philosophy, anti-patterns, and monitoring implementation details

### Monitoring-specific Patterns

**Server uses Ray Jobs SDK** (`JobSubmissionClient`), not httpx proxy. Sync SDK methods are wrapped with `run_in_executor()` to avoid blocking the event loop.

**Auth middleware returns JSONResponse(401)**, not `raise HTTPException`. `BaseHTTPMiddleware` doesn't properly handle FastAPI's `HTTPException`.

**Test apps bypass the lifespan** by replacing `app.router.lifespan_context` with a no-op that injects fake aggregator/job client/dispatcher.

**Ray tests need `runtime_env={"working_dir": None}`** in `ray.init()` to prevent Ray from packaging the project directory into a separate venv for workers.

**Integration tests use anonymous actors** (not named/detached) for isolation. Named actors persist across tests and cause contamination.

## What NOT to Do

- ❌ Add dependencies without strong justification
- ❌ Use `ast` module for decorated functions (strips comments)
- ❌ Create classes when functions suffice (maintainer prefers functional style)
- ❌ Add abstractions speculatively - wait for actual need
- ❌ Delete tests without explicit request
- ❌ Write test artifacts to repository directories
- ❌ Optimize prematurely - simplicity > performance

## Container Workflow

Image base stored in `pyproject.toml` under `[tool.hip-cargo].image`. Tag derived at runtime by `get_image_tag()`:
- Releases: semantic version from `.tbump_version` sentinel (e.g., `0.1.2`)
- Main branch: `latest`
- Feature branches: `branch-name`

The `@stimela_cab` decorator does **not** contain `image=`. Image is resolved at runtime from project config. Build/publish automated via `.github/workflows/publish-container.yml`.

## Questions Before Implementing

1. Can this be done with stdlib?
2. Can this be a simple function?
3. Is this actually needed now?
4. Will this add dependencies?
5. Is this simple enough for the maintainer's taste?

When in doubt, consult `CLAUDE.md` for extended guidance and [The Twelve-Factor App](https://12factor.net/) for architectural decisions.
