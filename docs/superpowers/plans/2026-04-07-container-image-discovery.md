# Container Image Discovery Refactor

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace brittle CWD-walk and git-based image discovery with `[project.urls] Container` as the single source of truth, readable via `importlib.metadata` from anywhere.

**Architecture:** The full container image+tag (e.g. `ghcr.io/user/repo:latest`) is stored in `[project.urls] Container` in pyproject.toml. The tbump hooks update the tag to the release version, and the `update-cabs` GitHub App workflow resets it to `:latest` after merge. At runtime, generated CLI code reads the image via `importlib.metadata.metadata(package_name)` and passes it directly to `run_in_container()`. For `generate-cabs`, the same `importlib.metadata` lookup replaces the old CWD walk + git tag resolution. The functions `get_image_tag()`, `get_project_image()`, and `find_pyproject_toml()` are deleted.

**Tech Stack:** Python 3.10+, `importlib.metadata` (stdlib 3.11+) / `importlib_metadata` (already a dependency for <3.11)

---

## Design Summary

### Before (brittle)

```
generate-cabs:  get_project_image() [CWD walk] + get_image_tag() [git rev-parse] → image
runtime:        run_in_container discovers image via cab_config or CWD walk
```

### After (robust)

```
pyproject.toml: [project.urls] Container = "ghcr.io/user/repo:latest"  ← single source of truth
                ↑ updated by tbump hooks and update-cabs workflow

generate-cabs:  get_container_image(package_name) [importlib.metadata] → image (or --image override)
runtime:        get_container_image(package_name) [importlib.metadata] → image → run_in_container(image=...)
```

### Package name derivation

The cab YAML `command` field has the form `pfb_imaging.core.grid.grid`. The first component (`pfb_imaging`) is the Python import name. The distribution name is derived by replacing underscores with hyphens: `pfb-imaging`. This is the standard Python packaging convention and is what `importlib.metadata.metadata()` expects.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/hip_cargo/utils/config.py` | Rewrite | Keep `get_container_image()`, delete `find_pyproject_toml()`, `get_project_image()`, `get_image_tag()` |
| `src/hip_cargo/utils/runner.py` | Modify | Clean up dead imports (line 10), keep `image` as required param |
| `src/hip_cargo/utils/cab_to_function.py` | Modify | Generate `get_container_image()` call + `image=` arg in fallback body |
| `src/hip_cargo/core/generate_function.py` | Modify | Import and pass package name to body generator |
| `src/hip_cargo/core/generate_cabs.py` | Modify | Replace `get_project_image()` + `get_image_tag()` with `get_container_image()` |
| `src/hip_cargo/cli/generate_cabs.py` | Modify | Update fallback to pass `image=` |
| `src/hip_cargo/cli/generate_function.py` | Modify | Update fallback to pass `image=` |
| `src/hip_cargo/__init__.py` | Modify | Export `get_container_image` |
| `src/hip_cargo/templates/pyproject.toml` | Modify | Add `Container` to `[project.urls]`, remove `[tool.hip-cargo]` section |
| `src/hip_cargo/templates/tbump.toml` | Modify | Add hook to update Container URL tag, add `uv sync` step |
| `src/hip_cargo/templates/workflows/update-cabs.yml` | Modify | Add step to reset Container URL to `:latest` |
| `pyproject.toml` (hip-cargo's own) | Modify | Add `Container` URL, remove `[tool.hip-cargo]` section |
| `tests/test_runner.py` | Modify | Add test for `run_in_container` with image param, remove stale tests |
| `tests/test_config.py` | Create | Test `get_container_image()` |
| `tests/test_roundtrip.py` | Modify | Update roundtrip tests (generated code now includes `get_container_image` call) |
| `tests/test_cli.py` | Modify | Update `test_generate_image_override` |

---

### Task 1: Rewrite `config.py` — `get_container_image()` as sole function

**Files:**
- Modify: `src/hip_cargo/utils/config.py`
- Create: `tests/test_config.py`

The function `get_container_image(package_name)` already exists in `config.py`. We delete `find_pyproject_toml()`, `get_project_image()`, and `get_image_tag()`, and remove the `subprocess` and `Path` imports they required. We keep only `get_container_image()`.

- [ ] **Step 1: Write failing tests for `get_container_image`**

```python
"""Tests for container image resolution from package metadata."""

