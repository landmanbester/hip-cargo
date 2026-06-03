# Replace Entry Points with `_container_image.py` Module — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the spec-violating `[project.entry-points."hip.cargo"]` container image storage with a `_container_image.py` module per package, fixing the `importlib_metadata` crash that breaks dask/jupyter/pytest in any environment where hip-cargo is installed.

**Architecture:** Each package stores its container image URL as a Python constant in `_container_image.py`. At runtime, `get_container_image()` dynamically imports the target package's module. Workflows and tbump update the `.py` file directly instead of rewriting a TOML entry point.

**Tech Stack:** Python stdlib (`importlib`), ruff, pytest, GitHub Actions, tbump

**Spec:** `docs/superpowers/specs/2026-04-09-replace-entry-points-with-container-image-module.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `src/hip_cargo/_container_image.py` | Single source of truth for hip-cargo's container image URL |
| Modify | `src/hip_cargo/utils/config.py` | Rewrite `get_container_image()` to use dynamic module import |
| Modify | `src/hip_cargo/core/generate_cabs.py:1-14,55-63` | Remove `PackageNotFoundError` import, simplify error handling |
| Modify | `src/hip_cargo/__init__.py:1-3` | Keep `get_container_image` export (no change needed) |
| Modify | `pyproject.toml:25-41` | Remove entry-point section, remove `importlib_metadata` dep |
| Modify | `tbump.toml:30-36,60-68` | Retarget tag regex and `[[file]]` to `_container_image.py` |
| Modify | `.github/workflows/update-cabs.yml:51-62,73,84` | Retarget regex, remove `uv sync` step, update paths |
| Modify | `src/hip_cargo/templates/pyproject.toml:18-29` | Remove entry-point section, remove `importlib_metadata` dep |
| Modify | `src/hip_cargo/templates/tbump.toml:28-29,66-68` | Retarget tag regex and `[[file]]` to `_container_image.py` |
| Modify | `src/hip_cargo/templates/workflows/update-cabs.yml:50-69,80` | Retarget regex, remove `uv sync`, update paths |
| Modify | `src/hip_cargo/core/init.py:86-98` | Generate `_container_image.py` in scaffolded projects |
| Modify | `src/hip_cargo/templates/onboard_core.py:146-172` | Update image tag workflow docs |
| Modify | `tests/test_config.py` | Rewrite tests for module-import approach |
| Modify | `tests/test_container_tag_regex.py` | Update regex and test strings to Python syntax |
| Modify | `CLAUDE.md` | Update all entry-point references |
| Delete | `docs/using_entry_points_for_metadata.md` | No longer relevant |

---

### Task 1: Create `_container_image.py` and rewrite `get_container_image()`

**Files:**
- Create: `src/hip_cargo/_container_image.py`
- Modify: `src/hip_cargo/utils/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of `tests/test_config.py`:

```python
"""Tests for container image resolution from package metadata."""

import pytest

from hip_cargo.utils.config import get_container_image


class TestGetContainerImage:
    """Test get_container_image reads from _container_image module."""

    @pytest.mark.unit
    def test_returns_image_for_hip_cargo(self):
        """hip-cargo's own _container_image.py has a CONTAINER_IMAGE constant."""
        image = get_container_image("hip-cargo")
        assert image is not None
        assert image.startswith("ghcr.io/")

    @pytest.mark.unit
    def test_returns_none_for_package_without_container(self):
        """Packages without a _container_image module should return None."""
        image = get_container_image("pytest")
        assert image is None

    @pytest.mark.unit
    def test_returns_none_for_nonexistent_package(self):
        """Non-existent package should return None (not raise)."""
        image = get_container_image("nonexistent-package-xyz-12345")
        assert image is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/bester/software/hip-cargo && python -m pytest tests/test_config.py -v`

Expected: `test_returns_none_for_nonexistent_package` FAILS because current code raises `PackageNotFoundError` instead of returning `None`.

- [ ] **Step 3: Create `_container_image.py`**

