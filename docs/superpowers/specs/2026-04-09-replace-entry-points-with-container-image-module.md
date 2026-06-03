# Replace Entry Points with `_container_image.py` Module

**Date**: 2026-04-09
**Status**: Approved
**Scope**: Breaking change to container image storage mechanism

## Problem

hip-cargo 0.1.8 stores the container image URL as a Python entry point:

```toml
[project.entry-points."hip.cargo"]
container-image = "ghcr.io/landmanbester/hip-cargo:latest"
```

Entry point values must be valid Python object references (`module:attribute`) per the [entry-points spec](https://packaging.python.org/en/latest/specifications/entry-points/#data-model). A container image URL like `ghcr.io/landmanbester/hip-cargo:0.1.8` is not a valid reference.

CPython's stdlib `importlib.metadata` is lenient and validates lazily, so it doesn't crash. But the `importlib_metadata` backport (installed as a transitive dependency by dask, jupyter, etc.) validates eagerly: its `EntryPoint.__init__` forces a regex match that raises `ValueError` on construction.

Any package that calls `importlib_metadata.entry_points()` to discover plugins (dask, jupyter, pytest plugins) iterates ALL installed distributions' entry points. The first invalid one crashes the entire call. This means `import dask` fails in any environment where hip-cargo 0.1.8 is installed alongside the `importlib_metadata` backport.

This affects every downstream hip-cargo user, not just pfb-imaging.

## Solution

Replace the entry-point storage with a `_container_image.py` module inside each package. This module contains a single constant:

```python
# src/hip_cargo/_container_image.py
CONTAINER_IMAGE = "ghcr.io/landmanbester/hip-cargo:latest"
```

### Runtime access

`get_container_image()` dynamically imports the module:

```python
def get_container_image(package_name: str) -> str | None:
    import importlib
    try:
        pkg = package_name.replace("-", "_")
        mod = importlib.import_module(f"{pkg}._container_image")
        return mod.CONTAINER_IMAGE
    except (ImportError, AttributeError):
        return None
```

### Why this approach

- **stdlib only**: Uses `importlib.import_module()`, no third-party dependencies needed
- **No CWD dependency**: Works from any directory (reads from installed package)
- **No spec violations**: No entry points, no URL validation issues
- **Simple tag management**: Regex replacement works the same way, just targeting the `.py` file
- **Single source of truth**: One file per package, no TOML/Python duplication

### Alternatives considered

1. **`[tool.hip-cargo]` table in pyproject.toml**: Not preserved in installed metadata, so runtime access requires CWD or a second storage mechanism.
2. **Valid entry point pointing to a Python constant** (`"hip_cargo._meta:CONTAINER_IMAGE"`): Works but adds unnecessary indirection through the entry-point machinery.
3. **`importlib.resources` data file**: Works but a Python constant is more conventional and has no compatibility concerns.

## Changes Required

### 1. New file: `src/hip_cargo/_container_image.py`

Single constant with the image URL. This is the source of truth.

### 2. Remove entry point from `pyproject.toml`

Delete:
```toml
[project.entry-points."hip.cargo"]
container-image = "ghcr.io/landmanbester/hip-cargo:latest"
```

### 3. Remove `importlib_metadata` dependency

The `importlib_metadata >= 9.0.0; python_version < '3.11'` dependency was only needed for entry-point access. With the new approach, it's no longer required by hip-cargo itself. (Downstream packages that don't use it for other purposes can also drop it.)

### 4. Rewrite `utils/config.py`

Replace entry-point iteration with dynamic module import. Change error semantics from `PackageNotFoundError` to returning `None` (package not installed or no `_container_image.py`).

### 5. Update `core/generate_cabs.py`

Remove `PackageNotFoundError` import and conditional `sys.version_info` block. Update the except clause to catch `ImportError` (or just let `get_container_image()` return `None`).

### 6. Update `__init__.py`

Keep `get_container_image` export (API unchanged).

### 7. Update workflows

**`.github/workflows/update-cabs.yml`**:
- Change regex target from `pyproject.toml` to `src/hip_cargo/_container_image.py`
- Change regex from `container-image\s*=\s*".*:` to `CONTAINER_IMAGE\s*=\s*".*:`
- Remove the "Sync environment to refresh package metadata" `uv sync` step (no longer needed; editable installs read the `.py` file directly)
- Update `git diff`/`git add` paths

**`src/hip_cargo/templates/workflows/update-cabs.yml`**: Same changes, with `<PACKAGE_NAME>` placeholders.

### 8. Update `tbump.toml`

- Change the "Update container image tag" `before_commit` hook to target `_container_image.py` instead of `pyproject.toml`
- Remove the `uv sync` step between tag update and cab regeneration (no longer needed)
- Update the `[[file]]` entry to match `_container_image.py` instead of pyproject.toml's entry-point line

**`src/hip_cargo/templates/tbump.toml`**: Same changes with placeholders.

### 9. Update `core/init.py` (project scaffolding)

- Generate `_container_image.py` in each scaffolded project's source directory
- Remove the entry-point section from the template `pyproject.toml`
- Remove `importlib_metadata` from template dependencies

### 10. Update template `pyproject.toml`

Remove the `[project.entry-points."hip.cargo"]` section and the `importlib_metadata` dependency.

### 11. Update template `onboard_core.py`

Update the "Day-to-Day Development: Image Tag Workflow" section to reference `_container_image.py` instead of the entry point in `pyproject.toml`.

### 12. Update tests

- **`test_config.py`**: Rewrite to test module-import approach. Test hip-cargo's own `_container_image.py`, test missing module returns `None`, test nonexistent package returns `None`.
- **`test_container_tag_regex.py`**: Update regex pattern and test strings from TOML `container-image = "..."` to Python `CONTAINER_IMAGE = "..."`.
- **`test_generate_function_body.py`**: No changes needed (tests check for `get_container_image` string presence, which is unchanged).
- **`test_container_fallback_integration.py`**: No changes needed (mocks `get_container_image`, doesn't test its internals).
- **`test_list_types.py`**: No changes needed (checks for `get_container_image` string presence).

### 13. Update CLAUDE.md

Update all references to entry points, `[project.entry-points."hip.cargo"]`, and the image tag lifecycle documentation to reflect the new `_container_image.py` approach.

### 14. Clean up documentation

- Update or remove `docs/using_entry_points_for_metadata.md`
- Update `docs/superpowers/plans/2026-04-07-container-image-discovery.md` if still relevant

## Impact on Downstream Packages

Downstream packages (e.g. pfb-imaging) that adopted the entry-point pattern from hip-cargo 0.1.8 will need to:

1. Replace their `[project.entry-points."hip.cargo"]` section with a `_container_image.py` module
2. Remove `importlib_metadata` dependency if it was only needed for this
3. Update their `tbump.toml` and `update-cabs.yml` to target the `.py` file
4. Bump their hip-cargo dependency to the release containing this fix

This is a breaking change, but the entry-point approach was broken from the start. The fix is straightforward and the `hip-cargo init` template will scaffold the correct pattern going forward.

## Version

This will be released as 0.2.0 (breaking change in how container images are stored and discovered).