import pytest

from hip_cargo.utils.config import get_container_image


class TestGetContainerImage:
    """Test get_container_image reads from importlib.metadata."""

    @pytest.mark.unit
    def test_returns_image_for_hip_cargo(self):
        """hip-cargo's own pyproject.toml has a Container URL."""
        image = get_container_image("hip-cargo")
        assert image is not None
        assert image.startswith("ghcr.io/")

    @pytest.mark.unit
    def test_returns_none_for_package_without_container(self):
        """Packages without a Container URL should return None."""
        image = get_container_image("pytest")
        assert image is None

    @pytest.mark.unit
    def test_raises_for_nonexistent_package(self):
        """Non-existent package should raise PackageNotFoundError."""
        from importlib.metadata import PackageNotFoundError

        with pytest.raises(PackageNotFoundError):
            get_container_image("nonexistent-package-xyz-12345")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_config.py -v`
Expected: `test_returns_image_for_hip_cargo` FAILS because hip-cargo's pyproject.toml doesn't have `Container` in `[project.urls]` yet.

- [ ] **Step 3: Add `Container` URL to hip-cargo's own `pyproject.toml`**

In `pyproject.toml`, add the Container line to `[project.urls]` and remove the `[tool.hip-cargo]` section:

Replace:

```toml
[project.urls]
Homepage = "https://github.com/landmanbester/hip-cargo"
Repository = "https://github.com/landmanbester/hip-cargo"
"Bug Tracker" = "https://github.com/landmanbester/hip-cargo/issues"
```

With:

```toml
[project.urls]
Homepage = "https://github.com/landmanbester/hip-cargo"
Repository = "https://github.com/landmanbester/hip-cargo"
"Bug Tracker" = "https://github.com/landmanbester/hip-cargo/issues"
Container = "ghcr.io/landmanbester/hip-cargo:latest"
```

And delete the `[tool.hip-cargo]` section:

```toml
[tool.hip-cargo]
image = "ghcr.io/landmanbester/hip-cargo"
```

- [ ] **Step 4: Run `uv sync` to refresh installed metadata**

Run: `uv sync`
Expected: Completes successfully, metadata now reflects the new Container URL.

- [ ] **Step 5: Rewrite `config.py` — delete old functions, keep only `get_container_image`**

Replace the entire contents of `src/hip_cargo/utils/config.py` with:

```python
"""Read container image from installed package metadata."""

import sys

if sys.version_info >= (3, 11):
    from importlib.metadata import metadata
else:
    from importlib_metadata import metadata


def get_container_image(package_name: str) -> str | None:
    """Return the container image URL registered in a package's project metadata.

    Looks up the 'Container' entry under [project.urls] in the package metadata.
    This reads from the installed package metadata via importlib.metadata, so it
    works from any directory — no CWD dependency.

    Args:
        package_name: The distribution name of the package (e.g. 'pfb-imaging').

    Returns:
        The full container image string (including tag), or None if not configured.

    Raises:
        PackageNotFoundError: If the package is not installed.
    """
    meta = metadata(package_name)
    for entry in meta.get_all("Project-URL") or []:
        label, _, url = entry.partition(", ")
        if label.strip().lower() == "container":
            return url.strip()
    return None
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/hip_cargo/utils/config.py tests/test_config.py pyproject.toml
git commit -m "refactor: replace CWD-walk image discovery with importlib.metadata

Store full container image+tag in [project.urls] Container.
Delete get_project_image(), find_pyproject_toml(), get_image_tag().
get_container_image() reads from installed package metadata."
```

---

### Task 2: Clean up `runner.py` — remove dead imports

**Files:**
- Modify: `src/hip_cargo/utils/runner.py:10`
- Test: `tests/test_runner.py`

- [ ] **Step 1: Write a test for `run_in_container` with explicit image parameter**

Add to `tests/test_runner.py`:

```python
class TestRunInContainer:
    """Test run_in_container dispatches correctly with explicit image."""

    @pytest.mark.unit
    def test_run_in_container_uses_provided_image(self, tmp_path):
        """run_in_container should use the image passed directly."""
        from hip_cargo.utils.decorators import stimela_cab

        @stimela_cab(name="test-cmd", info="test")
        def func(input_file: Annotated[File, typer.Option(..., parser=Path, help="input")]):
            pass

        input_file = tmp_path / "data.ms"
        input_file.touch()

        with (
            patch("hip_cargo.utils.runner._detect_runtime", return_value="docker"),
            patch("hip_cargo.utils.runner.subprocess.run") as mock_run,
            patch("hip_cargo.utils.runner.sys") as mock_sys,
        ):
            mock_sys.argv = ["/usr/bin/test-cmd", "--input-file", str(input_file)]

            from hip_cargo.utils.runner import run_in_container

            run_in_container(
                func,
                {"input_file": input_file},
                image="ghcr.io/test/pkg:v1.0",
                backend="docker",
            )

        # Verify the image was used in the container command
        call_args = mock_run.call_args[0][0]
        assert "ghcr.io/test/pkg:v1.0" in call_args
