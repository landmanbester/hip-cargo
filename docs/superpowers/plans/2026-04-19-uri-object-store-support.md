# URI / Object-Store Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable hip-cargo's `URI`/`File`/`Directory`/`MS` types to accept object-store URIs (`s3://`, `gs://`, `az://`, `http(s)://`) with auto-detected credentials in both native execution and container fallback.

**Architecture:** Make the four custom NewTypes UPath-backed (via `universal_pathlib`), treat local paths exactly as today, skip mount resolution for remote protocols, forward per-scheme credential env vars and config directories into container commands, and pre-flight `must_exist` on remote URIs before dispatch.

**Tech Stack:** Python 3.10+, `fsspec` + `universal_pathlib` (new core deps), optional extras `s3fs` / `gcsfs` / `adlfs`, existing libcst + typer + ruff toolchain.

**Spec:** `docs/superpowers/specs/2026-04-19-uri-object-store-support-design.md`

---

## File Structure

**Created:**
- `tests/test_upath_parser.py` — `parse_upath` unit tests.
- `tests/test_remote_uri_runner.py` — scheme detection, remote mount skipping, must_exist pre-flight, credential command construction, short-lived token heuristic. Uses fsspec `memory://` for remote behaviour.

**Modified:**
- `pyproject.toml` — add `fsspec`, `universal_pathlib` to core deps; add `s3` / `gcs` / `azure` / `all` extras.
- `src/hip_cargo/utils/types.py` — add `parse_upath` parser and re-export `UPath`.
- `src/hip_cargo/utils/introspector.py` — switch the four NewType wrappers to UPath supertypes.
- `src/hip_cargo/utils/runner.py` — widen `_is_path_type`; add protocol helpers, credential maps, `preflight_remote_must_exist`; skip remote UPaths in `_resolve_mounts`; thread credentials through `_build_container_cmd`; improve the "no runtime" error message with an extras hint.
- `src/hip_cargo/utils/cab_to_function.py` — change the path parser emitted in generated CLIs from `Path` to `parse_upath`; adjust the generated import block accordingly; emit a `preflight_remote_must_exist(...)` call at the top of the body.
- `src/hip_cargo/__init__.py` — export `parse_upath`, `UPath`.
- `Dockerfile` — install `hip-cargo[all]` instead of `.`.
- `README.md` — add "Remote URIs and object stores" section.
- `.claude/rules/architecture.md` — update §2 (types) and §4 (runtime) with UPath semantics and credential-forwarding table.
- `.claude/rules/python-standards.md` — §3 note on lazy fsspec backend imports.
- `.claude/rules/testing-and-ci.md` — guidance on `memory://` unit tests and `HIP_CARGO_LIVE_*` gating.

---

## Task 1: Add fsspec and universal_pathlib as core deps

**Files:**
- Modify: `pyproject.toml:25-32`

- [ ] **Step 1: Add core deps**

Edit `pyproject.toml` dependencies array to:

```toml
dependencies = [
    "typer>=0.12.0",
    "pyyaml>=6.0",
    "typing-extensions>=4.15.0",
    "libcst==1.8.6",
    "tomli>=2.0; python_version < '3.11'",
    "ruff>=0.13.2",
    "fsspec>=2024.10.0",
    "universal-pathlib>=0.2.5",
]
```

- [ ] **Step 2: Sync the environment**

Run: `uv sync`
Expected: installs `fsspec` and `universal-pathlib`, exits 0.

- [ ] **Step 3: Verify import**

Run: `uv run python -c "from upath import UPath; print(UPath('/tmp').protocol)"`
Expected: prints `""` (empty string for local paths). No error.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add fsspec and universal_pathlib as core dependencies"
```

---

## Task 2: Add `parse_upath` and re-export UPath

**Files:**
- Create: `tests/test_upath_parser.py`
- Modify: `src/hip_cargo/utils/types.py`
- Modify: `src/hip_cargo/__init__.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_upath_parser.py`:

```python
"""Tests for parse_upath and UPath re-export."""

from upath import UPath

from hip_cargo import UPath as ReexportedUPath
from hip_cargo.utils.types import parse_upath


def test_parse_upath_local_path():
    result = parse_upath("/tmp/foo")
    assert isinstance(result, UPath)
    assert result.protocol in ("", "file", "local")
    assert str(result) == "/tmp/foo"


def test_parse_upath_relative_path():
    result = parse_upath("data/x.fits")
    assert isinstance(result, UPath)
    assert result.protocol in ("", "file", "local")


def test_parse_upath_s3_uri():
    result = parse_upath("s3://my-bucket/key.fits")
    assert isinstance(result, UPath)
    assert result.protocol == "s3"


def test_parse_upath_gcs_uri():
    result = parse_upath("gs://my-bucket/key.fits")
    assert isinstance(result, UPath)
    assert result.protocol in ("gs", "gcs")


def test_parse_upath_memory_uri():
    result = parse_upath("memory:///scratch/x.bin")
    assert isinstance(result, UPath)
    assert result.protocol == "memory"


def test_upath_reexport_identity():
    assert ReexportedUPath is UPath
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/test_upath_parser.py -v`
Expected: FAIL (`parse_upath` does not exist, `UPath` not exported).

- [ ] **Step 3: Implement parse_upath**

Replace `src/hip_cargo/utils/types.py` with:

```python
"""Custom types for comma-separated list parameters and URI paths."""

from typing import NewType

from upath import UPath

ListInt = NewType("ListInt", str)
ListFloat = NewType("ListFloat", str)
ListStr = NewType("ListStr", str)


def parse_list_int(value: str) -> list[int]:
    """Parse a comma-separated string into a list of integers."""
    return [int(x.strip()) for x in value.split(",")]


def parse_list_float(value: str) -> list[float]:
    """Parse a comma-separated string into a list of floats."""
    return [float(x.strip()) for x in value.split(",")]


def parse_list_str(value: str) -> list[str]:
    """Parse a comma-separated string into a list of strings."""
    return [x.strip() for x in value.split(",")]


def parse_upath(value: str) -> UPath:
    """Parse a CLI string into a universal Path (local or remote URI)."""
    return UPath(value)
```

- [ ] **Step 4: Update `__init__.py` exports**

Replace `src/hip_cargo/__init__.py` with:

```python
"""hip-cargo: Tools for generating Stimela cab definitions."""

from upath import UPath

from hip_cargo.utils.config import get_container_image
from hip_cargo.utils.decorators import stimela_cab, stimela_output
from hip_cargo.utils.metadata import StimelaMeta
from hip_cargo.utils.types import (
    ListFloat,
    ListInt,
    ListStr,
    parse_list_float,
    parse_list_int,
    parse_list_str,
    parse_upath,
)