Create `src/hip_cargo/_container_image.py`:

```python
CONTAINER_IMAGE = "ghcr.io/landmanbester/hip-cargo:latest"
```

- [ ] **Step 4: Rewrite `utils/config.py`**

Replace the entire contents of `src/hip_cargo/utils/config.py`:

```python
"""Read container image from installed package metadata."""

import importlib


def get_container_image(package_name: str) -> str | None:
    """Return the container image registered in a package's _container_image module.

    Dynamically imports ``<package>._container_image`` and reads the
    ``CONTAINER_IMAGE`` constant. This works from any directory because it
    reads from the installed package, not from ``pyproject.toml``.

    Args:
        package_name: The distribution name of the package (e.g. 'pfb-imaging').
            Hyphens are converted to underscores for the import.

    Returns:
        The full container image string (including tag), or None if the
        package is not installed or has no ``_container_image`` module.
    """
    pkg = package_name.replace("-", "_")
    try:
        mod = importlib.import_module(f"{pkg}._container_image")
        return getattr(mod, "CONTAINER_IMAGE", None)
    except (ImportError, ModuleNotFoundError):
        return None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/bester/software/hip-cargo && python -m pytest tests/test_config.py -v`

Expected: All 3 tests PASS.

- [ ] **Step 6: Lint**

Run: `cd /home/bester/software/hip-cargo && uv run ruff format . && uv run ruff check . --fix`

- [ ] **Step 7: Commit**

```bash
cd /home/bester/software/hip-cargo
git add src/hip_cargo/_container_image.py src/hip_cargo/utils/config.py tests/test_config.py
git commit -m "feat: replace entry-point lookup with _container_image module import

get_container_image() now dynamically imports <package>._container_image
instead of reading from entry points. This fixes the importlib_metadata
crash that broke dask/jupyter in environments with hip-cargo installed."
```

---

### Task 2: Remove entry point and `importlib_metadata` dependency from `pyproject.toml`

**Files:**
- Modify: `pyproject.toml:25-41`
- Modify: `src/hip_cargo/core/generate_cabs.py:1-14,55-63`

- [ ] **Step 1: Remove the entry-point section and dependency from `pyproject.toml`**

In `pyproject.toml`, remove the `importlib_metadata` line from dependencies:

```
    "importlib_metadata >= 9.0.0; python_version < '3.11'",
```

Remove the entire entry-points section:

```toml
[project.entry-points."hip.cargo"]
container-image = "ghcr.io/landmanbester/hip-cargo:latest"
```

After editing, the dependencies list should be:
```toml
dependencies = [
    "typer>=0.12.0",
    "pyyaml>=6.0",
    "typing-extensions>=4.15.0",
    "libcst==1.8.6",
    "tomli>=2.0; python_version < '3.11'",
    "ruff>=0.13.2",
]
```

And the sections between `[project.urls]` and `[project.scripts]` should have no entry-points block.

- [ ] **Step 2: Simplify `core/generate_cabs.py` imports**

In `src/hip_cargo/core/generate_cabs.py`, replace lines 1-14:

```python
"""Core logic for generating Stimela cab definitions from Python modules."""

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    from importlib.metadata import PackageNotFoundError
else:
    from importlib_metadata import PackageNotFoundError

import libcst as cst
import yaml

from hip_cargo.utils.config import get_container_image
from hip_cargo.utils.introspector import extract_input_libcst, format_info_fields, parse_decorator_libcst
```

with:

```python
"""Core logic for generating Stimela cab definitions from Python modules."""

from pathlib import Path

import libcst as cst
import yaml

from hip_cargo.utils.config import get_container_image
from hip_cargo.utils.introspector import extract_input_libcst, format_info_fields, parse_decorator_libcst
```

- [ ] **Step 3: Simplify the except clause in `generate_cabs()`**

In `src/hip_cargo/core/generate_cabs.py`, replace the except clause at line 63:

```python
        except (ValueError, IndexError, PackageNotFoundError):
            pass
```

with:

```python
        except (ValueError, IndexError):
            pass
```

`get_container_image()` now returns `None` instead of raising, so `PackageNotFoundError` is no longer possible.

- [ ] **Step 4: Update the docstring**

In `src/hip_cargo/core/generate_cabs.py`, in the `generate_cabs` docstring (around line 29), replace:

```
            If None, resolved from [project.entry-points."hip.cargo"] in installed package metadata.
```

with:

```
            If None, resolved from the package's _container_image module.
```

- [ ] **Step 5: Run the full test suite**

Run: `cd /home/bester/software/hip-cargo && python -m pytest tests/ -v`

Expected: All tests pass. The integration test `test_generate_cabs_resolves_image_from_metadata` should still pass because `get_container_image("hip-cargo")` now reads from `_container_image.py`.

- [ ] **Step 6: Sync and lint**

Run: `cd /home/bester/software/hip-cargo && uv sync && uv run ruff format . && uv run ruff check . --fix`

- [ ] **Step 7: Commit**

```bash
cd /home/bester/software/hip-cargo
git add pyproject.toml uv.lock src/hip_cargo/core/generate_cabs.py
git commit -m "fix: remove spec-violating entry point and importlib_metadata dependency

The [project.entry-points.\"hip.cargo\"] section stored a container image
URL which is not a valid Python object reference per the entry-points spec.
This caused importlib_metadata to crash when iterating entry points,
breaking dask/jupyter/pytest plugin discovery."
```

---

### Task 3: Update container tag regex tests

**Files:**
- Modify: `tests/test_container_tag_regex.py`

- [ ] **Step 1: Rewrite the test file**

Replace the entire contents of `tests/test_container_tag_regex.py`:

```python
"""Tests for the container image tag regex used in update-cabs workflow and tbump.

The regex rewrites the tag portion of the CONTAINER_IMAGE constant in
_container_image.py. It must handle registries with ports (e.g.
localhost:5000/org/img:tag) by matching the *last* colon before the closing
quote, not the first.
"""

import re

import pytest

# This is the regex used in .github/workflows/update-cabs.yml and tbump.toml
CONTAINER_TAG_REGEX = r'(CONTAINER_IMAGE\s*=\s*".*:)[^"]+'


class TestContainerTagRegex:
    """Test the regex pattern that rewrites container image tags."""

    @pytest.mark.unit
    def test_standard_ghcr_url(self):
        line = 'CONTAINER_IMAGE = "ghcr.io/user/repo:feature-branch"'
        result = re.sub(CONTAINER_TAG_REGEX, r"\g<1>latest", line)
        assert result == 'CONTAINER_IMAGE = "ghcr.io/user/repo:latest"'

    @pytest.mark.unit
    def test_registry_with_port(self):
        """Registries like localhost:5000 must not be truncated."""
        line = 'CONTAINER_IMAGE = "localhost:5000/org/img:feature-branch"'
        result = re.sub(CONTAINER_TAG_REGEX, r"\g<1>latest", line)
        assert result == 'CONTAINER_IMAGE = "localhost:5000/org/img:latest"'

    @pytest.mark.unit
    def test_registry_with_port_and_nested_path(self):
        line = 'CONTAINER_IMAGE = "registry.example.com:8080/team/project/img:v1.2.3"'
        result = re.sub(CONTAINER_TAG_REGEX, r"\g<1>0.2.0", line)
        assert result == 'CONTAINER_IMAGE = "registry.example.com:8080/team/project/img:0.2.0"'

    @pytest.mark.unit
    def test_latest_to_semver(self):
        line = 'CONTAINER_IMAGE = "ghcr.io/user/repo:latest"'
        result = re.sub(CONTAINER_TAG_REGEX, r"\g<1>0.1.8", line)
        assert result == 'CONTAINER_IMAGE = "ghcr.io/user/repo:0.1.8"'

    @pytest.mark.unit
    def test_semver_to_latest(self):
        line = 'CONTAINER_IMAGE = "ghcr.io/user/repo:0.1.8"'
        result = re.sub(CONTAINER_TAG_REGEX, r"\g<1>latest", line)
        assert result == 'CONTAINER_IMAGE = "ghcr.io/user/repo:latest"'

    @pytest.mark.unit
    def test_branch_name_with_slashes(self):
        line = 'CONTAINER_IMAGE = "ghcr.io/user/repo:fix/my-bug"'
        result = re.sub(CONTAINER_TAG_REGEX, r"\g<1>latest", line)
        assert result == 'CONTAINER_IMAGE = "ghcr.io/user/repo:latest"'

    @pytest.mark.unit
    def test_preserves_surrounding_content(self):
        """Regex should only affect the CONTAINER_IMAGE line, not surrounding text."""
        py_file = (
            '"""Container image for my-pkg."""\n'
            'CONTAINER_IMAGE = "ghcr.io/user/repo:dev"\n'
        )
        result = re.sub(CONTAINER_TAG_REGEX, r"\g<1>latest", py_file)
        assert 'CONTAINER_IMAGE = "ghcr.io/user/repo:latest"' in result
        assert '"""Container image for my-pkg."""' in result

    @pytest.mark.unit
    def test_whitespace_around_equals(self):
        """Regex handles optional whitespace around = sign."""
        line = 'CONTAINER_IMAGE  =  "ghcr.io/user/repo:old-tag"'
        result = re.sub(CONTAINER_TAG_REGEX, r"\g<1>latest", line)
        assert result == 'CONTAINER_IMAGE  =  "ghcr.io/user/repo:latest"'

    @pytest.mark.unit
    def test_no_match_without_colon_in_url(self):
        """URL without a tag colon should not be matched."""
        line = 'CONTAINER_IMAGE = "ghcr.io/user/repo"'
        result = re.sub(CONTAINER_TAG_REGEX, r"\g<1>latest", line)
        # No colon in the image ref means no match — line unchanged
        assert result == line
```