```

- [ ] **Step 2: Run to verify it passes (image param already exists)**

Run: `python -m pytest tests/test_runner.py::TestRunInContainer -v`
Expected: PASS (the `image` parameter already exists on `run_in_container`)

- [ ] **Step 3: Remove dead imports from `runner.py`**

In `src/hip_cargo/utils/runner.py`, replace line 10:

```python
from hip_cargo.utils.config import get_container_image, get_image_tag
```

With nothing — delete the line entirely. The function no longer needs any imports from config.

- [ ] **Step 4: Fix the docstring (line 28 says `image_base` instead of `image`)**

In `src/hip_cargo/utils/runner.py`, replace:

```python
        image_base: Base name of the container image to use.
```

With:

```python
        image: Full container image reference (e.g. "ghcr.io/user/repo:tag").
```

- [ ] **Step 5: Run all runner tests**

Run: `python -m pytest tests/test_runner.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/hip_cargo/utils/runner.py tests/test_runner.py
git commit -m "fix: clean up dead imports and docstring in runner.py"
```

---

### Task 3: Update `generate_cabs` to use `get_container_image()`

**Files:**
- Modify: `src/hip_cargo/core/generate_cabs.py:1-12` (imports) and `48-52` (image resolution)
- Test: `tests/test_cli.py`

`generate_cabs()` currently calls `get_project_image()` + `get_image_tag()`. We replace this with `get_container_image()`. The package name is derived from the module path: the first component after `src/` in the module path is the Python import name, which maps to the distribution name via underscore→hyphen.

- [ ] **Step 1: Update imports in `generate_cabs.py`**

In `src/hip_cargo/core/generate_cabs.py`, replace:

```python
from hip_cargo.utils.config import get_project_image
from hip_cargo.utils.introspector import extract_input_libcst, format_info_fields, parse_decorator_libcst
```

With:

```python
from hip_cargo.utils.config import get_container_image
from hip_cargo.utils.introspector import extract_input_libcst, format_info_fields, parse_decorator_libcst
```

And delete the line:

```python
from hip_cargo.utils.config import get_image_tag
```

- [ ] **Step 2: Replace the image resolution block**

In `src/hip_cargo/core/generate_cabs.py`, replace:

```python
    # Resolve image from pyproject.toml when not explicitly provided
    if image is None:
        image_base = get_project_image()
        if image_base:
            image = f"{image_base}:{get_image_tag()}"
```

With:

```python
    # Resolve image from installed package metadata when not explicitly provided.
    # Derive distribution name from module path: src/<package>/cli/module.py
    # The first component after src/ is the Python import name.
    if image is None:
        first_mod = modlist[0]
        parts = first_mod.parts
        try:
            src_idx = parts.index("src")
            import_name = parts[src_idx + 1]
            dist_name = import_name.replace("_", "-")
            image = get_container_image(dist_name)
        except (ValueError, IndexError):
            pass
```

- [ ] **Step 3: Run the existing CLI tests**

Run: `python -m pytest tests/test_cli.py -v`
Expected: ALL PASS. The `test_generate_image_override` test uses `--image` explicitly so is unaffected. The other tests generate cabs for hip-cargo's own CLI modules, so `get_container_image("hip-cargo")` will return the Container URL we set in Task 1.

- [ ] **Step 4: Run the roundtrip tests to verify cabs still generate correctly**

Run: `python -m pytest tests/test_roundtrip.py -v`
Expected: FAIL — the roundtrip tests compare generated CLI code line-for-line with the originals. The originals (`cli/generate_cabs.py`, `cli/generate_function.py`) still call `run_in_container` without `image=`. We'll fix this in Task 5.

- [ ] **Step 5: Commit (partial — roundtrip tests will be fixed in Task 5)**

```bash
git add src/hip_cargo/core/generate_cabs.py
git commit -m "refactor: use get_container_image() in generate_cabs