__version__ = "0.2.0"
__all__ = [
    "get_container_image",
    "stimela_cab",
    "stimela_output",
    "StimelaMeta",
    "ListInt",
    "ListFloat",
    "ListStr",
    "UPath",
    "parse_list_int",
    "parse_list_float",
    "parse_list_str",
    "parse_upath",
]
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_upath_parser.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 6: Lint**

Run: `uv run ruff format . && uv run ruff check . --fix`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/hip_cargo/utils/types.py src/hip_cargo/__init__.py tests/test_upath_parser.py
git commit -m "feat(types): add parse_upath parser and re-export UPath"
```

---

## Task 3: Switch NewType supertypes to UPath

**Files:**
- Modify: `src/hip_cargo/utils/introspector.py:1-14`

- [ ] **Step 1: Run the existing test suite for a baseline**

Run: `uv run pytest -v 2>&1 | tail -30`
Expected: a summary line showing PASSED (note the count; we want the same count after this task).

- [ ] **Step 2: Modify supertypes**

Edit `src/hip_cargo/utils/introspector.py:1-14` — replace:

```python
"""Function introspection for extracting cab information."""

import ast
import re
from pathlib import Path
from typing import Any, NewType

import libcst as cst
from libcst import matchers

MS = NewType("MS", Path)
Directory = NewType("Directory", Path)
File = NewType("File", Path)
URI = NewType("URI", Path)
```

with:

```python
"""Function introspection for extracting cab information."""

import ast
import re
from pathlib import Path  # noqa: F401 -- retained for downstream consumers
from typing import Any, NewType

import libcst as cst
from libcst import matchers
from upath import UPath

MS = NewType("MS", UPath)
Directory = NewType("Directory", UPath)
File = NewType("File", UPath)
URI = NewType("URI", UPath)
```

- [ ] **Step 3: Re-run the full suite**

Run: `uv run pytest -v 2>&1 | tail -30`
Expected: identical PASSED count to Step 1. If anything fails, it's a real regression — stop and fix before continuing.

- [ ] **Step 4: Commit**

```bash
git add src/hip_cargo/utils/introspector.py
git commit -m "feat(types): back File/Directory/MS/URI with UPath"
```

---

## Task 4: Widen `_is_path_type` to detect UPath

**Files:**
- Create test in: `tests/test_remote_uri_runner.py`
- Modify: `src/hip_cargo/utils/runner.py:215-246`

- [ ] **Step 1: Write the failing test**

Create `tests/test_remote_uri_runner.py`:

```python
"""Tests for remote-URI-aware runner behaviour."""

from hip_cargo.utils.introspector import Directory, File, MS, URI
from hip_cargo.utils.runner import _is_path_type


def test_is_path_type_detects_upath_newtypes():
    assert _is_path_type(File) is True
    assert _is_path_type(Directory) is True
    assert _is_path_type(MS) is True
    assert _is_path_type(URI) is True


def test_is_path_type_detects_list_of_upath_newtype():
    assert _is_path_type(list[File]) is True
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/test_remote_uri_runner.py -v`
Expected: FAILs — current `_is_path_type` terminates on `Path`, and UPath is not a `pathlib.Path` subclass.

- [ ] **Step 3: Widen the check**

In `src/hip_cargo/utils/runner.py` around line 215, replace the `_is_path_type` body's local-path branch:

```python
    # Direct Path check
    if tp is Path:
        return True
    if isinstance(tp, type) and issubclass(tp, Path):
        return True
```

with:

```python
    # Path / UPath check: match anything in the PurePath hierarchy
    import pathlib

    if tp is Path:
        return True
    if isinstance(tp, type) and issubclass(tp, pathlib.PurePath):
        return True
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_remote_uri_runner.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Re-run full suite**

Run: `uv run pytest -v 2>&1 | tail -10`
Expected: no regressions.

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff format . && uv run ruff check . --fix
git add src/hip_cargo/utils/runner.py tests/test_remote_uri_runner.py
git commit -m "feat(runner): widen _is_path_type to cover UPath"
```

---

## Task 5: Protocol helpers — remote detection and collection

**Files:**
- Modify: `tests/test_remote_uri_runner.py`
- Modify: `src/hip_cargo/utils/runner.py` (add helpers near `_is_path_type`)

- [ ] **Step 1: Append failing tests**

Append to `tests/test_remote_uri_runner.py`:

```python
from typing import Annotated

import typer
from upath import UPath

from hip_cargo.utils.runner import (
    _collect_remote_protocols,
    _is_remote_upath,
)


def test_is_remote_upath_local():
    assert _is_remote_upath(UPath("/tmp/x")) is False


def test_is_remote_upath_memory():
    assert _is_remote_upath(UPath("memory:///scratch/x")) is True


def test_is_remote_upath_s3():
    assert _is_remote_upath(UPath("s3://bkt/k")) is True


def test_collect_remote_protocols_mixed():
    def fn(
        a: Annotated[File, typer.Option()] = UPath("/tmp/a"),  # noqa: B008
        b: Annotated[File, typer.Option()] = UPath("s3://bkt/b"),  # noqa: B008
        c: Annotated[File, typer.Option()] = UPath("memory:///c"),  # noqa: B008
    ) -> None:
        pass

    params = {
        "a": UPath("/tmp/a"),
        "b": UPath("s3://bkt/b"),
        "c": UPath("memory:///c"),
    }
    protocols = _collect_remote_protocols(fn, params)
    assert protocols == {"s3", "memory"}


def test_collect_remote_protocols_all_local():
    def fn(a: Annotated[File, typer.Option()] = UPath("/tmp/a")) -> None:  # noqa: B008
        pass

    assert _collect_remote_protocols(fn, {"a": UPath("/tmp/a")}) == set()
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/test_remote_uri_runner.py -v`
Expected: four new FAILs (`_is_remote_upath`, `_collect_remote_protocols` not defined).

- [ ] **Step 3: Implement helpers**

Add near the bottom of `src/hip_cargo/utils/runner.py` (below `_is_path_type`):

```python
_LOCAL_PROTOCOLS = frozenset({"", "file", "local"})


def _is_remote_upath(value: typing.Any) -> bool:
    """Return True if value is a UPath with a non-local protocol."""
    protocol = getattr(value, "protocol", None)
    if protocol is None:
        return False
    if isinstance(protocol, tuple):
        protocol = protocol[0] if protocol else ""
    return protocol not in _LOCAL_PROTOCOLS