- [ ] **Step 2: Run tests**

Run: `cd /home/bester/software/hip-cargo && python -m pytest tests/test_container_tag_regex.py -v`

Expected: All 9 tests PASS.

- [ ] **Step 3: Commit**

```bash
cd /home/bester/software/hip-cargo
git add tests/test_container_tag_regex.py
git commit -m "test: update container tag regex tests for _container_image.py syntax"
```

---

### Task 4: Update `tbump.toml` (hip-cargo's own)

**Files:**
- Modify: `tbump.toml`

- [ ] **Step 1: Update the "Update container image tag" before_commit hook**

In `tbump.toml`, replace lines 31-32:

```toml
[[before_commit]]
name = "Update container image tag to release version"
cmd = "python -c \"import re; p = 'pyproject.toml'; t = open(p).read(); t = re.sub(r'(container-image\\s*=\\s*\\\".*:)[^\\\"]+', r'\\g<1>{new_version}', t); open(p, 'w').write(t)\""
```

with:

```toml
[[before_commit]]
name = "Update container image tag to release version"
cmd = "python -c \"import re; p = 'src/hip_cargo/_container_image.py'; t = open(p).read(); t = re.sub(r'(CONTAINER_IMAGE\\s*=\\s*\\\".*:)[^\\\"]+', r'\\g<1>{new_version}', t); open(p, 'w').write(t)\""
```

- [ ] **Step 2: Remove the `uv sync` step between tag update and cab regeneration**

Delete lines 34-36 (the "Sync environment to refresh package metadata" block):

```toml
[[before_commit]]
name = "Sync environment to refresh package metadata"
cmd = "uv sync"
```

This step was needed to refresh installed entry-point metadata. With `_container_image.py`, editable installs read the source file directly.

- [ ] **Step 3: Update the "Stage pyproject.toml" hook**

Replace:

```toml
[[before_commit]]
name = "Stage pyproject.toml with updated container image tag"
cmd = "git add pyproject.toml"
```

with:

```toml
[[before_commit]]
name = "Stage _container_image.py with updated container image tag"
cmd = "git add src/hip_cargo/_container_image.py"
```

- [ ] **Step 4: Replace the `[[file]]` entry for container-image**

The current `tbump.toml` has no explicit `[[file]]` entry for the container-image line (it was handled by the `before_commit` regex hook). Verify there is no `[[file]]` entry matching `container-image` at the end of the file. If one exists, replace it with:

```toml
[[file]]
src = "src/hip_cargo/_container_image.py"
search = 'CONTAINER_IMAGE = "ghcr.io/landmanbester/hip-cargo:{current_version}"'
```

Note: Since the `before_commit` hook already handles the regex replacement, a `[[file]]` entry is technically redundant. However, checking the current file shows no such entry exists for hip-cargo's own `tbump.toml` (only for the template). No action needed here.

- [ ] **Step 5: Commit**

```bash
cd /home/bester/software/hip-cargo
git add tbump.toml
git commit -m "ci: retarget tbump container tag hooks to _container_image.py"
```

---

### Task 5: Update `.github/workflows/update-cabs.yml`

**Files:**
- Modify: `.github/workflows/update-cabs.yml`

- [ ] **Step 1: Update the regex step**

Replace the "Update container image tag to latest in pyproject.toml" step (lines 51-59):

```yaml
      - name: Update container image tag to latest in pyproject.toml
        run: |
          python -c "
          import re
          p = 'pyproject.toml'
          t = open(p).read()
          t = re.sub(r'(container-image\s*=\s*\".*:)[^\"]+', r'\g<1>latest', t)
          open(p, 'w').write(t)
          "
```

with:

```yaml
      - name: Update container image tag to latest
        run: |
          python -c "
          import re
          p = 'src/hip_cargo/_container_image.py'
          t = open(p).read()
          t = re.sub(r'(CONTAINER_IMAGE\s*=\s*\".*:)[^\"]+', r'\g<1>latest', t)
          open(p, 'w').write(t)
          "
```

- [ ] **Step 2: Remove the "Sync environment" step**

Delete the step (lines 61-62):

```yaml
      - name: Sync environment to refresh package metadata
        run: uv sync
```

- [ ] **Step 3: Update the "Check for changes" step**

Replace the diff check (around line 73):

```yaml
          if git diff --quiet src/hip_cargo/cabs/*.yml pyproject.toml uv.lock; then
```

with:

```yaml
          if git diff --quiet src/hip_cargo/cabs/*.yml src/hip_cargo/_container_image.py; then
```

- [ ] **Step 4: Update the "Commit and push" step**

Replace the `git add` line (around line 84):

```yaml
          git add src/hip_cargo/cabs/*.yml pyproject.toml uv.lock
```

with:

```yaml
          git add src/hip_cargo/cabs/*.yml src/hip_cargo/_container_image.py
```

- [ ] **Step 5: Commit**

```bash
cd /home/bester/software/hip-cargo
git add .github/workflows/update-cabs.yml
git commit -m "ci: retarget update-cabs workflow to _container_image.py"
```

---

### Task 6: Update templates for scaffolded projects

**Files:**
- Modify: `src/hip_cargo/templates/pyproject.toml`
- Modify: `src/hip_cargo/templates/tbump.toml`
- Modify: `src/hip_cargo/templates/workflows/update-cabs.yml`
- Modify: `src/hip_cargo/templates/onboard_core.py`
- Modify: `src/hip_cargo/core/init.py`

- [ ] **Step 1: Update template `pyproject.toml`**

In `src/hip_cargo/templates/pyproject.toml`, remove the `importlib_metadata` dependency line (line 19):

```
    "importlib_metadata>=9.0.0; python_version < '3.11'",
```

Remove the entry-points section (lines 28-29):

```toml
[project.entry-points."hip.cargo"]
container-image = "ghcr.io/<GITHUB_USER>/<PROJECT_NAME>:latest"
```

- [ ] **Step 2: Update template `tbump.toml`**