Replace get_project_image() + get_image_tag() with importlib.metadata
lookup. Derive distribution name from module path."
```

---

### Task 4: Generate `get_container_image()` call in function body

**Files:**
- Modify: `src/hip_cargo/utils/cab_to_function.py:483-581` (the `generate_function_body` function)
- Modify: `src/hip_cargo/core/generate_function.py:111` (`uses_literal` check) and `149-154` (imports block)

This is the core change: the generated fallback code must call `get_container_image(dist_name)` and pass `image=` to `run_in_container()`.

- [ ] **Step 1: Write a test for the generated function body**

Add to `tests/test_list_types.py` (where `generate_function_body` tests live):

```python
def test_generate_function_body_container_fallback_image():
    """Generated body should resolve image via get_container_image and pass to run_in_container."""
    cab_def = {
        "_name": "my-cmd",
        "command": "my_pkg.core.my_cmd.my_cmd",
        "image": "ghcr.io/user/my-pkg:latest",
        "inputs": {},
        "outputs": {},
    }
    body_lines = generate_function_body(cab_def, {}, {})
    body = "\n".join(body_lines)

    # Should derive distribution name from command
    assert '"my-pkg"' in body
    # Should call get_container_image
    assert "get_container_image" in body
    # Should pass image= to run_in_container
    assert "image=" in body
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_list_types.py::test_generate_function_body_container_fallback_image -v`
Expected: FAIL — body doesn't contain `get_container_image` yet

- [ ] **Step 3: Modify `generate_function_body` to generate image resolution code**

In `src/hip_cargo/utils/cab_to_function.py`, replace the entire container fallback block inside `generate_function_body()`. Replace from line 556 to line 579:

```python
    if has_image:
        lines.append(f"{indent}return")
        lines.append("        except ImportError:")
        lines.append("            if backend == 'native':")
        lines.append("                raise")
        lines.append("")
        lines.append("    # Fall back to container execution")
        lines.append("    from hip_cargo.utils.runner import run_in_container  # noqa: E402")
        lines.append("")

        # Build the params dict for run_in_container (excludes backend)
        lines.append("    run_in_container(")
        lines.append(f"        {func_name},")
        lines.append("        dict(")
        for param_name in inputs:
            py_name = param_name.replace("-", "_")
            lines.append(f"            {py_name}={py_name},")
        for output_name in outputs:
            py_name = output_name.replace("-", "_")
            lines.append(f"            {py_name}={py_name},")
        lines.append("        ),")
        lines.append("        backend=backend,")
        lines.append("        always_pull_images=always_pull_images,")
        lines.append("    )")
```

With:

```python
    if has_image:
        lines.append(f"{indent}return")
        lines.append("        except ImportError:")
        lines.append("            if backend == 'native':")
        lines.append("                raise")
        lines.append("")
        lines.append("    # Resolve container image from installed package metadata")
        lines.append("    from hip_cargo.utils.config import get_container_image  # noqa: E402")
        lines.append("    from hip_cargo.utils.runner import run_in_container  # noqa: E402")
        lines.append("")

        # Derive distribution name from command: "pfb_imaging.core.grid.grid" → "pfb-imaging"
        command = cab_def.get("command", "")
        import_name = command.split(".")[0] if command else ""
        dist_name = import_name.replace("_", "-")

        lines.append(f'    image = get_container_image("{dist_name}")')
        lines.append("    if image is None:")
        lines.append(f'        raise RuntimeError("No container image configured for {dist_name}. ')
        lines.append(f'Set Container in [project.urls] in {dist_name}\'s pyproject.toml.")')
        lines.append("")

        # Build the params dict for run_in_container (excludes backend)
        lines.append("    run_in_container(")
        lines.append(f"        {func_name},")
        lines.append("        dict(")
        for param_name in inputs:
            py_name = param_name.replace("-", "_")
            lines.append(f"            {py_name}={py_name},")
        for output_name in outputs:
            py_name = output_name.replace("-", "_")
            lines.append(f"            {py_name}={py_name},")
        lines.append("        ),")
        lines.append("        image=image,")
        lines.append("        backend=backend,")
        lines.append("        always_pull_images=always_pull_images,")
        lines.append("    )")