def _collect_remote_protocols(
    func: typing.Callable, params: dict[str, typing.Any]
) -> set[str]:
    """Scan path-typed params and return the set of non-local protocols in use."""
    hints = typing.get_type_hints(func, include_extras=True)
    protocols: set[str] = set()
    for name, value in params.items():
        if value is None:
            continue
        if name in hints and not _is_path_type(hints[name]):
            continue
        values = value if isinstance(value, list) else [value]
        for v in values:
            if _is_remote_upath(v):
                proto = v.protocol
                if isinstance(proto, tuple):
                    proto = proto[0]
                protocols.add(proto)
    return protocols
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_remote_uri_runner.py -v`
Expected: all tests in the file PASS.

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff format . && uv run ruff check . --fix
git add src/hip_cargo/utils/runner.py tests/test_remote_uri_runner.py
git commit -m "feat(runner): add remote-URI protocol detection helpers"
```

---

## Task 6: `_resolve_mounts` skips remote UPaths

**Files:**
- Modify: `tests/test_remote_uri_runner.py`
- Modify: `src/hip_cargo/utils/runner.py:141-168` (inside `_resolve_mounts`)

- [ ] **Step 1: Append failing test**

Append to `tests/test_remote_uri_runner.py`:

```python
from hip_cargo.utils.runner import _resolve_mounts


def test_resolve_mounts_skips_remote_upaths(tmp_path):
    local = tmp_path / "local.fits"
    local.write_bytes(b"data")

    def fn(
        a: Annotated[File, typer.Option()] = UPath(str(local)),  # noqa: B008
        b: Annotated[File, typer.Option()] = UPath("s3://bkt/k"),  # noqa: B008
    ) -> None:
        pass

    params = {"a": UPath(str(local)), "b": UPath("s3://bkt/k")}
    mounts = _resolve_mounts(fn, params)

    # Remote param contributes nothing.
    assert not any("s3" in p or "bkt" in p for p in mounts)
    # Local param still produces a mount.
    assert any(str(tmp_path) in p for p in mounts)
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/test_remote_uri_runner.py::test_resolve_mounts_skips_remote_upaths -v`
Expected: FAIL — current code tries to `Path(...).resolve()` the `s3://bkt/k` string and either produces a nonsensical mount or raises.

- [ ] **Step 3: Skip remote UPaths inside `_resolve_mounts`**

Inside `_resolve_mounts`, find the loop:

```python
        for p in paths:
            if not isinstance(p, Path):
                continue
            abs_path = p.resolve()
```

Replace with:

```python
        for p in paths:
            if _is_remote_upath(p):
                continue
            if not isinstance(p, Path):
                continue
            abs_path = p.resolve()
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_remote_uri_runner.py -v`
Expected: PASS, and no regressions in `test_runner.py`.

- [ ] **Step 5: Commit**

```bash
uv run ruff format . && uv run ruff check . --fix
git add src/hip_cargo/utils/runner.py tests/test_remote_uri_runner.py
git commit -m "feat(runner): skip remote UPaths in mount resolution"
```

---

## Task 7: `preflight_remote_must_exist` helper

**Files:**
- Modify: `tests/test_remote_uri_runner.py`
- Modify: `src/hip_cargo/utils/runner.py` (add helper; uses existing `_extract_stimela_meta_from_hints`)

- [ ] **Step 1: Append failing tests**

Append to `tests/test_remote_uri_runner.py`:

```python
import pytest
import fsspec
import typer as _typer

from hip_cargo.utils.metadata import StimelaMeta
from hip_cargo.utils.runner import preflight_remote_must_exist


def test_preflight_passes_for_existing_remote_upath():
    fs = fsspec.filesystem("memory")
    with fs.open("/present.bin", "wb") as f:
        f.write(b"x")

    def fn(
        x: Annotated[File, _typer.Option(), StimelaMeta(must_exist=True)] = UPath(  # noqa: B008
            "memory:///present.bin"
        ),
    ) -> None:
        pass

    preflight_remote_must_exist(fn, {"x": UPath("memory:///present.bin")})


def test_preflight_fails_for_missing_remote_upath():
    def fn(
        x: Annotated[File, _typer.Option(), StimelaMeta(must_exist=True)] = UPath(  # noqa: B008
            "memory:///absent.bin"
        ),
    ) -> None:
        pass

    with pytest.raises(_typer.Exit):
        preflight_remote_must_exist(fn, {"x": UPath("memory:///absent.bin")})


def test_preflight_ignores_local_paths(tmp_path):
    missing = tmp_path / "does-not-exist.bin"

    def fn(
        x: Annotated[File, _typer.Option(), StimelaMeta(must_exist=True)] = UPath(  # noqa: B008
            str(missing)
        ),
    ) -> None:
        pass

    # Local paths are not pre-flighted here — mount logic owns that contract.
    preflight_remote_must_exist(fn, {"x": UPath(str(missing))})


def test_preflight_ignores_params_without_must_exist():
    def fn(
        x: Annotated[File, _typer.Option()] = UPath("memory:///nope.bin"),  # noqa: B008
    ) -> None:
        pass

    # No StimelaMeta(must_exist=True) → skip.
    preflight_remote_must_exist(fn, {"x": UPath("memory:///nope.bin")})
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/test_remote_uri_runner.py -k preflight -v`
Expected: FAIL — `preflight_remote_must_exist` not defined.

- [ ] **Step 3: Implement the helper**

Add to `src/hip_cargo/utils/runner.py` (below `_collect_remote_protocols`):

```python
def preflight_remote_must_exist(
    func: typing.Callable, params: dict[str, typing.Any]
) -> None:
    """For remote UPath params whose metadata sets must_exist=True, verify they exist.

    Local paths and params without ``must_exist`` are ignored — those contracts
    are enforced elsewhere (mount logic for local paths; the user's own code
    otherwise). Raises ``typer.Exit(1)`` on a missing remote URI.
    """
    import typer

    stimela_meta = _extract_stimela_meta_from_hints(func)
    output_meta: dict[str, dict] = {}
    for output_def in getattr(func, "__stimela_outputs__", []):
        py_name = output_def["name"].replace("-", "_")
        output_meta[py_name] = output_def

    for name, value in params.items():
        if value is None:
            continue
        values = value if isinstance(value, list) else [value]
        meta = stimela_meta.get(name, {})
        output_def = output_meta.get(name, {})
        must_exist = meta.get("must_exist", output_def.get("must_exist"))
        if not must_exist:
            continue
        for v in values:
            if not _is_remote_upath(v):
                continue
            if not v.exists():
                typer.echo(
                    f"Parameter '{name}': '{v}' does not exist",
                    err=True,
                )
                raise typer.Exit(code=1)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_remote_uri_runner.py -k preflight -v`
Expected: all 4 preflight tests PASS.

- [ ] **Step 5: Commit**

```bash
uv run ruff format . && uv run ruff check . --fix
git add src/hip_cargo/utils/runner.py tests/test_remote_uri_runner.py
git commit -m "feat(runner): add preflight_remote_must_exist for remote URIs"
```