In `src/hip_cargo/templates/tbump.toml`, replace the "Update container image tag" hook (lines 28-29):

```toml
[[before_commit]]
name = "Update container image tag to release version"
cmd = "python -c \"import re; p = 'pyproject.toml'; t = open(p).read(); t = re.sub(r'(container-image\\s*=\\s*\\\".*:)[^\\\"]+', r'\\g<1>{new_version}', t); open(p, 'w').write(t)\""
```

with:

```toml
[[before_commit]]
name = "Update container image tag to release version"
cmd = "python -c \"import re; p = 'src/<PACKAGE_NAME>/_container_image.py'; t = open(p).read(); t = re.sub(r'(CONTAINER_IMAGE\\s*=\\s*\\\".*:)[^\\\"]+', r'\\g<1>{new_version}', t); open(p, 'w').write(t)\""
```

Replace the `[[file]]` entry for container-image (lines 66-68):

```toml
[[file]]
src = "pyproject.toml"
search = 'container-image = "ghcr.io/<GITHUB_USER>/<PROJECT_NAME>:{current_version}"'
```

with:

```toml
[[file]]
src = "src/<PACKAGE_NAME>/_container_image.py"
search = 'CONTAINER_IMAGE = "ghcr.io/<GITHUB_USER>/<PROJECT_NAME>:{current_version}"'
```

Also find and remove the "Sync environment to refresh package metadata" `[[before_commit]]` block if present (check for a `uv sync` hook between the tag update and cab regeneration).

Update the "Stage pyproject.toml with updated container image tag" hook:

```toml
[[before_commit]]
name = "Stage pyproject.toml with updated container image tag"
cmd = "git add pyproject.toml"
```

to:

```toml
[[before_commit]]
name = "Stage _container_image.py with updated container image tag"
cmd = "git add src/<PACKAGE_NAME>/_container_image.py"
```

- [ ] **Step 3: Update template `update-cabs.yml`**

In `src/hip_cargo/templates/workflows/update-cabs.yml`, replace the regex step (lines 50-58):

```yaml
      - name: Reset container image tag to latest
        run: |
          python -c "
          import re
          p = 'pyproject.toml'
          t = open(p).read()
          t = re.sub(r'(container-image\s*=\s*\".*:)[^\"]+', r'\g<1>latest', t)
          open(p, 'w').write(t)
          "
```

with:

```yaml
      - name: Reset container image tag to latest
        run: |
          python -c "
          import re
          p = 'src/<PACKAGE_NAME>/_container_image.py'
          t = open(p).read()
          t = re.sub(r'(CONTAINER_IMAGE\s*=\s*\".*:)[^\"]+', r'\g<1>latest', t)
          open(p, 'w').write(t)
          "
```

Remove the "Sync environment to refresh package metadata" step (lines 60-61):

```yaml
      - name: Sync environment to refresh package metadata
        run: uv sync
```

Update the diff check (line 69):

```yaml
          if git diff --quiet src/<PACKAGE_NAME>/cabs/*.yml pyproject.toml uv.lock; then
```

to:

```yaml
          if git diff --quiet src/<PACKAGE_NAME>/cabs/*.yml src/<PACKAGE_NAME>/_container_image.py; then
```

Update the `git add` (line 80):

```yaml
          git add src/<PACKAGE_NAME>/cabs/*.yml pyproject.toml uv.lock
```

to:

```yaml
          git add src/<PACKAGE_NAME>/cabs/*.yml src/<PACKAGE_NAME>/_container_image.py
```

- [ ] **Step 4: Update template `onboard_core.py`**

In `src/hip_cargo/templates/onboard_core.py`, replace the "Day-to-Day Development: Image Tag Workflow" section (lines 142-173) with:

```python
────────────────────────────────────────────────────────────────────────────────
  Day-to-Day Development: Image Tag Workflow
────────────────────────────────────────────────────────────────────────────────

  The container image is stored in src/<PACKAGE_NAME>/_container_image.py
  as the single source of truth for cab generation and container fallback
  execution. The tag portion must stay in sync with your current context.

  When you create a feature branch:

    1. Edit src/<PACKAGE_NAME>/_container_image.py and change the tag:

         CONTAINER_IMAGE = "ghcr.io/<GITHUB_USER>/<PROJECT_NAME>:my-feature"

    2. Commit and develop as normal — pre-commit hooks will generate cab
       definitions with the correct branch-specific image tag.

  You do NOT need to reset the tag before merging. On merge to <DEFAULT_BRANCH>,
  the update-cabs workflow automatically:

    - Resets the CONTAINER_IMAGE tag to "latest"
    - Regenerates cab definitions
    - Commits _container_image.py and cab YAML files

  During releases, tbump updates the tag to the semantic version
  (e.g. 0.1.0) via its before-commit hooks.

────────────────────────────────────────────────────────────────────────────────
```

Note: This is inside a triple-quoted print string. Preserve the exact indentation and surrounding context.

- [ ] **Step 5: Update `core/init.py` to generate `_container_image.py`**

In `src/hip_cargo/core/init.py`, after the line that writes `cabs/__init__.py` (around line 168, after the `_write_file(src_pkg / "cabs" / "__init__.py", ...)` call), add:

```python
    _write_file(
        src_pkg / "_container_image.py",
        f'CONTAINER_IMAGE = "ghcr.io/{github_user}/{project_name}:latest"\n',
    )
```

- [ ] **Step 6: Lint**

Run: `cd /home/bester/software/hip-cargo && uv run ruff format . && uv run ruff check . --fix`

- [ ] **Step 7: Run the full test suite**

Run: `cd /home/bester/software/hip-cargo && python -m pytest tests/ -v`

Expected: All tests pass.

- [ ] **Step 8: Commit**

```bash
cd /home/bester/software/hip-cargo
git add src/hip_cargo/templates/pyproject.toml \
        src/hip_cargo/templates/tbump.toml \
        src/hip_cargo/templates/workflows/update-cabs.yml \
        src/hip_cargo/templates/onboard_core.py \
        src/hip_cargo/core/init.py
git commit -m "feat(init): update scaffolding templates for _container_image.py

Scaffolded projects now store the container image URL in
_container_image.py instead of a pyproject.toml entry point.
Removes importlib_metadata dependency from generated projects."
```

---

### Task 7: Update CLAUDE.md and clean up documentation

**Files:**
- Modify: `CLAUDE.md`
- Delete: `docs/using_entry_points_for_metadata.md`

- [ ] **Step 1: Update CLAUDE.md**

Apply the following replacements throughout `CLAUDE.md`:

**a)** In the "Project Structure" tree, add `_container_image.py` to the `src/hip_cargo/` section:

```
│   ├── _container_image.py   # Container image URL (single source of truth)
```

**b)** In the dependencies list, remove `importlib_metadata`:

Remove:
```
- Current dependencies: `typer`, `pyyaml`, `libcst`, `ruff`, `typing-extensions`, `tomli` (Python < 3.11 only), `importlib_metadata` (Python < 3.11 only)
```
Replace with:
```
- Current dependencies: `typer`, `pyyaml`, `libcst`, `ruff`, `typing-extensions`, `tomli` (Python < 3.11 only)
```

**c)** In the "Image Resolution" section, replace the entire entry-point explanation with:

```markdown
### Image Resolution

The container image (including tag) is stored as a Python constant in `_container_image.py` within each package:

```python
# src/hip_cargo/_container_image.py
CONTAINER_IMAGE = "ghcr.io/landmanbester/hip-cargo:latest"
```

At runtime, `get_container_image()` in `utils/config.py` dynamically imports this module via `importlib.import_module()` (no CWD dependency). The value is used as-is by both `generate_cabs()` (when no `--image` override is passed) and `run_in_container()` for container fallback.

The tag portion is managed by three mechanisms (see [Image Tag Lifecycle](#image-tag-lifecycle) above):
- Developer edits `_container_image.py` directly on feature branches
- `update-cabs` workflow resets it to `latest` on merge to main
- `tbump` sets it to the semantic version during releases
```