```

- [ ] **Step 4: Update the imports block in `generate_function.py`**

In `src/hip_cargo/core/generate_function.py`, the `hip_cargo_imports` list (line 152-154) builds the `from hip_cargo import ...` line. We need to add `get_container_image` when the cab has an image.

Replace:

```python
    # Build a single import line from hip_cargo with decorators + list types
    hip_cargo_imports = sorted(list_types_used) + sorted(LIST_TYPE_PARSERS[t] for t in list_types_used)
    hip_cargo_imports.extend(["stimela_cab", "stimela_output"])
    lines.append(f"from hip_cargo import {', '.join(hip_cargo_imports)}")
```

With:

```python
    # Build a single import line from hip_cargo with decorators + list types
    hip_cargo_imports = sorted(list_types_used) + sorted(LIST_TYPE_PARSERS[t] for t in list_types_used)
    if cab_def.get("image"):
        hip_cargo_imports.append("get_container_image")
    hip_cargo_imports.extend(["stimela_cab", "stimela_output"])
    lines.append(f"from hip_cargo import {', '.join(sorted(hip_cargo_imports))}")
```

Note: we sort the final list to keep import order deterministic.

- [ ] **Step 5: Export `get_container_image` from `__init__.py`**

In `src/hip_cargo/__init__.py`, add the import and export:

Replace:

```python
from hip_cargo.utils.decorators import stimela_cab, stimela_output
```

With:

```python
from hip_cargo.utils.config import get_container_image
from hip_cargo.utils.decorators import stimela_cab, stimela_output
```

And add `"get_container_image"` to the `__all__` list.

- [ ] **Step 6: Run the test**

Run: `python -m pytest tests/test_list_types.py::test_generate_function_body_container_fallback_image -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/hip_cargo/utils/cab_to_function.py src/hip_cargo/core/generate_function.py src/hip_cargo/__init__.py
git commit -m "feat: generate get_container_image() call in container fallback