---

## Task 8: Emit `preflight_remote_must_exist` in generated wrappers and switch parser to `parse_upath`

**Files:**
- Modify: `src/hip_cargo/utils/cab_to_function.py:388-404` and the header-generation section.
- Modify/Update: `tests/test_generate_function_body.py` (existing tests need updating for the new output).

- [ ] **Step 1: Inspect which existing tests pin the generated code**

Run: `uv run pytest tests/test_generate_function_body.py tests/test_roundtrip.py -v 2>&1 | tail -20`
Expected: baseline PASS. If any test strings contain `parser=Path`, they are tests we will need to update in this task.

- [ ] **Step 2: Switch the default path parser to `parse_upath`**

In `src/hip_cargo/utils/cab_to_function.py` around lines 388-394, replace:

```python
    # Determine parser: list types use their own parser, custom types use Path
    parser_str = None
    if list_type_name:
        parser_str = LIST_TYPE_PARSERS[list_type_name]
    elif needs_parser:
        parser_str = "Path"
```

with:

```python
    # Determine parser: list types use their own parser, custom path types
    # use parse_upath so the CLI accepts local paths or remote URIs.
    parser_str = None
    if list_type_name:
        parser_str = LIST_TYPE_PARSERS[list_type_name]
    elif needs_parser:
        parser_str = "parse_upath"
```

- [ ] **Step 3: Update the generated import block**

Search for the string `from pathlib import Path` in `cab_to_function.py` (used to be emitted when path types were in use). Replace the import it emits with a `from hip_cargo import parse_upath` line when any custom path type is used. If no such emission logic exists (the current code references `Path` without an import, relying on user namespace), search for `needs_parser` / `custom_types` to find the guard and add an emit for `parse_upath`.

Run: `grep -n "parse_upath\|from pathlib\|from hip_cargo" src/hip_cargo/utils/cab_to_function.py`
Expected: the regeneration logic imports `parse_upath` whenever `needs_parser` is true for a non-list custom path type.

If the existing code has no such import emission (parser was previously `Path` which resolves via user code), add it in the header-generation block: find where `parse_list_int` etc. are conditionally imported and add `parse_upath` to that same conditional import when any of `File`/`Directory`/`MS`/`URI` appears in the cab.

- [ ] **Step 4: Emit preflight call inside the try block (or at body top when no image)**

The preflight calls `.exists()` on remote UPaths, which can raise `ImportError`
if the relevant fsspec backend is missing. That `ImportError` must be caught by
the same `try/except` that guards the lazy core import, so the preflight call
must live **inside** that `try` block. When the cab has no image (no fallback
available), the preflight runs at the top of the body directly.

In `generate_function_body`:

When `has_image` is True, emit the preflight INSIDE the existing `try:` block
BEFORE the lazy-import line (at the `indent = "            "` level):

```python
        lines.append(f"{indent}# Pre-flight must_exist for remote URIs before dispatching.")
        lines.append(f"{indent}from hip_cargo.utils.runner import preflight_remote_must_exist  # noqa: E402")
        lines.append(f"{indent}preflight_remote_must_exist(")
        lines.append(f"{indent}    {func_name},")
        lines.append(f"{indent}    dict(")
        for param_name in inputs:
            py_name = param_name.replace("-", "_")
            lines.append(f"{indent}        {py_name}={py_name},")
        for output_name in outputs:
            py_name = output_name.replace("-", "_")
            lines.append(f"{indent}        {py_name}={py_name},")
        lines.append(f"{indent}    ),")
        lines.append(f"{indent})")
        lines.append("")
```

When `has_image` is False, emit the same block at body-top indentation (`"    "`):

```python
    lines.append("    # Pre-flight must_exist for remote URIs before dispatching.")
    lines.append("    from hip_cargo.utils.runner import preflight_remote_must_exist  # noqa: E402")
    lines.append("    preflight_remote_must_exist(")
    lines.append(f"        {func_name},")
    lines.append("        dict(")
    for param_name in inputs:
        py_name = param_name.replace("-", "_")
        lines.append(f"            {py_name}={py_name},")
    for output_name in outputs:
        py_name = output_name.replace("-", "_")
        lines.append(f"            {py_name}={py_name},")
    lines.append("        ),")
    lines.append("    )")
    lines.append("")
```

Both branches emit the block just before the existing `# Lazy import the core
implementation` line.

- [ ] **Step 5: Update existing generated-code tests**

Any test asserting on `parser=Path` in the generated output must be updated to expect `parser=parse_upath`. Run:

```bash
grep -rn "parser=Path" tests/
```

For every match, replace `parser=Path` with `parser=parse_upath` in the expected-output string. Any test asserting on the expected header imports may also need `parse_upath` added.

- [ ] **Step 6: Regenerate committed cab-derived code (if any)**

Run the cab generation round-trip used by existing tests to confirm no stale artifacts:

```bash
uv run pytest tests/test_roundtrip.py tests/test_generate_function_body.py tests/test_pfb_imaging_roundtrip.py -v 2>&1 | tail -30
```

Expected: all PASS. If failures point at an unmatched expected string, update the expected string (the behaviour change is intentional).

- [ ] **Step 7: Lint + commit**

```bash
uv run ruff format . && uv run ruff check . --fix
git add src/hip_cargo/utils/cab_to_function.py tests/
git commit -m "feat(codegen): emit parse_upath parser and must_exist pre-flight"
```

---

## Task 9: Credential env-var and config-dir maps

**Files:**
- Modify: `tests/test_remote_uri_runner.py`
- Modify: `src/hip_cargo/utils/runner.py` (add constants + helpers)

- [ ] **Step 1: Append failing tests**

Append:

```python
import os
from pathlib import Path as _Path
from unittest import mock

from hip_cargo.utils.runner import (
    _build_credential_env,
    _build_credential_mounts,
)


def test_credential_env_s3_when_vars_present():
    env = {
        "AWS_ACCESS_KEY_ID": "k",
        "AWS_SECRET_ACCESS_KEY": "s",
        "AWS_REGION": "eu-west-1",
        "UNRELATED": "ignore",
    }
    result = _build_credential_env({"s3"}, env)
    assert result["AWS_ACCESS_KEY_ID"] == "k"
    assert result["AWS_SECRET_ACCESS_KEY"] == "s"
    assert result["AWS_REGION"] == "eu-west-1"
    assert "UNRELATED" not in result


def test_credential_env_skips_unset_vars():
    result = _build_credential_env({"s3"}, {"AWS_ACCESS_KEY_ID": "k"})
    assert result == {"AWS_ACCESS_KEY_ID": "k"}


def test_credential_env_gcs_includes_app_creds():
    env = {"GOOGLE_APPLICATION_CREDENTIALS": "/home/u/key.json"}
    result = _build_credential_env({"gcs"}, env)
    assert result["GOOGLE_APPLICATION_CREDENTIALS"] == "/home/u/key.json"


def test_credential_env_azure():
    env = {"AZURE_STORAGE_ACCOUNT": "acct", "AZURE_STORAGE_KEY": "k"}
    result = _build_credential_env({"az"}, env)
    assert result["AZURE_STORAGE_ACCOUNT"] == "acct"
    assert result["AZURE_STORAGE_KEY"] == "k"


def test_credential_mounts_s3(tmp_path):
    home = tmp_path / "home"
    aws = home / ".aws"
    aws.mkdir(parents=True)
    (aws / "credentials").write_text("[default]\n")

    mounts, keyfile = _build_credential_mounts(
        {"s3"}, env={}, home=home
    )
    assert str(aws) in mounts
    assert keyfile is None


def test_credential_mounts_s3_skipped_with_session_token(tmp_path):
    home = tmp_path / "home"
    aws = home / ".aws"
    aws.mkdir(parents=True)

    mounts, _ = _build_credential_mounts(
        {"s3"}, env={"AWS_SESSION_TOKEN": "temp"}, home=home
    )
    assert str(aws) not in mounts


def test_credential_mounts_gcs_binds_key_file(tmp_path):
    home = tmp_path / "home"
    key = tmp_path / "service-account.json"
    key.write_text("{}")

    mounts, keyfile = _build_credential_mounts(
        {"gcs"},
        env={"GOOGLE_APPLICATION_CREDENTIALS": str(key)},
        home=home,
    )
    assert str(key) in mounts
    assert keyfile == str(key)


def test_credential_mounts_gcs_binds_config_dir(tmp_path):
    home = tmp_path / "home"
    gcloud = home / ".config" / "gcloud"
    gcloud.mkdir(parents=True)

    mounts, _ = _build_credential_mounts({"gcs"}, env={}, home=home)
    assert str(gcloud) in mounts


def test_credential_mounts_azure(tmp_path):
    home = tmp_path / "home"
    azure = home / ".azure"
    azure.mkdir(parents=True)

    mounts, _ = _build_credential_mounts({"az"}, env={}, home=home)
    assert str(azure) in mounts
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/test_remote_uri_runner.py -k credential -v`
Expected: FAIL — helpers not defined.

- [ ] **Step 3: Implement the maps and helpers**

Append to `src/hip_cargo/utils/runner.py`:

```python
# Per-scheme credential mapping. Keys are normalised protocol names; values
# are the host env vars to forward when the scheme is present in the params.
_CREDENTIAL_ENV_VARS: dict[str, tuple[str, ...]] = {
    "s3": (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_PROFILE",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "AWS_ENDPOINT_URL",
    ),
    "gcs": ("GOOGLE_APPLICATION_CREDENTIALS",),
    "az": (
        "AZURE_STORAGE_ACCOUNT",
        "AZURE_STORAGE_KEY",
        "AZURE_STORAGE_CONNECTION_STRING",
        "AZURE_CLIENT_ID",
        "AZURE_TENANT_ID",
        "AZURE_CLIENT_SECRET",
    ),
}

# Alternate protocol names that should share a credential group.
_PROTOCOL_ALIASES: dict[str, str] = {
    "gs": "gcs",
    "abfs": "az",
    "adl": "az",
}


def _normalise_protocol(proto: str) -> str:
    return _PROTOCOL_ALIASES.get(proto, proto)


def _build_credential_env(
    protocols: set[str], env: dict[str, str]
) -> dict[str, str]:
    """Return host env vars to forward for the given protocol set."""
    result: dict[str, str] = {}
    seen: set[str] = set()
    for proto in protocols:
        group = _normalise_protocol(proto)
        for var in _CREDENTIAL_ENV_VARS.get(group, ()):
            if var in seen:
                continue
            seen.add(var)
            if var in env:
                result[var] = env[var]
    return result


def _build_credential_mounts(
    protocols: set[str],
    env: dict[str, str],
    home: os.PathLike[str] | str,
) -> tuple[dict[str, bool], str | None]:
    """Return read-only mounts + optional GCS key file path for the given protocols."""
    home_path = Path(home)
    mounts: dict[str, bool] = {}
    keyfile: str | None = None

    for proto in protocols:
        group = _normalise_protocol(proto)
        if group == "s3":
            # Skip ~/.aws when short-lived creds are active to avoid stale
            # profile files masking the session.
            if "AWS_SESSION_TOKEN" in env:
                continue
            aws = home_path / ".aws"
            if aws.is_dir():
                mounts[str(aws)] = False
        elif group == "gcs":
            gcloud = home_path / ".config" / "gcloud"
            if gcloud.is_dir():
                mounts[str(gcloud)] = False
            key = env.get("GOOGLE_APPLICATION_CREDENTIALS")
            if key:
                key_path = Path(key)
                if key_path.is_file():
                    mounts[str(key_path)] = False
                    keyfile = str(key_path)
        elif group == "az":
            azure = home_path / ".azure"
            if azure.is_dir():
                mounts[str(azure)] = False

    return mounts, keyfile
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_remote_uri_runner.py -k credential -v`
Expected: all credential tests PASS.

- [ ] **Step 5: Commit**

```bash
uv run ruff format . && uv run ruff check . --fix
git add src/hip_cargo/utils/runner.py tests/test_remote_uri_runner.py
git commit -m "feat(runner): add per-scheme credential env/mount maps"
```

---

## Task 10: Thread credentials through `_build_container_cmd`

**Files:**
- Modify: `tests/test_remote_uri_runner.py`
- Modify: `src/hip_cargo/utils/runner.py` — `_build_container_cmd` and `run_in_container`

- [ ] **Step 1: Append failing tests**