**d)** In the "Image Tag Lifecycle" section, replace the entry-point mechanism with:

```markdown
### Image Tag Lifecycle

The container image is stored in `src/<package>/_container_image.py` as a `CONTAINER_IMAGE` constant:

```python
CONTAINER_IMAGE = "ghcr.io/user/repo:latest"
```

Three mechanisms keep the tag in sync:

1. **Feature branches (manual)**: The developer edits `_container_image.py` to change the tag to the branch name. Since `get_container_image()` imports the module directly, no `uv sync` is needed.
2. **Merge to main (`update-cabs` workflow)**: Resets the tag to `latest` via regex, regenerates cabs, and commits `_container_image.py` and cab YAML files.
3. **Releases (`tbump`)**: Updates the tag to the semantic version (e.g. `0.1.8`) via before-commit hooks in `tbump.toml`.
```

**e)** In the "Current Feature Set" section, replace:

```
- **Runtime image resolution**: Container image (including tag) read from `[project.entry-points."hip.cargo"]` in `pyproject.toml` via installed package metadata — no image metadata in CLI source files
```

with:

```
- **Runtime image resolution**: Container image (including tag) read from `_container_image.py` via dynamic module import — no CWD dependency, no image metadata in CLI source files
```

**f)** Replace any remaining references to `[project.entry-points."hip.cargo"]` with references to `_container_image.py`. Search for `entry-points` and `entry_points` in the file.

**g)** In the pyproject.toml snippet under "Image Resolution" (or similar), remove:

```toml
[project.entry-points."hip.cargo"]
container-image = "ghcr.io/user/repo:latest"
```

**h)** Update the "Image Tag Lifecycle" note about `uv sync`: feature branches no longer need `uv sync` after editing `_container_image.py`.

- [ ] **Step 2: Delete the obsolete doc**

```bash
rm docs/using_entry_points_for_metadata.md
```

- [ ] **Step 3: Commit**

```bash
cd /home/bester/software/hip-cargo
git add CLAUDE.md
git rm docs/using_entry_points_for_metadata.md
git commit -m "docs: update CLAUDE.md for _container_image.py, remove entry-point doc"
```

---

### Task 8: Final verification

**Files:** (none — verification only)

- [ ] **Step 1: Run the full test suite**

Run: `cd /home/bester/software/hip-cargo && python -m pytest tests/ -v`

Expected: All tests pass.

- [ ] **Step 2: Verify no remaining references to entry-point pattern**

Run: `cd /home/bester/software/hip-cargo && grep -r "entry.points.*hip.cargo" --include="*.py" --include="*.toml" --include="*.yml" src/ .github/ pyproject.toml tbump.toml`

Expected: No matches (only docs/plans may still reference it historically).

Run: `cd /home/bester/software/hip-cargo && grep -r "importlib_metadata" --include="*.py" --include="*.toml" src/ pyproject.toml`

Expected: No matches.

- [ ] **Step 3: Verify `get_container_image` still works**

Run: `cd /home/bester/software/hip-cargo && python -c "from hip_cargo.utils.config import get_container_image; print(get_container_image('hip-cargo'))"`

Expected: Prints `ghcr.io/landmanbester/hip-cargo:latest`

- [ ] **Step 4: Verify the regex works on the new file**

Run:
```bash
cd /home/bester/software/hip-cargo && python -c "
import re
p = 'src/hip_cargo/_container_image.py'
t = open(p).read()
t = re.sub(r'(CONTAINER_IMAGE\s*=\s*\".*:)[^\"]+', r'\g<1>0.2.0', t)
print(t)
"
```

Expected: `CONTAINER_IMAGE = "ghcr.io/landmanbester/hip-cargo:0.2.0"`

- [ ] **Step 5: Lint one final time**

Run: `cd /home/bester/software/hip-cargo && uv run ruff format . && uv run ruff check . --fix`

Expected: Clean output.