Generated CLI functions now resolve the image from installed package
metadata via get_container_image() and pass it to run_in_container()."
```

---

### Task 5: Update hip-cargo's own CLI files to match generated output

**Files:**
- Modify: `src/hip_cargo/cli/generate_cabs.py`
- Modify: `src/hip_cargo/cli/generate_function.py`
- Test: `tests/test_roundtrip.py`

The roundtrip tests compare hip-cargo's own CLI files line-for-line with the output of `generate_function`. Since we changed the generated fallback code in Task 4, we must update hip-cargo's own CLI files to match.

- [ ] **Step 1: Regenerate hip-cargo's own CLI files from its cab definitions**

Rather than manually editing, regenerate the files to ensure exact match:

Run:
```bash
uv run hip-cargo generate-function --cab-file src/hip_cargo/cabs/generate_cabs.yml --output-file src/hip_cargo/cli/generate_cabs.py --config-file pyproject.toml
uv run hip-cargo generate-function --cab-file src/hip_cargo/cabs/generate_function.yml --output-file src/hip_cargo/cli/generate_function.py --config-file pyproject.toml
```

- [ ] **Step 2: Verify the regenerated files look correct**

Read both files and verify:
- They import `get_container_image` from `hip_cargo`
- The fallback block calls `get_container_image("hip-cargo")`
- The `run_in_container` call has `image=image`

- [ ] **Step 3: Run the roundtrip tests**

Run: `python -m pytest tests/test_roundtrip.py -v`
Expected: ALL PASS

- [ ] **Step 4: Run the full test suite**

Run: `python -m pytest tests/ -v`
Expected: ALL PASS (except pfb-imaging roundtrip which requires pfb-imaging installed)

- [ ] **Step 5: Commit**

```bash
git add src/hip_cargo/cli/generate_cabs.py src/hip_cargo/cli/generate_function.py
git commit -m "chore: regenerate hip-cargo CLI files with new fallback pattern"
```

---

### Task 6: Update templates for scaffolded projects

**Files:**
- Modify: `src/hip_cargo/templates/pyproject.toml`
- Modify: `src/hip_cargo/templates/tbump.toml`
- Modify: `src/hip_cargo/templates/workflows/update-cabs.yml`
- Modify: `src/hip_cargo/core/init.py` (placeholder handling)
- Test: `tests/test_init.py`

#### 6a: Update pyproject.toml template

- [ ] **Step 1: Add Container URL and remove `[tool.hip-cargo]`**

In `src/hip_cargo/templates/pyproject.toml`, replace:

```toml
[project.urls]
Homepage = "<GITHUB_URL>"
Repository = "<GITHUB_URL>"
"Bug Tracker" = "<GITHUB_URL>/issues"
```

With:

```toml
[project.urls]
Homepage = "<GITHUB_URL>"
Repository = "<GITHUB_URL>"
"Bug Tracker" = "<GITHUB_URL>/issues"
Container = "ghcr.io/<GITHUB_USER>/<PROJECT_NAME>:latest"
```

And delete the `[tool.hip-cargo]` section (lines 36-37):

```toml
[tool.hip-cargo]
image = "ghcr.io/<GITHUB_USER>/<PROJECT_NAME>"
```

#### 6b: Update tbump template

- [ ] **Step 2: Add hooks to update Container URL during tbump release**

In `src/hip_cargo/templates/tbump.toml`, add two new `before_commit` hooks. Add after the existing "Write release version sentinel" hook:

```toml
[[before_commit]]
name = "Update Container image tag to release version"
cmd = "python -c \"import re; p = 'pyproject.toml'; t = open(p).read(); t = re.sub(r'(Container\\s*=\\s*\\\"[^:]+:)[^\\\"]+', r'\\g<1>{new_version}', t); open(p, 'w').write(t)\""
```

And add a `uv sync` step before the "Regenerate cab definitions" hook:

```toml
[[before_commit]]
name = "Sync environment to refresh package metadata"
cmd = "uv sync"
```

Also remove the "Write release version sentinel" hook and the "Remove version sentinel" before_push hook entirely, since we no longer use the `.tbump_version` sentinel file.

The full `before_commit` section should become:

```toml
[[before_commit]]
name = "Update Container image tag to release version"
cmd = "python -c \"import re; p = 'pyproject.toml'; t = open(p).read(); t = re.sub(r'(Container\\s*=\\s*\\\"[^:]+:)[^\\\"]+', r'\\g<1>{new_version}', t); open(p, 'w').write(t)\""

[[before_commit]]
name = "Sync environment to refresh package metadata"
cmd = "uv sync"

[[before_commit]]
name = "Regenerate cab definitions with release version"
cmd = "<CLI_COMMAND> generate-cabs --module 'src/<PACKAGE_NAME>/cli/*.py' --output-dir src/<PACKAGE_NAME>/cabs"

[[before_commit]]
name = "Stage updated cab definitions"
cmd = "git add src/<PACKAGE_NAME>/cabs/*.yml"

[[before_commit]]
name = "Stage pyproject.toml with updated Container tag"
cmd = "git add pyproject.toml"

[[before_commit]]
name = "Update uv.lock"
cmd = "uv lock"

[[before_commit]]
name = "Stage uv.lock"
cmd = "git add uv.lock"
```

And the `before_push` section should be empty (remove the sentinel cleanup hook):

```toml
# before_push hooks run after the commit succeeds (no cleanup needed)
```

- [ ] **Step 3: Add `[file]` entry for pyproject.toml Container URL**

In `src/hip_cargo/templates/tbump.toml`, add a tbump `[[file]]` entry so tbump also updates the Container tag via its own substitution mechanism. Add after the existing `[[file]]` entries:

```toml
[[file]]
src = "pyproject.toml"
search = 'Container = "ghcr.io/<GITHUB_USER>/<PROJECT_NAME>:{current_version}"'
```

Note: this handles the case where the Container URL already has a version tag (after a previous release). For first release from `:latest`, the `before_commit` hook regex handles it.

#### 6c: Update the update-cabs workflow template

- [ ] **Step 4: Add step to reset Container URL to `:latest`**

In `src/hip_cargo/templates/workflows/update-cabs.yml`, add a step before "Regenerate cab definitions with latest tag". Insert after "Install package":

```yaml
      - name: Reset Container image tag to latest
        run: |
          python -c "
          import re
          p = 'pyproject.toml'
          t = open(p).read()
          t = re.sub(r'(Container\s*=\s*\"[^:]+:)[^\"]+', r'\g<1>latest', t)
          open(p, 'w').write(t)
          "

      - name: Sync environment to refresh package metadata
        run: uv sync