```python
from hip_cargo.utils.runner import _build_container_cmd


def test_build_container_cmd_docker_forwards_env_and_mounts():
    cmd = _build_container_cmd(
        runtime="docker",
        image="ghcr.io/u/r:tag",
        mounts={"/data": True},
        cwd="/data",
        cli_args=["hip-cargo", "some-cmd"],
        cred_env={"AWS_ACCESS_KEY_ID": "k", "AWS_SECRET_ACCESS_KEY": "s"},
        cred_mounts={"/home/u/.aws": False},
    )
    assert "-e" in cmd
    assert "AWS_ACCESS_KEY_ID=k" in cmd
    assert "AWS_SECRET_ACCESS_KEY=s" in cmd
    assert "/home/u/.aws:/home/u/.aws:ro" in cmd


def test_build_container_cmd_apptainer_forwards_env_and_mounts():
    cmd = _build_container_cmd(
        runtime="apptainer",
        image="ghcr.io/u/r:tag",
        mounts={"/data": True},
        cwd="/data",
        cli_args=["hip-cargo", "some-cmd"],
        cred_env={"AWS_ACCESS_KEY_ID": "k"},
        cred_mounts={"/home/u/.aws": False},
    )
    assert "--env" in cmd
    assert "AWS_ACCESS_KEY_ID=k" in cmd
    assert any("/home/u/.aws:/home/u/.aws:ro" in arg for arg in cmd)


def test_build_container_cmd_no_creds_keeps_existing_output():
    cmd = _build_container_cmd(
        runtime="docker",
        image="img",
        mounts={"/data": True},
        cwd="/data",
        cli_args=["hip-cargo"],
        cred_env={},
        cred_mounts={},
    )
    # No credential env flags when nothing to forward.
    assert not any(v.startswith("AWS_") for v in cmd)
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/test_remote_uri_runner.py -k build_container_cmd -v`
Expected: FAIL — `_build_container_cmd` signature does not accept `cred_env` / `cred_mounts`.

- [ ] **Step 3: Update `_build_container_cmd`**

In `src/hip_cargo/utils/runner.py`, change the signature and body of `_build_container_cmd`:

```python
def _build_container_cmd(
    runtime: str,
    image: str,
    mounts: dict[str, bool],
    cwd: str,
    cli_args: list[str],
    cred_env: dict[str, str] | None = None,
    cred_mounts: dict[str, bool] | None = None,
) -> list[str]:
    """Assemble the full container execution command."""
    cred_env = cred_env or {}
    cred_mounts = cred_mounts or {}
    all_mounts = {**mounts, **cred_mounts}

    if runtime in ("apptainer", "singularity"):
        cmd = [runtime, "exec", "--pwd", cwd]
        for path, rw in sorted(all_mounts.items()):
            mode = "rw" if rw else "ro"
            cmd.extend(["--bind", f"{path}:{path}:{mode}"])
        for var, value in sorted(cred_env.items()):
            cmd.extend(["--env", f"{var}={value}"])
        if not image.endswith(".sif") and "://" not in image:
            image = f"docker://{image}"
        cmd.append(image)
    else:  # docker, podman
        uid_gid = f"{os.getuid()}:{os.getgid()}"
        cmd = [runtime, "run", "--rm", "--user", uid_gid, "-w", cwd]
        for path, rw in sorted(all_mounts.items()):
            mode = "rw" if rw else "ro"
            cmd.extend(["-v", f"{path}:{path}:{mode}"])
        for var, value in sorted(cred_env.items()):
            cmd.extend(["-e", f"{var}={value}"])
        cmd.append(image)

    cmd.extend(cli_args)
    return cmd
```

- [ ] **Step 4: Wire `run_in_container` to collect and pass credentials**

In `run_in_container`, after `mounts = _resolve_mounts(func, params)`, add:

```python
    protocols = _collect_remote_protocols(func, params)
    cred_env = _build_credential_env(protocols, dict(os.environ))
    cred_mounts, _gcs_keyfile = _build_credential_mounts(
        protocols, dict(os.environ), home=os.path.expanduser("~")
    )
```

Then update the `_build_container_cmd(...)` call site to pass `cred_env=cred_env, cred_mounts=cred_mounts`.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_remote_uri_runner.py -v`
Expected: all tests in the file PASS.

- [ ] **Step 6: Full suite + lint**

Run: `uv run pytest -v 2>&1 | tail -20 && uv run ruff format . && uv run ruff check . --fix`
Expected: no regressions, clean lint.

- [ ] **Step 7: Commit**

```bash
git add src/hip_cargo/utils/runner.py tests/test_remote_uri_runner.py
git commit -m "feat(runner): forward credential env/mounts to container cmd"
```

---

## Task 11: Improve "no runtime" error with extras hint

**Files:**
- Modify: `tests/test_remote_uri_runner.py`
- Modify: `src/hip_cargo/utils/runner.py:64-72` — `_detect_runtime` error message

- [ ] **Step 1: Append failing test**

```python
def test_detect_runtime_error_mentions_extras_when_s3_in_argv(monkeypatch):
    from hip_cargo.utils import runner

    monkeypatch.setattr(runner.shutil, "which", lambda _: None)
    monkeypatch.setattr("sys.argv", ["hip-cargo", "--input", "s3://bkt/k"])

    with pytest.raises(RuntimeError) as exc:
        runner._detect_runtime("auto")

    assert "hip-cargo[s3]" in str(exc.value)


def test_detect_runtime_error_plain_when_no_remote_scheme(monkeypatch):
    from hip_cargo.utils import runner

    monkeypatch.setattr(runner.shutil, "which", lambda _: None)
    monkeypatch.setattr("sys.argv", ["hip-cargo", "--input", "/tmp/x"])

    with pytest.raises(RuntimeError) as exc:
        runner._detect_runtime("auto")

    assert "hip-cargo[" not in str(exc.value)
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/test_remote_uri_runner.py -k detect_runtime -v`
Expected: FAIL.

- [ ] **Step 3: Enhance `_detect_runtime`**

Replace the bottom of `_detect_runtime`:

```python
    raise RuntimeError(
        "No container runtime found. Install one of: "
        + ", ".join(CONTAINER_RUNTIMES)
        + "\nOr install the full package dependencies to run natively."
    )
```

with:

```python
    hint = _extras_hint_from_argv(sys.argv)
    msg = (
        "No container runtime found. Install one of: "
        + ", ".join(CONTAINER_RUNTIMES)
        + "\nOr install the full package dependencies to run natively."
    )
    if hint:
        msg += f"\nFor remote URIs, install the relevant extra: {hint}"
    raise RuntimeError(msg)
```

And add this helper in the same module (near the top, below `CONTAINER_RUNTIMES`):

```python
_EXTRA_FOR_SCHEME: dict[str, str] = {
    "s3": "hip-cargo[s3]",
    "gs": "hip-cargo[gcs]",
    "gcs": "hip-cargo[gcs]",
    "az": "hip-cargo[azure]",
    "abfs": "hip-cargo[azure]",
    "adl": "hip-cargo[azure]",
}


def _extras_hint_from_argv(argv: list[str]) -> str:
    """Scan argv for remote URIs and return a `pip install` hint."""
    hints: set[str] = set()
    for arg in argv:
        for scheme, extra in _EXTRA_FOR_SCHEME.items():
            if arg.startswith(f"{scheme}://"):
                hints.add(extra)
    return ", ".join(sorted(hints))
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_remote_uri_runner.py -k detect_runtime -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run ruff format . && uv run ruff check . --fix
git add src/hip_cargo/utils/runner.py tests/test_remote_uri_runner.py
git commit -m "feat(runner): hint at hip-cargo[s3/gcs/azure] extras on missing runtime"
```

---

## Task 12: Declare optional backend extras

**Files:**
- Modify: `pyproject.toml` (below `[project.urls]`)

- [ ] **Step 1: Add `[project.optional-dependencies]`**

Append immediately after the `[project.urls]` block in `pyproject.toml`:

```toml
[project.optional-dependencies]
s3 = ["s3fs>=2024.10.0"]
gcs = ["gcsfs>=2024.10.0"]
azure = ["adlfs>=2024.7.0"]
all = ["hip-cargo[s3,gcs,azure]"]
```

- [ ] **Step 2: Verify the extras resolve**

Run: `uv sync --all-extras`
Expected: resolves and installs `s3fs`, `gcsfs`, `adlfs` without error.

- [ ] **Step 3: Quick smoke test**

Run:
```bash
uv run python -c "from upath import UPath; u = UPath('s3://no-such-bucket-12345/x'); print(u.protocol)"
```
Expected: prints `s3`. No ImportError.

- [ ] **Step 4: Back out extras from the default environment**

Run: `uv sync`
Expected: removes the optional backends, leaves the core install intact. This verifies the extras really are optional.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat(packaging): add s3/gcs/azure/all optional extras"
```

---

## Task 13: Update Dockerfile to install `hip-cargo[all]`

**Files:**
- Modify: `Dockerfile:13`

- [ ] **Step 1: Change the install line**

Replace `RUN uv pip install --system --no-cache .` with:

```dockerfile
RUN uv pip install --system --no-cache '.[all]'
```

- [ ] **Step 2: Build the image locally to verify**

Run: `docker build -t hip-cargo:uri-test .` (use `podman` if docker is unavailable).
Expected: build succeeds; the final `hip-cargo --help` smoke runs without ImportError.

- [ ] **Step 3: Quick protocol check inside the image**

Run:
```bash
docker run --rm hip-cargo:uri-test python -c "import s3fs, gcsfs, adlfs; print('ok')"
```
Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile
git commit -m "build(docker): install hip-cargo[all] for remote URI support"
```

---

## Task 14: README section on Remote URIs and object stores

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Locate insertion point**

Run: `grep -n "^##" README.md | head -20`
Expected output shows the top-level section headings. Identify a reasonable slot (usually after "Features" or "Custom types" and before "Development" / "Contributing").

- [ ] **Step 2: Insert the new section**

Add the following section at the chosen point:

```markdown
## Remote URIs and object stores