```

And update the "Check for changes" step to also check pyproject.toml:

Replace:

```yaml
      - name: Check for changes
        id: check_changes
        run: |
          if git diff --quiet src/<PACKAGE_NAME>/cabs/*.yml; then
            echo "changed=false" >> $GITHUB_OUTPUT
          else
            echo "changed=true" >> $GITHUB_OUTPUT
          fi
```

With:

```yaml
      - name: Check for changes
        id: check_changes
        run: |
          if git diff --quiet src/<PACKAGE_NAME>/cabs/*.yml pyproject.toml; then
            echo "changed=false" >> $GITHUB_OUTPUT
          else
            echo "changed=true" >> $GITHUB_OUTPUT
          fi
```

And update the commit step to also stage pyproject.toml:

Replace:

```yaml
          git add src/<PACKAGE_NAME>/cabs/*.yml
```

With:

```yaml
          git add src/<PACKAGE_NAME>/cabs/*.yml pyproject.toml
```

#### 6d: Update init.py placeholder handling

- [ ] **Step 5: Check if `core/init.py` needs a new placeholder**

The template already uses `<GITHUB_USER>` and `<PROJECT_NAME>` in the Container URL, which are existing placeholders handled by `core/init.py`. No new placeholder needed.

Verify by reading `core/init.py` to confirm `<GITHUB_USER>` and `<PROJECT_NAME>` are in the replacement map.

- [ ] **Step 6: Run init tests**

Run: `python -m pytest tests/test_init.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/hip_cargo/templates/pyproject.toml src/hip_cargo/templates/tbump.toml src/hip_cargo/templates/workflows/update-cabs.yml
git commit -m "feat: update templates for Container URL image discovery

- pyproject.toml template: add Container URL, remove [tool.hip-cargo]
- tbump template: update Container tag on release, add uv sync step,
  remove .tbump_version sentinel logic
- update-cabs workflow: reset Container tag to :latest after merge"
```

---

### Task 7: Update hip-cargo's own tbump.toml

**Files:**
- Modify: `tbump.toml` (hip-cargo's own, at project root)

Hip-cargo's own `tbump.toml` needs the same changes as the template.

- [ ] **Step 1: Read hip-cargo's own tbump.toml**

Read `tbump.toml` to see the current hooks.

- [ ] **Step 2: Apply the same changes as Task 6b/6c**

Update the `before_commit` hooks to:
1. Replace "Write release version sentinel" with "Update Container image tag to release version" (same regex command but with `hip-cargo` specifics resolved)
2. Add "Sync environment to refresh package metadata" (`uv sync`) before `generate-cabs`
3. Add "Stage pyproject.toml with updated Container tag" (`git add pyproject.toml`)
4. Remove the "Remove version sentinel" `before_push` hook

Add the `[[file]]` entry for the Container URL in pyproject.toml.

- [ ] **Step 3: Commit**

```bash
git add tbump.toml
git commit -m "chore: update hip-cargo tbump.toml for Container URL workflow"
```

---

### Task 8: Final verification and cleanup

**Files:**
- All modified files
- Test: entire test suite

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 2: Run ruff**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: No issues

- [ ] **Step 3: Verify no remaining references to deleted functions**

Run:
```bash
grep -r "get_project_image\|find_pyproject_toml\|get_image_tag\|tbump_version" src/ tests/ --include="*.py"
```
Expected: No matches (except possibly in test files that test the old behavior, which should have been removed)

- [ ] **Step 4: Verify no remaining references to `[tool.hip-cargo]`**

Run:
```bash
grep -r "tool.hip-cargo\|tool\.hip.cargo" src/ tests/ pyproject.toml --include="*.py" --include="*.toml"
```
Expected: No matches in source or config files (may still appear in docs/CLAUDE.md which should be updated separately)

- [ ] **Step 5: Commit any final fixups**

```bash
git add -A
git commit -m "chore: final cleanup for container image discovery refactor"
```