`File`, `Directory`, `MS`, and `URI` are backed by
[`universal_pathlib.UPath`](https://github.com/fsspec/universal_pathlib),
so every path-typed parameter accepts either a local filesystem path or a
remote URI: `s3://bucket/key`, `gs://bucket/key`, `az://container/key`,
`http(s)://...`, plus any other scheme fsspec supports (`memory://`, `ftp://`,
etc.).

### Installing backends

hip-cargo's core install includes `fsspec` and `universal_pathlib`. Cloud
backends are optional extras — install only what you need:

```bash
pip install 'hip-cargo[s3]'       # AWS S3 / S3-compatible endpoints
pip install 'hip-cargo[gcs]'      # Google Cloud Storage
pip install 'hip-cargo[azure]'    # Azure Blob Storage
pip install 'hip-cargo[all]'      # all three
```

### Credentials

Native execution uses each SDK's standard credential chain — no hip-cargo
configuration. You already have the right setup if any of these work today:

- **AWS:** `AWS_*` env vars, `~/.aws/credentials`, IAM instance/role creds
- **GCS:** `GOOGLE_APPLICATION_CREDENTIALS`, `gcloud auth
  application-default login`, workload identity
- **Azure:** `AZURE_*` env vars, `az login`, managed identity

When hip-cargo falls back to container execution, it forwards the relevant
credentials automatically based on the schemes it detects in your
parameters:

| Scheme | Env vars forwarded | Config dir mounted (ro) |
|---|---|---|
| `s3` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_PROFILE`, `AWS_REGION`, `AWS_DEFAULT_REGION`, `AWS_ENDPOINT_URL` | `~/.aws` (skipped if `AWS_SESSION_TOKEN` is set) |
| `gs` / `gcs` | `GOOGLE_APPLICATION_CREDENTIALS` | `~/.config/gcloud` + the keyfile |
| `az` / `abfs` / `adl` | `AZURE_STORAGE_ACCOUNT`, `AZURE_STORAGE_KEY`, `AZURE_STORAGE_CONNECTION_STRING`, `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET` | `~/.azure` |

### Example

```python
from typing import Annotated

import typer
from hip_cargo import File, stimela_cab

@stimela_cab(name="inspect", info="Inspect a FITS file header")
def inspect(
    image: Annotated[File, typer.Option(..., help="Path or URI to a FITS image")],
) -> None:
    # image is a UPath — same API locally and remotely.
    with image.open("rb") as fh:
        header = fh.read(2880)
    print(header[:80])
```

Invoke it with either a local path or a remote URI:

```bash
hip-cargo inspect --image /data/x.fits
hip-cargo inspect --image s3://my-bucket/x.fits
```

### What about `must_exist`, `mkdir`, and `write_parent`?

For remote URIs, hip-cargo pre-flights `must_exist` with a single `exists()`
call before dispatch, failing fast on typos or missing objects. `mkdir`,
`write_parent`, and `access_parent` are skipped for remote URIs — they map
to local container mount logic that has no meaning on object stores. Local
paths keep their existing mount-driven semantics.
```

- [ ] **Step 3: Preview the markdown**

Run: `uv run python -c "import pathlib; print(pathlib.Path('README.md').read_text()[:500])"` (or open in an editor).
Expected: the new section appears cleanly.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs(readme): add Remote URIs and object stores section"
```

---

## Task 15: Update `.claude/rules/architecture.md`

**Files:**
- Modify: `.claude/rules/architecture.md`

- [ ] **Step 1: Update §2 "Type Handling & Stimela Metadata"**

At the end of §2, append:

```markdown
* **UPath-backed path types:** `File`, `Directory`, `MS`, and `URI` are all
  `NewType(..., UPath)`. User functions receive a
  `universal_pathlib.UPath` instance and call `.open()` / `.read_bytes()` /
  `.exists()` directly — hip-cargo does no IO. Local paths behave exactly
  like `pathlib.Path`; remote URIs (`s3://`, `gs://`, `az://`, `http(s)://`)
  are handled by the matching fsspec backend. Only the `URI` / `File` etc.
  wrappers emit the `parse_upath` parser in generated Typer CLIs; lists
  keep their comma-separated parsers.
```

- [ ] **Step 2: Update §4 "Runtime Execution & Fallback"**

Append to §4:

```markdown
* **Remote URIs:** When a path-typed param carries a non-local UPath
  (`protocol not in {"", "file", "local"}`):
  * `_resolve_mounts` skips it — remote URIs contribute no bind mounts.
  * `preflight_remote_must_exist` calls `upath.exists()` before dispatch
    when `must_exist=True`. Missing → `typer.Exit(1)`. `mkdir` /
    `write_parent` / `access_parent` are skipped (no meaning on object
    stores).
  * `run_in_container` forwards per-scheme credentials into the container:

    | Scheme | Env vars forwarded | Config dir mounted (ro) |
    |---|---|---|
    | `s3` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_PROFILE`, `AWS_REGION`, `AWS_DEFAULT_REGION`, `AWS_ENDPOINT_URL` | `~/.aws` (skipped if `AWS_SESSION_TOKEN` is set) |
    | `gs` / `gcs` | `GOOGLE_APPLICATION_CREDENTIALS` | `~/.config/gcloud` + the keyfile |
    | `az` / `abfs` / `adl` | `AZURE_STORAGE_ACCOUNT`, `AZURE_STORAGE_KEY`, `AZURE_STORAGE_CONNECTION_STRING`, `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET` | `~/.azure` |

* **Missing backend extras:** If a user passes `s3://...` without
  `hip-cargo[s3]` installed, UPath raises `ImportError`. The generated
  wrapper's existing `try/except ImportError → run_in_container` pattern
  catches this, so users with a runtime installed fall through to
  containerised execution; users without a runtime get an enhanced error
  that suggests `pip install hip-cargo[s3]` (or `[gcs]`/`[azure]`).
```

- [ ] **Step 2b: Reflect the emitted parser name**

Under §3 ("Code Generation & Subprocesses"), find the paragraph mentioning the path parser; update references from `Path` to `parse_upath` so the rule matches the generated output.

- [ ] **Step 3: Commit**

```bash
git add .claude/rules/architecture.md
git commit -m "docs(rules): document UPath types and remote URI credential plumbing"
```

---

## Task 16: Update `.claude/rules/python-standards.md` and `testing-and-ci.md`

**Files:**
- Modify: `.claude/rules/python-standards.md` (§3)
- Modify: `.claude/rules/testing-and-ci.md` (§1)

- [ ] **Step 1: Extend `python-standards.md` §3**

Append to §3 ("Lazy Imports for CLI Modules"):

```markdown
* **fsspec backends stay lazy.** Never import `s3fs`, `gcsfs`, or `adlfs`
  directly from CLI modules. fsspec loads backends on demand when a UPath
  with the matching protocol is first accessed, which is exactly what we
  want — core install stays lightweight and users pay for only the backends
  they use.
```

- [ ] **Step 2: Extend `testing-and-ci.md` §1**

Append to §1 ("Test Infrastructure & Execution"):

```markdown
* **Remote URI testing.** Prefer fsspec's built-in `memory://` protocol for
  unit tests that exercise remote-URI behaviour — it requires no external
  credentials and is fast. Use it for `preflight_remote_must_exist`, mount
  skipping, scheme detection, etc.
* **Live-cloud tests are opt-in.** Any test that hits a real S3/GCS/Azure
  endpoint must be gated on an `HIP_CARGO_LIVE_S3`, `HIP_CARGO_LIVE_GCS`, or
  `HIP_CARGO_LIVE_AZURE` environment variable and must be excluded from the
  required CI checks.
```

- [ ] **Step 3: Commit**

```bash
git add .claude/rules/python-standards.md .claude/rules/testing-and-ci.md
git commit -m "docs(rules): document fsspec laziness and memory:// test strategy"
```

---

## Task 17: Regenerate committed cab YAML and roundtrip-verify

**Files:**
- Regenerate: `src/hip_cargo/cabs/*.yml`

- [ ] **Step 1: Regenerate cabs**

Run: `uv run hip-cargo generate-cabs`
Expected: regenerates the cab YAMLs. Since the cab YAML format is unchanged (per the spec), the diff should be empty.

- [ ] **Step 2: Inspect the diff**

Run: `git status -s src/hip_cargo/cabs/ && git diff src/hip_cargo/cabs/`
Expected: no changes. If the diff is non-empty, something in the generation pipeline changed unexpectedly — investigate before continuing.

- [ ] **Step 3: Full roundtrip verification**

Run: `uv run pytest tests/test_roundtrip.py tests/test_end_to_end_comment_preservation.py -v 2>&1 | tail -20`
Expected: all PASS.

- [ ] **Step 4: Commit (only if diff exists)**

If Step 2 produced no diff, skip this step. If there was a diff and it is intentional:

```bash
git add src/hip_cargo/cabs/
git commit -m "chore(cabs): regenerate cab YAML after UPath introduction"
```

---

## Task 18: Final verification — full suite, lint, CLI smoke

**Files:** none

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -v 2>&1 | tail -30`
Expected: all PASS. Record the final count.

- [ ] **Step 2: Lint**

Run: `uv run ruff format . && uv run ruff check . --fix`
Expected: clean.

- [ ] **Step 3: CLI smoke — local path**

Run: `uv run hip-cargo --help`
Expected: help output renders without error.

- [ ] **Step 4: CLI smoke — memory URI**

Run:
```bash
uv run python -c "
import fsspec
fs = fsspec.filesystem('memory')
with fs.open('/smoke.bin', 'wb') as f: f.write(b'hello')
from upath import UPath
u = UPath('memory:///smoke.bin')
assert u.exists() and u.read_bytes() == b'hello'
print('memory:// roundtrip ok')
"
```
Expected: prints `memory:// roundtrip ok`.

- [ ] **Step 5: Verify `preflight_remote_must_exist` via an end-to-end invocation**

This step only applies if an existing test covers it. If not, rely on Task 7's unit coverage and skip.

- [ ] **Step 6: Confirm no stray untracked files**

Run: `git status`
Expected: clean working tree (all intended changes committed; no leftover experiment files).

- [ ] **Step 7: Announce completion**

Work is complete when Steps 1–6 all produced the expected output. If the branch is a feature branch, this is the handoff point for the `superpowers:finishing-a-development-branch` skill.

---

## Out of scope (reminder)

Per the spec, none of the following are in this plan:

- Glob expansion of remote URIs (e.g. `s3://bkt/*.fits` → `list[File]`).
- Caching or prefetch of remote objects.
- Auto-upload of local outputs to object stores.
- Auth flows beyond env + default config dirs (IAM roles, workload identity,
  device login all work natively via the SDK chains — no special-casing).
