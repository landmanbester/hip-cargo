# Stokify Demonstrator Spike — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable `stokify` demonstrator (a standalone sibling repo) that proves the RFC's target shape — a three-step linear pipeline whose hand-written `runtime/` exemplifies transpiler output, streaming live progress through hip-cargo's existing monitoring stack on synthetic data.

**Architecture:** `stokify` is scaffolded via `hip-cargo init` (multi-command mode) at `~/software/stokify`, depending on the **local** hip-cargo `apis` checkout (editable path dependency) so it picks up the unreleased monitoring/progress APIs. Three `core/` functions (`init`/`process`/`image`) take `memory_mode: Literal["greedy","conservative"]`, return synthetic `xr.Dataset`s, and emit `track_progress` events. Hand-written `runtime/{tasks.py,runner.py,cli.py}` chain the steps by Ray ObjectRef (driver never `ray.get`s intermediates) and weave pipeline-level events. A `demo.py` integration script runs the pipeline against a local Ray cluster with `hip-cargo monitor` and asserts the five REST/WS endpoints stream real data.

**Tech Stack:** Python 3.10+, Typer, Ray (`ray[default]>=2.40.0` via `hip-cargo[monitoring]`), xarray + numpy + zarr (synthetic data, under a `[full]` extra), pytest, ruff, bandit.

**Scope guardrails (do NOT):** build the transpiler; build the React frontend; depend on casacore / python-casacore / measurement-set libs; modify the restricted grammar or the §6 exclusions; modify hip-cargo's monitoring code except for genuine bug fixes. Reference doc: `/home/bester/software/hip-cargo/docs/design/transpile-rfc.md` (§12 stages 1, 2, 2.5, 3).

**Two honesty caveats baked into the artifacts (RFC §12 stage 2.5):** (1) the local demo runs steps **in-process** — `tasks.py` carries the per-step container `runtime_env` *shape* as data but does not apply `image_uri` (experimental; validated separately, §11); (2) on a single node the `greedy`/`conservative` distinction is **cosmetic** (plasma vs. a local zarr on the same disk) — the demo proves the contract + event flow, not the disk-bypass performance characteristic.

---

## File Structure

All paths below are inside the **new** repo `~/software/stokify/` unless prefixed with `hip-cargo:`.

**Scaffolded by `hip-cargo init` (then edited):**
- `pyproject.toml` — edited to point `hip-cargo` at the local apis checkout, add the `[full]` extra and dev deps.
- `src/stokify/__init__.py`, `src/stokify/_container_image.py` — as generated.
- `src/stokify/cli/__init__.py` — Typer app; we register `init`/`process`/`image`/`run`.
- `src/stokify/cli/onboard.py`, `src/stokify/core/onboard.py` — generated example; left in place (harmless) until Task 8.
- `tests/test_install.py`, `tests/test_roundtrip.py` — generated; we extend `test_roundtrip.py`.

**Created by this plan:**
- `src/stokify/core/_synth.py` — shared synthetic-data + memory-mode helpers (one responsibility: build/reify/store synthetic datasets). Stand-in for the future `hip_cargo.runtime` memory helpers.
- `src/stokify/core/init.py`, `core/process.py`, `core/image.py` — the three plain-Python step bodies (return `xr.Dataset`, emit progress).
- `src/stokify/cli/init.py`, `cli/process.py`, `cli/image.py` — thin Typer wrappers (`@stimela_cab` + `@stimela_output`), standard native-try / container-fallback shape.
- `src/stokify/cabs/init.yml`, `process.yml`, `image.yml` — generated via `hip-cargo generate-cabs`.
- `src/stokify/runtime/__init__.py`, `runtime/tasks.py`, `runtime/runner.py`, `runtime/cli.py` — the hand-written would-be transpiler output.
- `src/stokify/recipes/stokify.yml` — the restricted-grammar recipe (the transpiler's would-be input).
- `tests/test_memory_modes.py` — unit tests for the core step contract.
- `demo.py` — the end-to-end monitoring demonstration / integration check (the artifact shown to reviewers).
- `DEMONSTRATOR.md` — cross-repo setup + run instructions, plus the documented manual monitoring-wiring steps (reference for the future §9.7 templates).

---

## Task 0: Bootstrap the `stokify` repo

**Files:**
- Create (via tool): the whole `~/software/stokify/` tree
- Modify: `~/software/stokify/pyproject.toml`

- [ ] **Step 1: Confirm the target directory does not exist**

`hip-cargo init` raises if the output dir already exists.

Run: `test ! -e ~/software/stokify && echo OK || echo "EXISTS — stop"`
Expected: `OK`

- [ ] **Step 2: Scaffold via `hip-cargo init` (multi-command mode)**

Run from the hip-cargo checkout (so `uv run` uses the apis-branch hip-cargo):

```bash
cd /home/bester/software/hip-cargo
uv run hip-cargo init \
  --project-name stokify \
  --github-user landmanbester \
  --cli-mode multi \
  --license-type MIT \
  --description "Restricted-subset demonstrator for the hip-cargo transpiler RFC" \
  --project-dir /home/bester/software/stokify
```

Expected: prints "Project created at: …/stokify", runs `uv sync`, `pytest tests/test_install.py` (2 passed), `generate-cabs` for `onboard`, ruff, `git init -b main`, initial commit, `pre-commit install`. (Requires network for `uv sync`.) If `uv sync` fails resolving `hip-cargo>=0.2.0` from PyPI without the apis APIs, that is expected to still succeed here because the scaffold's own code only imports the published surface; we repoint the dependency in Step 4.

- [ ] **Step 3: Verify the generated layout**

Run: `cd /home/bester/software/stokify && ls src/stokify && ls src/stokify/cli src/stokify/core src/stokify/cabs`
Expected: `cli core cabs __init__.py _container_image.py`; `cli/` has `__init__.py onboard.py`; `core/` has `__init__.py onboard.py`; `cabs/` has `__init__.py onboard.yml`.

- [ ] **Step 4: Repoint hip-cargo at the local apis checkout + add extras**

Edit `~/software/stokify/pyproject.toml`. Change the dependency and add a uv source so the unreleased monitoring/progress APIs are available; add the heavy stack under `[full]`; add dev/test deps.

Replace the `dependencies = [...]` block:

```toml
dependencies = [
    "hip-cargo[monitoring]",
]
```

Replace the `[project.optional-dependencies]` block:

```toml
[project.optional-dependencies]
# Heavy scientific stack — needed to RUN the synthetic pipeline natively.
# A real transpiled package keeps these in the per-step container image, not here
# (RFC §9.5). For this in-process local demo we install `.[full]`.
full = [
    "xarray>=2024.1.0",
    "numpy>=1.26",
    "zarr>=2.17,<3",
]
```

Add, immediately after the `[project.optional-dependencies]` block:

```toml
[tool.uv.sources]
hip-cargo = { path = "/home/bester/software/hip-cargo", editable = true }
```

Append to the `[dependency-groups]` `dev = [...]` list these entries (for `demo.py` REST queries and async tests):

```toml
    "httpx>=0.27.0",
    "pytest-asyncio>=0.24.0",
    "bandit>=1.7.9",
```

- [ ] **Step 5: Re-sync with the full extra and verify the apis APIs import**

Run:
```bash
cd /home/bester/software/stokify
uv sync --group dev --extra full
uv run python -c "from hip_cargo.utils.progress_context import track_progress; from hip_cargo.monitoring.ray_backend import get_or_create_aggregator, RayProgressBackend; print('apis APIs OK')"
```
Expected: `apis APIs OK`

- [ ] **Step 6: Commit**

```bash
cd /home/bester/software/stokify
git add -A
git commit -m "chore: repoint hip-cargo at local apis checkout, add full/dev extras"
```

---

## Task 1: Synthetic data + memory-mode helpers (`core/_synth.py`)

**Files:**
- Create: `src/stokify/core/_synth.py`
- Test: `tests/test_memory_modes.py`

This module is the one place that knows how to (a) build a synthetic `xr.Dataset` of realistic shape, (b) `reify` it to NumPy-backing (greedy), and (c) `store` it to a zarr and reopen lazily without dask (conservative). The three step bodies call these so the greedy/conservative branch is uniform and one line each.

- [ ] **Step 1: Write the failing test**

Create `tests/test_memory_modes.py`:

```python
"""Contract tests for the synthetic-data + memory-mode helpers."""

import tempfile
from pathlib import Path

import numpy as np
import xarray as xr

from stokify.core._synth import make_synth_dataset, reify_greedy, store_conservative


def test_make_synth_dataset_shape():
    ds = make_synth_dataset(n_band=4, n_stokes=2, n_x=64, n_y=64, seed=0)
    assert isinstance(ds, xr.Dataset)
    assert ds["vis"].shape == (4, 2, 64, 64)
    assert set(ds.dims) == {"band", "stokes", "x", "y"}


def test_reify_greedy_is_numpy_backed():
    ds = make_synth_dataset(n_band=2, n_stokes=2, n_x=32, n_y=32, seed=1)
    out = reify_greedy(ds)
    # A reified dataset holds concrete numpy arrays (no lazy/dask backing).
    assert isinstance(out["vis"].data, np.ndarray)


def test_store_conservative_roundtrips_without_dask():
    ds = make_synth_dataset(n_band=2, n_stokes=2, n_x=32, n_y=32, seed=2)
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "step.zarr"
        out = store_conservative(ds, store)
        assert isinstance(out, xr.Dataset)
        # Opened without dask: chunks is an empty mapping, not dask chunking.
        assert out.chunks == {} or out.chunks is None
        # Values still resolve (deferred read from the store).
        assert np.allclose(out["vis"].values, ds["vis"].values)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd /home/bester/software/stokify && uv run --extra full pytest tests/test_memory_modes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stokify.core._synth'`

- [ ] **Step 3: Implement `core/_synth.py`**

Create `src/stokify/core/_synth.py`:

```python
"""Synthetic-data and memory-mode helpers for the stokify demonstrator.

These stand in for what `hip_cargo.runtime` would eventually provide (RFC §9.4).
`make_synth_dataset` fabricates a small dataset shaped like a real imaging
intermediate; `reify_greedy` forces NumPy backing (plasma-resident handoff);
`store_conservative` persists to a zarr and reopens it lazily WITHOUT dask, so
the serialized object is a thin store-backed descriptor (RFC §5.5 / §9.1).
"""

from pathlib import Path

import numpy as np
import xarray as xr


def make_synth_dataset(
    n_band: int = 4,
    n_stokes: int = 2,
    n_x: int = 256,
    n_y: int = 256,
    seed: int = 0,
) -> xr.Dataset:
    """Build a synthetic, NumPy-backed dataset shaped like an imaging intermediate."""
    rng = np.random.default_rng(seed)
    vis = rng.standard_normal((n_band, n_stokes, n_x, n_y)).astype("float32")
    return xr.Dataset(
        data_vars={"vis": (("band", "stokes", "x", "y"), vis)},
        coords={
            "band": np.arange(n_band),
            "stokes": ["I", "Q", "U", "V"][:n_stokes],
            "x": np.arange(n_x),
            "y": np.arange(n_y),
        },
        attrs={"synthetic": 1},
    )


def reify_greedy(ds: xr.Dataset) -> xr.Dataset:
    """Greedy mode: force every array to concrete NumPy backing (plasma-resident)."""
    return ds.load()


def store_conservative(ds: xr.Dataset, store: Path) -> xr.Dataset:
    """Conservative mode: persist to a zarr and reopen lazily WITHOUT dask.

    The returned dataset is a thin, store-backed handle; reads are deferred to
    the store on access. This *defers* disk I/O rather than eliminating it.
    """
    store = Path(store)
    ds.to_zarr(store, mode="w")
    return xr.open_zarr(store, chunks=None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/bester/software/stokify && uv run --extra full pytest tests/test_memory_modes.py -v`
Expected: 3 passed

- [ ] **Step 5: Lint**

Run: `cd /home/bester/software/stokify && uv run ruff format . && uv run ruff check . --fix`
Expected: no errors (files reformatted/clean)

- [ ] **Step 6: Commit**

```bash
cd /home/bester/software/stokify
git add src/stokify/core/_synth.py tests/test_memory_modes.py
git commit -m "feat: synthetic-data and greedy/conservative memory helpers"
```

---

## Task 2: The three core step bodies (`core/init.py`, `core/process.py`, `core/image.py`)

**Files:**
- Create: `src/stokify/core/init.py`, `src/stokify/core/process.py`, `src/stokify/core/image.py`
- Test: `tests/test_core_steps.py`

Plain-Python functions (no decorators, no Typer). Each takes `memory_mode`, an optional `job_id` (so events group across the pipeline), a `work_dir` for conservative-mode persistence, and returns an `xr.Dataset`. Each wraps its loop in `track_progress` so it emits `STARTED → PROGRESS×N (+METRIC) → COMPLETED` through whatever backend is active (NullBackend if none).

These are the **in-memory** functions (`init_inmem` / `process_inmem` / `image_inmem`) that the hand-written runner imports and chains by ObjectRef (Task 5). They are named with the `_inmem` suffix so that Task 3 can add thin `init`/`process`/`image` cab-entry wrappers *in the same modules* — the round-trip convention (verified: `cli/<name>.py`→`<name>`→`command: <pkg>.core.<name>.<name>`) forces the cab-entry function to be named `<name>` and to take only CLI-expressible params, which an `xr.Dataset` is not.

- [ ] **Step 1: Write the failing test**

Create `tests/test_core_steps.py`:

```python
"""Tests for the three stokify core step bodies and their progress wiring."""

import tempfile

import xarray as xr

from hip_cargo.utils.progress import EventType, NullBackend, set_backend
from stokify.core.image import image_inmem
from stokify.core.init import init_inmem
from stokify.core.process import process_inmem


class _Recorder:
    """A ProgressBackend that records every emitted event."""

    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)

    def close(self):
        pass


def _run(fn, **kwargs):
    rec = _Recorder()
    set_backend(rec)
    try:
        out = fn(**kwargs)
    finally:
        set_backend(NullBackend())
    return out, rec.events


def test_init_returns_dataset_and_emits_lifecycle():
    with tempfile.TemporaryDirectory() as tmp:
        out, events = _run(
            init_inmem,
            memory_mode="greedy",
            job_id="J",
            n_band=2,
            n_stokes=2,
            n_x=32,
            n_y=32,
            n_steps=3,
            sleep=0.0,
            work_dir=tmp,
        )
    assert isinstance(out, xr.Dataset)
    assert out["vis"].shape == (2, 2, 32, 32)
    types = [e.event_type for e in events]
    assert types[0] == EventType.STARTED
    assert types[-1] == EventType.COMPLETED
    assert types.count(EventType.PROGRESS) == 3
    assert all(e.job_id == "J" and e.worker_name == "init" for e in events)


def test_process_emits_residual_and_convergence_metrics():
    with tempfile.TemporaryDirectory() as tmp:
        ds = init_inmem(memory_mode="greedy", job_id="J", n_band=2, n_stokes=2,
                  n_x=32, n_y=32, n_steps=1, sleep=0.0, work_dir=tmp)
        out, events = _run(
            process_inmem, dataset=ds, memory_mode="greedy", job_id="J",
            n_iterations=5, sleep=0.0, work_dir=tmp,
        )
    assert isinstance(out, xr.Dataset)
    metric_names = {e.metric_name for e in events if e.event_type == EventType.METRIC}
    assert {"residual", "convergence"} <= metric_names


def test_image_conservative_returns_store_backed_dataset():
    with tempfile.TemporaryDirectory() as tmp:
        ds = init_inmem(memory_mode="greedy", job_id="J", n_band=2, n_stokes=2,
                  n_x=32, n_y=32, n_steps=1, sleep=0.0, work_dir=tmp)
        out, events = _run(
            image_inmem, dataset=ds, memory_mode="conservative", job_id="J",
            n_iterations=4, sleep=0.0, work_dir=tmp,
        )
    assert isinstance(out, xr.Dataset)
    assert any(e.event_type == EventType.COMPLETED for e in events)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd /home/bester/software/stokify && uv run --extra full pytest tests/test_core_steps.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stokify.core.init'`

- [ ] **Step 3: Implement `core/init.py`**

Create `src/stokify/core/init.py`:

```python
"""Core: read a measurement set (synthetic) -> coherency xr.Dataset.

For the demonstrator this fabricates synthetic data instead of reading a real
measurement set, so the package has no casacore dependency.
"""

import time
from pathlib import Path
from typing import Literal

import xarray as xr

from hip_cargo.utils.progress_context import track_progress
from stokify.core._synth import make_synth_dataset, reify_greedy, store_conservative


def init_inmem(
    memory_mode: Literal["greedy", "conservative"] = "greedy",
    job_id: str | None = None,
    n_band: int = 4,
    n_stokes: int = 2,
    n_x: int = 256,
    n_y: int = 256,
    n_steps: int = 5,
    sleep: float = 0.2,
    work_dir: str = ".stokify_work",
) -> xr.Dataset:
    """Simulate reading a measurement set, returning a coherency dataset.

    Args:
        memory_mode: "greedy" reifies in memory; "conservative" persists to zarr.
        job_id: Pipeline job id so emitted events group with the rest of the run.
        n_band/n_stokes/n_x/n_y: Synthetic dataset shape.
        n_steps: Number of simulated read chunks (drives progress events).
        sleep: Per-step sleep to simulate work (0.0 in tests).
        work_dir: Directory for conservative-mode zarr persistence.

    Returns:
        An xr.Dataset of synthetic coherencies (NumPy-backed in greedy mode,
        store-backed in conservative mode).
    """
    with track_progress("init", total_steps=n_steps, job_id=job_id, pipeline_run_id=job_id) as t:
        for i in range(n_steps):
            time.sleep(sleep)
            t.step(message=f"reading chunk {i + 1}/{n_steps}")
            t.metric("rows_read", float((i + 1) * 1000))
        ds = make_synth_dataset(n_band=n_band, n_stokes=n_stokes, n_x=n_x, n_y=n_y, seed=0)

    if memory_mode == "greedy":
        return reify_greedy(ds)
    return store_conservative(ds, Path(work_dir) / "init.zarr")
```

- [ ] **Step 4: Implement `core/process.py`**

Create `src/stokify/core/process.py`:

```python
"""Core: transform coherencies -> image-ready Stokes visibilities (synthetic)."""

import time
from pathlib import Path
from typing import Literal

import xarray as xr

from hip_cargo.utils.progress_context import track_progress
from stokify.core._synth import reify_greedy, store_conservative


def process_inmem(
    dataset: xr.Dataset,
    memory_mode: Literal["greedy", "conservative"] = "greedy",
    job_id: str | None = None,
    n_iterations: int = 10,
    sleep: float = 0.2,
    work_dir: str = ".stokify_work",
) -> xr.Dataset:
    """Apply a synthetic coherency->Stokes transform with iterative refinement.

    Emits a falling `residual` and a rising `convergence` metric per iteration.
    """
    with track_progress("process", total_steps=n_iterations, job_id=job_id, pipeline_run_id=job_id) as t:
        stokes = dataset["vis"] * 2.0  # stand-in coherency -> Stokes transform
        for i in range(n_iterations):
            time.sleep(sleep)
            stokes = stokes - stokes / (i + 2)  # cheap synthetic refinement
            t.step(message=f"iteration {i + 1}/{n_iterations}")
            t.metric("residual", 1.0 / (i + 1))
            t.metric("convergence", 1.0 - 1.0 / (i + 1))
        out = dataset.copy()
        out["vis"] = stokes

    if memory_mode == "greedy":
        return reify_greedy(out)
    return store_conservative(out, Path(work_dir) / "process.zarr")
```

- [ ] **Step 5: Implement `core/image.py`**

Create `src/stokify/core/image.py`:

```python
"""Core: grid and image the Stokes visibilities (synthetic)."""

import time
from pathlib import Path
from typing import Literal

import numpy as np
import xarray as xr

from hip_cargo.utils.progress_context import track_progress
from stokify.core._synth import reify_greedy, store_conservative


def image_inmem(
    dataset: xr.Dataset,
    memory_mode: Literal["greedy", "conservative"] = "conservative",
    job_id: str | None = None,
    n_iterations: int = 8,
    sleep: float = 0.2,
    work_dir: str = ".stokify_work",
) -> xr.Dataset:
    """Synthetic gridding + imaging; emits `rms` (falling) and `peak` (rising)."""
    with track_progress("image", total_steps=n_iterations, job_id=job_id, pipeline_run_id=job_id) as t:
        img = dataset["vis"]
        for i in range(n_iterations):
            time.sleep(sleep)
            img = img + img / (i + 2)  # cheap synthetic deconvolution-like update
            t.step(message=f"major cycle {i + 1}/{n_iterations}")
            t.metric("rms", 1.0 / (i + 1))
            t.metric("peak", float(np.abs(img.values).max()))
        out = dataset.copy()
        out["vis"] = img

    if memory_mode == "greedy":
        return reify_greedy(out)
    return store_conservative(out, Path(work_dir) / "image.zarr")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /home/bester/software/stokify && uv run --extra full pytest tests/test_core_steps.py -v`
Expected: 3 passed

- [ ] **Step 7: Lint**

Run: `cd /home/bester/software/stokify && uv run ruff format . && uv run ruff check . --fix`
Expected: clean

- [ ] **Step 8: Commit**

```bash
cd /home/bester/software/stokify
git add src/stokify/core/init.py src/stokify/core/process.py src/stokify/core/image.py tests/test_core_steps.py
git commit -m "feat: synthetic init/process/image core steps with progress events"
```

---

## Task 3: Cab-entry functions + CLI wrappers + generated cabs (round-trippable)

**Files:**
- Modify: `src/stokify/core/init.py`, `core/process.py`, `core/image.py` (append a cab-entry function each)
- Create: `src/stokify/cli/init.py`, `cli/process.py`, `cli/image.py`
- Modify: `src/stokify/cli/__init__.py` (register the three commands)
- Create (generated): `src/stokify/cabs/init.yml`, `cabs/process.yml`, `cabs/image.yml`
- Modify: `tests/test_roundtrip.py` (add a case per command)

**Design boundary (document this — it is the RFC's principal gap made concrete):** today's cab schema cannot express an *in-memory `xr.Dataset` (ObjectRef) input* (RFC §9.1, the principal proposed change). So each cab describes only its step's tunable **scalar** parameters, and its `command:` points at a small disk-persisting entry (`init`/`process`/`image`) that builds its upstream prefix in-process and writes a zarr. The hand-written runner (Task 5) instead imports the in-memory `*_inmem` variants and chains them by ObjectRef — no recomputation, no disk round-trip. A future transpiler + the §9.1 marker collapses the two: the cab would carry the ObjectRef input and the runner would import the cab's `command:` directly.

- [ ] **Step 1: Append the `init` cab-entry to `core/init.py`**

Append to `src/stokify/core/init.py` (no new imports needed — `Path`, `Literal`, `xr` already imported):

```python
def init(
    output: str,
    memory_mode: Literal["greedy", "conservative"] = "greedy",
    n_band: int = 4,
    n_stokes: int = 2,
    n_x: int = 256,
    n_y: int = 256,
    n_steps: int = 5,
) -> None:
    """Standalone step entry (the cab `command:`): run init and persist the dataset to `output`.

    The pipeline runner uses `init_inmem` for in-memory ObjectRef handoff; this
    disk-persisting entry exists so the step is a valid, round-trippable cab
    command with today's hip-cargo. A future transpiler + the RFC §9.1 ObjectRef
    marker would let the cab express the in-memory dataset directly and drop this shim.
    """
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    ds = init_inmem(
        memory_mode=memory_mode,
        n_band=n_band,
        n_stokes=n_stokes,
        n_x=n_x,
        n_y=n_y,
        n_steps=n_steps,
        work_dir=str(out.parent),
    )
    ds.to_zarr(out, mode="w")
    print(f"init -> {out}")
```

- [ ] **Step 2: Append the `process` cab-entry to `core/process.py`**

First add this import near the top of `src/stokify/core/process.py` (under the existing imports):

```python
from stokify.core.init import init_inmem
```

Then append:

```python
def process(
    output: str,
    memory_mode: Literal["greedy", "conservative"] = "greedy",
    n_iterations: int = 10,
) -> None:
    """Standalone step entry (the cab `command:`): build the upstream prefix
    in-process, run the process step, and persist the result to `output`."""
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    ds = init_inmem(memory_mode="greedy", work_dir=str(out.parent))
    out_ds = process_inmem(ds, memory_mode=memory_mode, n_iterations=n_iterations, work_dir=str(out.parent))
    out_ds.to_zarr(out, mode="w")
    print(f"process -> {out}")
```

- [ ] **Step 3: Append the `image` cab-entry to `core/image.py`**

First add these imports near the top of `src/stokify/core/image.py`:

```python
from stokify.core.init import init_inmem
from stokify.core.process import process_inmem
```

Then append:

```python
def image(
    output: str,
    memory_mode: Literal["greedy", "conservative"] = "conservative",
    n_iterations: int = 8,
) -> None:
    """Standalone step entry (the cab `command:`): build the upstream prefix
    (init -> process) in-process, run the image step, and persist the result to `output`."""
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    ds = init_inmem(memory_mode="greedy", work_dir=str(out.parent))
    ds = process_inmem(ds, memory_mode="greedy", work_dir=str(out.parent))
    out_ds = image_inmem(ds, memory_mode=memory_mode, n_iterations=n_iterations, work_dir=str(out.parent))
    out_ds.to_zarr(out, mode="w")
    print(f"image -> {out}")
```

- [ ] **Step 4: Verify the cab-entries import and run**

Run:
```bash
cd /home/bester/software/stokify
uv run --extra full python -c "from stokify.core.init import init; from stokify.core.process import process; from stokify.core.image import image; print('cab-entries import OK')"
```
Expected: `cab-entries import OK`

- [ ] **Step 5: Write `cli/init.py`**

Modeled exactly on `hip-cargo`'s `cli/generate_function.py`. The signature + decorators are what `generate-cabs` reads (the body is irrelevant to cab generation — `command:` is derived from the file path + function name). Step 10 regenerates this body canonically, so byte-exactness is guaranteed there; this hand-written body matches the canonical shape anyway.

Create `src/stokify/cli/init.py`:

```python
from pathlib import Path
from typing import Annotated, Literal, NewType

import typer

from hip_cargo import StimelaMeta, parse_upath, stimela_cab, stimela_output

Directory = NewType("Directory", Path)


@stimela_cab(
    name="init",
    info="Read a measurement set (synthetic) into a coherency dataset.",
)
@stimela_output(
    dtype="Directory",
    name="output",
    info="Zarr store of synthetic coherencies.",
    required=True,
    policies={"positional": True},
    metadata={"rich_help_panel": "Outputs"},
)
def init(
    output: Annotated[
        Directory,
        typer.Option(
            ...,
            parser=parse_upath,
            help="Zarr store of synthetic coherencies.",
            rich_help_panel="Outputs",
        ),
    ],
    memory_mode: Annotated[
        Literal["greedy", "conservative"],
        typer.Option(
            help="In-memory reify (greedy) or store-backed (conservative).",
            rich_help_panel="Inputs",
        ),
    ] = "greedy",
    n_band: Annotated[
        int,
        typer.Option(
            help="Number of frequency bands.",
            rich_help_panel="Inputs",
        ),
    ] = 4,
    n_stokes: Annotated[
        int,
        typer.Option(
            help="Number of Stokes parameters.",
            rich_help_panel="Inputs",
        ),
    ] = 2,
    n_x: Annotated[
        int,
        typer.Option(
            help="Image x size.",
            rich_help_panel="Inputs",
        ),
    ] = 256,
    n_y: Annotated[
        int,
        typer.Option(
            help="Image y size.",
            rich_help_panel="Inputs",
        ),
    ] = 256,
    n_steps: Annotated[
        int,
        typer.Option(
            help="Number of simulated read chunks.",
            rich_help_panel="Inputs",
        ),
    ] = 5,
    backend: Annotated[
        Literal["auto", "native", "apptainer", "singularity", "docker", "podman"],
        typer.Option(
            help="Execution backend.",
        ),
        StimelaMeta(
            skip=True,
        ),
    ] = "auto",
    always_pull_images: Annotated[
        bool,
        typer.Option(
            help="Always pull container images, even if cached locally.",
        ),
        StimelaMeta(
            skip=True,
        ),
    ] = False,
):
    """
    Read a measurement set (synthetic) into a coherency dataset.
    """
    if backend == "native" or backend == "auto":
        try:
            from hip_cargo.utils.runner import preflight_remote_must_exist  # noqa: E402

            preflight_remote_must_exist(
                init,
                dict(
                    output=output,
                    memory_mode=memory_mode,
                    n_band=n_band,
                    n_stokes=n_stokes,
                    n_x=n_x,
                    n_y=n_y,
                    n_steps=n_steps,
                ),
            )

            from stokify.core.init import init as init_core  # noqa: E402

            init_core(
                output,
                memory_mode=memory_mode,
                n_band=n_band,
                n_stokes=n_stokes,
                n_x=n_x,
                n_y=n_y,
                n_steps=n_steps,
            )
            return
        except ImportError:
            if backend == "native":
                raise

    from hip_cargo.utils.config import get_container_image  # noqa: E402
    from hip_cargo.utils.runner import run_in_container  # noqa: E402

    image = get_container_image("stokify")
    if image is None:
        raise RuntimeError("No Container URL in stokify metadata.")

    run_in_container(
        init,
        dict(
            output=output,
            memory_mode=memory_mode,
            n_band=n_band,
            n_stokes=n_stokes,
            n_x=n_x,
            n_y=n_y,
            n_steps=n_steps,
        ),
        image=image,
        backend=backend,
        always_pull_images=always_pull_images,
    )
```

- [ ] **Step 6: Write `cli/process.py`**

Create `src/stokify/cli/process.py`:

```python
from pathlib import Path
from typing import Annotated, Literal, NewType

import typer

from hip_cargo import StimelaMeta, parse_upath, stimela_cab, stimela_output

Directory = NewType("Directory", Path)


@stimela_cab(
    name="process",
    info="Transform coherencies into image-ready Stokes visibilities.",
)
@stimela_output(
    dtype="Directory",
    name="output",
    info="Zarr store of Stokes visibilities.",
    required=True,
    policies={"positional": True},
    metadata={"rich_help_panel": "Outputs"},
)
def process(
    output: Annotated[
        Directory,
        typer.Option(
            ...,
            parser=parse_upath,
            help="Zarr store of Stokes visibilities.",
            rich_help_panel="Outputs",
        ),
    ],
    memory_mode: Annotated[
        Literal["greedy", "conservative"],
        typer.Option(
            help="In-memory reify (greedy) or store-backed (conservative).",
            rich_help_panel="Inputs",
        ),
    ] = "greedy",
    n_iterations: Annotated[
        int,
        typer.Option(
            help="Number of refinement iterations.",
            rich_help_panel="Inputs",
        ),
    ] = 10,
    backend: Annotated[
        Literal["auto", "native", "apptainer", "singularity", "docker", "podman"],
        typer.Option(
            help="Execution backend.",
        ),
        StimelaMeta(
            skip=True,
        ),
    ] = "auto",
    always_pull_images: Annotated[
        bool,
        typer.Option(
            help="Always pull container images, even if cached locally.",
        ),
        StimelaMeta(
            skip=True,
        ),
    ] = False,
):
    """
    Transform coherencies into image-ready Stokes visibilities.
    """
    if backend == "native" or backend == "auto":
        try:
            from hip_cargo.utils.runner import preflight_remote_must_exist  # noqa: E402

            preflight_remote_must_exist(
                process,
                dict(
                    output=output,
                    memory_mode=memory_mode,
                    n_iterations=n_iterations,
                ),
            )

            from stokify.core.process import process as process_core  # noqa: E402

            process_core(
                output,
                memory_mode=memory_mode,
                n_iterations=n_iterations,
            )
            return
        except ImportError:
            if backend == "native":
                raise

    from hip_cargo.utils.config import get_container_image  # noqa: E402
    from hip_cargo.utils.runner import run_in_container  # noqa: E402

    image = get_container_image("stokify")
    if image is None:
        raise RuntimeError("No Container URL in stokify metadata.")

    run_in_container(
        process,
        dict(
            output=output,
            memory_mode=memory_mode,
            n_iterations=n_iterations,
        ),
        image=image,
        backend=backend,
        always_pull_images=always_pull_images,
    )
```

- [ ] **Step 7: Write `cli/image.py`**

Create `src/stokify/cli/image.py` (identical shape to `process.py`, with `name="image"`, the imaging info strings, and `n_iterations=8`):

```python
from pathlib import Path
from typing import Annotated, Literal, NewType

import typer

from hip_cargo import StimelaMeta, parse_upath, stimela_cab, stimela_output

Directory = NewType("Directory", Path)


@stimela_cab(
    name="image",
    info="Grid and image the Stokes visibilities.",
)
@stimela_output(
    dtype="Directory",
    name="output",
    info="Zarr store of the output image cube.",
    required=True,
    policies={"positional": True},
    metadata={"rich_help_panel": "Outputs"},
)
def image(
    output: Annotated[
        Directory,
        typer.Option(
            ...,
            parser=parse_upath,
            help="Zarr store of the output image cube.",
            rich_help_panel="Outputs",
        ),
    ],
    memory_mode: Annotated[
        Literal["greedy", "conservative"],
        typer.Option(
            help="In-memory reify (greedy) or store-backed (conservative).",
            rich_help_panel="Inputs",
        ),
    ] = "conservative",
    n_iterations: Annotated[
        int,
        typer.Option(
            help="Number of major cycles.",
            rich_help_panel="Inputs",
        ),
    ] = 8,
    backend: Annotated[
        Literal["auto", "native", "apptainer", "singularity", "docker", "podman"],
        typer.Option(
            help="Execution backend.",
        ),
        StimelaMeta(
            skip=True,
        ),
    ] = "auto",
    always_pull_images: Annotated[
        bool,
        typer.Option(
            help="Always pull container images, even if cached locally.",
        ),
        StimelaMeta(
            skip=True,
        ),
    ] = False,
):
    """
    Grid and image the Stokes visibilities.
    """
    if backend == "native" or backend == "auto":
        try:
            from hip_cargo.utils.runner import preflight_remote_must_exist  # noqa: E402

            preflight_remote_must_exist(
                image,
                dict(
                    output=output,
                    memory_mode=memory_mode,
                    n_iterations=n_iterations,
                ),
            )

            from stokify.core.image import image as image_core  # noqa: E402

            image_core(
                output,
                memory_mode=memory_mode,
                n_iterations=n_iterations,
            )
            return
        except ImportError:
            if backend == "native":
                raise

    from hip_cargo.utils.config import get_container_image  # noqa: E402
    from hip_cargo.utils.runner import run_in_container  # noqa: E402

    image_uri = get_container_image("stokify")
    if image_uri is None:
        raise RuntimeError("No Container URL in stokify metadata.")

    run_in_container(
        image,
        dict(
            output=output,
            memory_mode=memory_mode,
            n_iterations=n_iterations,
        ),
        image=image_uri,
        backend=backend,
        always_pull_images=always_pull_images,
    )
```

> Note: in `image.py` the container-image local variable is named `image_uri` (not `image`) to avoid shadowing the `image` command function. If Step 10's canonical regeneration names it `image` instead, adopt the regenerated version — Step 10 is the source of truth for byte-identical round-trip.

- [ ] **Step 8: Register the three commands in `cli/__init__.py`**

Edit `src/stokify/cli/__init__.py`. After the existing onboard registration block (`app.command(name="onboard")(onboard)`), add:

```python
from stokify.cli.image import image  # noqa: E402
from stokify.cli.init import init  # noqa: E402
from stokify.cli.process import process  # noqa: E402

app.command(name="init")(init)
app.command(name="process")(process)
app.command(name="image")(image)
```

- [ ] **Step 9: Verify the CLI builds**

Run: `cd /home/bester/software/stokify && uv run stokify --help`
Expected: help text listing commands `onboard`, `init`, `process`, `image`.

Run: `uv run stokify init --help`
Expected: shows `--output` (Outputs panel), `--memory-mode`, `--n-band`, …, but NOT `--backend`/`--always-pull-images` … actually `--backend`/`--always-pull-images` DO appear in `--help` (they are skipped only from the cab, not the CLI).

- [ ] **Step 10: Generate cabs for the three commands**

Run from the repo root:
```bash
cd /home/bester/software/stokify
uv run hip-cargo generate-cabs --module src/stokify/cli/init.py --output-dir src/stokify/cabs/
uv run hip-cargo generate-cabs --module src/stokify/cli/process.py --output-dir src/stokify/cabs/
uv run hip-cargo generate-cabs --module src/stokify/cli/image.py --output-dir src/stokify/cabs/
```
Expected: writes `src/stokify/cabs/init.yml`, `process.yml`, `image.yml`. Inspect one:

Run: `cat src/stokify/cabs/init.yml`
Expected (shape): `flavour: python`, `command: stokify.core.init.init`, `image: ghcr.io/landmanbester/stokify:latest`, an `inputs:` block with `memory-mode` (with `choices`), `n-band`/`n-stokes`/`n-x`/`n-y`/`n-steps`, and an `outputs:` block with `output` (`dtype: Directory`, `required: true`, positional). No `backend`/`always-pull-images`.

- [ ] **Step 11: Canonicalize the CLI modules from their cabs (guarantees round-trip)**

Regenerate each CLI from its cab and overwrite the hand-written file. After this the CLI files are canonical by construction, so the round-trip test is exact.

```bash
cd /home/bester/software/stokify
uv run hip-cargo generate-function --cab-file src/stokify/cabs/init.yml --output-file src/stokify/cli/init.py --config-file pyproject.toml
uv run hip-cargo generate-function --cab-file src/stokify/cabs/process.yml --output-file src/stokify/cli/process.py --config-file pyproject.toml
uv run hip-cargo generate-function --cab-file src/stokify/cabs/image.yml --output-file src/stokify/cli/image.py --config-file pyproject.toml
```
Expected: each prints "Generated function written to: …". Re-run `uv run stokify --help` to confirm the regenerated modules still import and register.

- [ ] **Step 12: Extend the round-trip test**

Edit `tests/test_roundtrip.py`. After `test_roundtrip_onboard`, add:

```python
def test_roundtrip_init() -> None:
    """The init command must round-trip cleanly through a cab."""
    _assert_roundtrip("init")


def test_roundtrip_process() -> None:
    """The process command must round-trip cleanly through a cab."""
    _assert_roundtrip("process")


def test_roundtrip_image() -> None:
    """The image command must round-trip cleanly through a cab."""
    _assert_roundtrip("image")
```

- [ ] **Step 13: Run the round-trip tests**

Run: `cd /home/bester/software/stokify && uv run --extra full pytest tests/test_roundtrip.py -v`
Expected: 4 passed (`onboard`, `init`, `process`, `image`).

- [ ] **Step 14: Lint**

Run: `cd /home/bester/software/stokify && uv run ruff format . && uv run ruff check . --fix`
Expected: clean.

- [ ] **Step 15: Commit**

```bash
cd /home/bester/software/stokify
git add -A
git commit -m "feat: init/process/image cab-entry functions, CLI wrappers, and cabs"
```

---

## Task 4: The restricted-grammar recipe (`recipes/stokify.yml`)

**Files:**
- Create: `src/stokify/recipes/__init__.py`, `src/stokify/recipes/stokify.yml`
- Test: `tests/test_recipe.py`

This recipe is the artifact a future `hip-cargo transpile` would *consume*; the hand-written `runtime/` (Tasks 5–7) is what it would *emit*. It uses only the restricted grammar (RFC §6). The test asserts the existing `monitoring/recipe_parser.py` ingests it into a linear 3-step DAG with all three cab schemas resolved — i.e. the recipe is well-formed against the infrastructure that already exists.

- [ ] **Step 1: Create the recipes package marker**

Create `src/stokify/recipes/__init__.py`:

```python
"""Stimela-style recipes for stokify (restricted-subset demonstrator)."""
```

- [ ] **Step 2: Write the recipe**

Create `src/stokify/recipes/stokify.yml`:

```yaml
# stokify — restricted-subset demonstrator recipe.
#
# This is the artifact a future `hip-cargo transpile` would CONSUME. It uses
# only the restricted grammar (RFC §6): `_include` cab references, `=recipe.x`
# namespace references, and `{recipe.x}` f-string interpolation. There is NO
# `=IF`, `=IFSET`, arithmetic, `=GLOB`, alias broadcast, `assign_based_on`,
# preamble/epilogue, wrangler, or `opts` runtime namespace anywhere in it.
#
# The hand-written runtime/{tasks,runner,cli}.py are what the transpiler WOULD
# emit from this recipe; a reviewer can compare the two and see the mapping is
# mechanical.

_include:
  - (stokify.cabs)init.yml
  - (stokify.cabs)process.yml
  - (stokify.cabs)image.yml

stokify:
  info: Linear Stokes imaging demonstrator (init -> process -> image).
  inputs:
    output-dir:
      dtype: Directory
      info: Directory for per-step zarr outputs.
      required: true
    memory-mode:
      dtype: str
      info: greedy (plasma-resident) or conservative (store-backed).
      default: greedy
  steps:
    init:
      cab: init
      params:
        output: "{recipe.output-dir}/init.zarr"
        memory-mode: =recipe.memory-mode
    process:
      cab: process
      params:
        output: "{recipe.output-dir}/process.zarr"
        memory-mode: =recipe.memory-mode
    image:
      cab: image
      params:
        output: "{recipe.output-dir}/image.zarr"
        memory-mode: =recipe.memory-mode
```

- [ ] **Step 3: Write the failing test**

Create `tests/test_recipe.py`:

```python
"""The restricted recipe must parse to a linear 3-step DAG with resolved cabs."""

from hip_cargo.monitoring.recipe_parser import parse_recipe

RECIPE = "src/stokify/recipes/stokify.yml"


def test_recipe_parses_to_linear_dag():
    dag = parse_recipe(RECIPE)
    assert dag.step_names() == ["init", "process", "image"]
    assert dag.edges == [("init", "process"), ("process", "image")]


def test_recipe_resolves_all_cab_schemas():
    dag = parse_recipe(RECIPE)
    assert len(dag.cab_schemas) == 3
    commands = {c.command for c in dag.cab_schemas.values()}
    assert commands == {
        "stokify.core.init.init",
        "stokify.core.process.process",
        "stokify.core.image.image",
    }
```

- [ ] **Step 4: Run the test**

Run: `cd /home/bester/software/stokify && uv run --extra full pytest tests/test_recipe.py -v`
Expected: 2 passed. (If `dag.edges` are dicts rather than tuples on this branch, adjust the assertion to match the actual `RecipeDAG.edges` shape — verify with `python -c "from hip_cargo.monitoring.recipe_parser import parse_recipe; print(parse_recipe('src/stokify/recipes/stokify.yml').edges)"`.)

- [ ] **Step 5: Lint and commit**

```bash
cd /home/bester/software/stokify
uv run ruff format . && uv run ruff check . --fix
git add -A
git commit -m "feat: restricted-grammar recipe + parser conformance test"
```

---

## Task 5: `runtime/tasks.py` — the `@ray.remote` task wrappers

**Files:**
- Create: `src/stokify/runtime/__init__.py`, `src/stokify/runtime/tasks.py`
- Test: `tests/test_tasks.py`

This is the first of the three hand-written "would-be transpiler output" modules. One `@ray.remote` task per step, each lazy-importing its in-memory core (`*_inmem`) **inside the task body** so the heavy stack lives in the worker, and each wiring the monitoring backend inside the worker process when `monitor=True`.

- [ ] **Step 1: Create the runtime package marker**

Create `src/stokify/runtime/__init__.py`:

```python
"""Hand-written exemplar of `hip-cargo transpile` output for the stokify recipe.

tasks.py / runner.py / cli.py here are what the transpiler WOULD emit from
recipes/stokify.yml. They are plain, mechanical Python by design (RFC §12).
"""
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_tasks.py`:

```python
"""Structural checks on the hand-written Ray task wrappers."""

import stokify.runtime.tasks as t


def test_runtime_env_constants_have_container_shape():
    for env in (t.INIT_RUNTIME_ENV, t.PROCESS_RUNTIME_ENV, t.IMAGE_RUNTIME_ENV):
        assert "image_uri" in env
        assert "env_vars" in env
        assert "run_options" in env


def test_tasks_are_ray_remote():
    for task in (t.init_task, t.process_task, t.image_task):
        assert hasattr(task, "remote")
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd /home/bester/software/stokify && uv run --extra full pytest tests/test_tasks.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stokify.runtime.tasks'`

- [ ] **Step 4: Implement `runtime/tasks.py`**

Create `src/stokify/runtime/tasks.py`:

```python
"""Ray task wrappers for the stokify pipeline (hand-written transpiler output).

One ``@ray.remote`` task per step. Each lazily imports its in-memory core
function (``*_inmem``) INSIDE the task body, so the heavy science stack lives in
the worker (or, in production, the per-step container image), never on the
driver (RFC §5.2-§5.3).

CONTAINER runtime_env — IMPORTANT (RFC §12 stage 2.5 honesty caveat):
The ``*_RUNTIME_ENV`` dicts below are the per-step container specs a transpiler
emits onto each decorator as ``@ray.remote(runtime_env=<STEP>_RUNTIME_ENV, ...)``.
They are kept here as DATA and deliberately NOT applied, so this spike runs
in-process on a local Ray cluster. Wiring them onto the decorators and
validating per-task ``image_uri`` (experimental upstream) is a SEPARATE
milestone (RFC §11). The per-step CPU resources ARE applied — they work locally
and are part of the transpiler's output too. A real ``image`` step would also
request ``num_gpus``; we omit that here so the task schedules on a CPU-only
local cluster.
"""

import ray

# Sourced from the cab `image:` field (stokify._container_image.CONTAINER_IMAGE).
_IMAGE = "ghcr.io/landmanbester/stokify:latest"

INIT_RUNTIME_ENV = {
    "image_uri": _IMAGE,
    "env_vars": {"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"},
    "run_options": ["--cap-drop=ALL", "--shm-size=4g"],
}
PROCESS_RUNTIME_ENV = {
    "image_uri": _IMAGE,
    "env_vars": {"OMP_NUM_THREADS": "2", "MKL_NUM_THREADS": "2"},
    "run_options": ["--cap-drop=ALL", "--shm-size=8g", "-v", "/scratch:/scratch:ro"],
}
IMAGE_RUNTIME_ENV = {
    "image_uri": _IMAGE,
    "env_vars": {"OMP_NUM_THREADS": "4", "MKL_NUM_THREADS": "4"},
    "run_options": ["--cap-drop=ALL", "--shm-size=8g", "-v", "/scratch:/scratch:ro"],
}


# Transpiler emits: @ray.remote(runtime_env=INIT_RUNTIME_ENV, num_cpus=2)
@ray.remote(num_cpus=2)
def init_task(memory_mode, job_id, monitor, n_band, n_stokes, n_x, n_y, n_steps, work_dir):
    if monitor:
        from hip_cargo.monitoring.ray_backend import RayProgressBackend, get_or_create_aggregator
        from hip_cargo.utils.progress import set_backend

        set_backend(RayProgressBackend(get_or_create_aggregator()))
    from stokify.core.init import init_inmem  # imported inside the worker

    return init_inmem(
        memory_mode=memory_mode,
        job_id=job_id,
        n_band=n_band,
        n_stokes=n_stokes,
        n_x=n_x,
        n_y=n_y,
        n_steps=n_steps,
        work_dir=work_dir,
    )


# Transpiler emits: @ray.remote(runtime_env=PROCESS_RUNTIME_ENV, num_cpus=4)
@ray.remote(num_cpus=4)
def process_task(dataset, memory_mode, job_id, monitor, n_iterations, work_dir):
    if monitor:
        from hip_cargo.monitoring.ray_backend import RayProgressBackend, get_or_create_aggregator
        from hip_cargo.utils.progress import set_backend

        set_backend(RayProgressBackend(get_or_create_aggregator()))
    from stokify.core.process import process_inmem

    return process_inmem(
        dataset, memory_mode=memory_mode, job_id=job_id, n_iterations=n_iterations, work_dir=work_dir
    )


# Transpiler emits: @ray.remote(runtime_env=IMAGE_RUNTIME_ENV, num_cpus=4, num_gpus=1)
@ray.remote(num_cpus=4)
def image_task(dataset, memory_mode, job_id, monitor, n_iterations, work_dir):
    if monitor:
        from hip_cargo.monitoring.ray_backend import RayProgressBackend, get_or_create_aggregator
        from hip_cargo.utils.progress import set_backend

        set_backend(RayProgressBackend(get_or_create_aggregator()))
    from stokify.core.image import image_inmem

    return image_inmem(
        dataset, memory_mode=memory_mode, job_id=job_id, n_iterations=n_iterations, work_dir=work_dir
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/bester/software/stokify && uv run --extra full pytest tests/test_tasks.py -v`
Expected: 2 passed

- [ ] **Step 6: Lint and commit**

```bash
cd /home/bester/software/stokify
uv run ruff format . && uv run ruff check . --fix
git add -A
git commit -m "feat: runtime/tasks.py @ray.remote step wrappers (transpiler exemplar)"
```

---

## Task 6: `runtime/runner.py` — ObjectRef chaining + pipeline events

**Files:**
- Create: `src/stokify/runtime/runner.py`
- Test: `tests/test_runner.py`

The runner chains the three tasks by ObjectRef and emits pipeline/step lifecycle events. It **never `ray.get`s an intermediate** — it uses `ray.wait` to detect completion without deserialising the dataset, so the driver stays light (RFC §5.4). The DAG is carried in the `PIPELINE_STARTED` event's `extra` so the monitoring server's `/dag` endpoint resolves.

- [ ] **Step 1: Write the failing test**

Create `tests/test_runner.py`:

```python
"""Integration test: the runner drives the chain and emits pipeline lifecycle events.

Marked `integration` because it stands up a local Ray cluster.
"""

import pytest
import ray

from hip_cargo.utils.progress import EventType, NullBackend, set_backend
from stokify.runtime.runner import run_pipeline


class _Recorder:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)

    def close(self):
        pass


@pytest.mark.integration
def test_run_pipeline_emits_lifecycle(tmp_path):
    ray.init(num_cpus=4, ignore_reinit_error=True, include_dashboard=False)
    rec = _Recorder()
    set_backend(rec)
    try:
        job_id = run_pipeline(
            work_dir=str(tmp_path),
            memory_mode="greedy",
            monitor=False,
            n_band=2,
            n_stokes=2,
            n_x=16,
            n_y=16,
            n_steps=1,
            process_iterations=2,
            image_iterations=2,
        )
    finally:
        set_backend(NullBackend())
        ray.shutdown()

    types = [e.event_type for e in rec.events]
    assert EventType.PIPELINE_STARTED in types
    assert types.count(EventType.STEP_STARTED) == 3
    assert types.count(EventType.STEP_COMPLETED) == 3
    assert types[-1] == EventType.COMPLETED
    assert all(e.job_id == job_id for e in rec.events)

    # The PIPELINE_STARTED event must carry the DAG for the /dag endpoint.
    started = next(e for e in rec.events if e.event_type == EventType.PIPELINE_STARTED)
    assert started.extra["nodes"] == ["init", "process", "image"]
    assert started.extra["edges"] == [["init", "process"], ["process", "image"]]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd /home/bester/software/stokify && uv run --extra full pytest tests/test_runner.py -v -m integration`
Expected: FAIL with `ModuleNotFoundError: No module named 'stokify.runtime.runner'`

- [ ] **Step 3: Implement `runtime/runner.py`**

Create `src/stokify/runtime/runner.py`:

```python
"""ObjectRef-chaining runner for the stokify pipeline (hand-written transpiler output).

Chains init -> process -> image by Ray ObjectRef. The driver holds only opaque
refs and never calls ``ray.get`` on an intermediate (driver-never-materializes,
RFC §5.4); it uses ``ray.wait`` to learn when each step finishes without
deserialising the dataset. Pipeline- and step-level events are emitted directly;
per-iteration PROGRESS/METRIC events come from inside each worker (the core
functions' ``track_progress`` blocks).
"""

import uuid

import ray

from hip_cargo.utils.progress import EventType, ProgressEvent, emit
from stokify.runtime.tasks import image_task, init_task, process_task

_STEPS = ["init", "process", "image"]
_EDGES = [["init", "process"], ["process", "image"]]


def _emit(event_type, worker_name, job_id, message="", extra=None):
    """Emit one pipeline/step lifecycle event, grouped under ``job_id``."""
    payload = {"pipeline_run_id": job_id}
    if extra:
        payload.update(extra)
    emit(
        ProgressEvent(
            job_id=job_id,
            worker_name=worker_name,
            event_type=event_type,
            message=message,
            extra=payload,
        )
    )


def run_pipeline(
    work_dir: str = ".stokify_work",
    memory_mode: str = "greedy",
    monitor: bool = False,
    job_id: str | None = None,
    ray_address: str | None = None,
    n_band: int = 4,
    n_stokes: int = 2,
    n_x: int = 256,
    n_y: int = 256,
    n_steps: int = 5,
    process_iterations: int = 10,
    image_iterations: int = 8,
) -> str:
    """Run the linear stokify pipeline by ObjectRef chaining. Returns the job_id."""
    if job_id is None:
        job_id = uuid.uuid4().hex[:8]

    if not ray.is_initialized():
        ray.init(address=ray_address, ignore_reinit_error=True)

    if monitor:
        from hip_cargo.monitoring.ray_backend import RayProgressBackend, get_or_create_aggregator
        from hip_cargo.utils.progress import set_backend

        set_backend(RayProgressBackend(get_or_create_aggregator()))

    # Pipeline start — carry the DAG in `extra` so GET /api/progress/{job_id}/dag works.
    _emit(
        EventType.PIPELINE_STARTED,
        "stokify",
        job_id,
        message="stokify pipeline started",
        extra={"nodes": _STEPS, "edges": _EDGES, "memory_mode": memory_mode},
    )

    # Submit the chain. Each .remote() returns immediately with an ObjectRef; Ray
    # resolves an upstream ref inside the consuming worker, never on the driver.
    _emit(EventType.STEP_STARTED, "init", job_id, message="submitting init")
    ref0 = init_task.remote(memory_mode, job_id, monitor, n_band, n_stokes, n_x, n_y, n_steps, work_dir)

    _emit(EventType.STEP_STARTED, "process", job_id, message="submitting process")
    ref1 = process_task.remote(ref0, memory_mode, job_id, monitor, process_iterations, work_dir)

    _emit(EventType.STEP_STARTED, "image", job_id, message="submitting image")
    ref2 = image_task.remote(ref1, memory_mode, job_id, monitor, image_iterations, work_dir)

    # Await completion in order WITHOUT materialising intermediates: ray.wait blocks
    # until a ref is ready but does not deserialise the object onto the driver.
    for name, ref in zip(_STEPS, [ref0, ref1, ref2]):
        ray.wait([ref], num_returns=1)
        _emit(EventType.STEP_COMPLETED, name, job_id, message=f"{name} complete")

    _emit(EventType.COMPLETED, "stokify", job_id, message="stokify pipeline complete")
    return job_id
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /home/bester/software/stokify && uv run --extra full pytest tests/test_runner.py -v -m integration`
Expected: 1 passed (takes a few seconds — local Ray startup).

- [ ] **Step 5: Lint and commit**

```bash
cd /home/bester/software/stokify
uv run ruff format . && uv run ruff check . --fix
git add -A
git commit -m "feat: runtime/runner.py ObjectRef-chaining pipeline runner"
```

---

## Task 7: `runtime/cli.py` — the thin `stokify run` driver

**Files:**
- Create: `src/stokify/runtime/cli.py`
- Modify: `src/stokify/cli/__init__.py` (register `run`)

`run` is the pipeline entry point — the CLI a transpiler would generate from the recipe's top-level `inputs:`. It is a plain Typer command (not a cab/step), depends only on ray + hip_cargo + Typer (light), and threads the recipe inputs + execution flags into `run_pipeline`.

- [ ] **Step 1: Implement `runtime/cli.py`**

Create `src/stokify/runtime/cli.py`:

```python
"""Thin lightweight-driver CLI for the stokify pipeline (hand-written transpiler output).

`stokify run` parses the recipe's top-level inputs plus execution flags and invokes
the ObjectRef-chaining runner. Its dependency footprint is ray + hip_cargo + Typer;
the heavy science stack stays in the workers. With --monitor it points the progress
backend at the detached aggregator the monitoring server reads.
"""

from pathlib import Path
from typing import Annotated, Literal

import typer


def run(
    work_dir: Annotated[
        Path,
        typer.Option(help="Directory for per-step zarr outputs (conservative mode)."),
    ] = Path(".stokify_work"),
    memory_mode: Annotated[
        Literal["greedy", "conservative"],
        typer.Option(help="greedy (plasma-resident) or conservative (store-backed)."),
    ] = "greedy",
    monitor: Annotated[
        bool,
        typer.Option(help="Stream progress to the monitoring aggregator."),
    ] = False,
    ray_address: Annotated[
        str | None,
        typer.Option(help="Ray cluster address (default: start a local cluster)."),
    ] = None,
    n_steps: Annotated[int, typer.Option(help="Simulated init read chunks.")] = 5,
    process_iterations: Annotated[int, typer.Option(help="process refinement iterations.")] = 10,
    image_iterations: Annotated[int, typer.Option(help="image major cycles.")] = 8,
) -> None:
    """Run the stokify pipeline (init -> process -> image) on a Ray cluster."""
    from stokify.runtime.runner import run_pipeline

    job_id = run_pipeline(
        work_dir=str(work_dir),
        memory_mode=memory_mode,
        monitor=monitor,
        ray_address=ray_address,
        n_steps=n_steps,
        process_iterations=process_iterations,
        image_iterations=image_iterations,
    )
    typer.echo(f"stokify pipeline complete - job_id={job_id}")
    if monitor:
        typer.echo(f"  events: GET http://localhost:8321/api/progress/{job_id}/events")
        typer.echo(f"  metrics: GET http://localhost:8321/api/progress/{job_id}/metrics/residual")
        typer.echo(f"  dag:    GET http://localhost:8321/api/progress/{job_id}/dag")
```

- [ ] **Step 2: Register `run` in `cli/__init__.py`**

Edit `src/stokify/cli/__init__.py`. After the `init`/`process`/`image` registration block, add:

```python
from stokify.runtime.cli import run  # noqa: E402

app.command(name="run")(run)
```

- [ ] **Step 3: Verify the CLI builds and `run` is registered**

Run: `cd /home/bester/software/stokify && uv run stokify --help`
Expected: command list now includes `run`.

Run: `uv run stokify run --help`
Expected: shows `--work-dir`, `--memory-mode`, `--monitor/--no-monitor`, `--ray-address`, `--n-steps`, `--process-iterations`, `--image-iterations`.

- [ ] **Step 4: Smoke-run the pipeline end-to-end (no monitor)**

Run (small + fast):
```bash
cd /home/bester/software/stokify
uv run --extra full stokify run --no-monitor --memory-mode greedy --n-steps 1 --process-iterations 2 --image-iterations 2
```
Expected: prints `stokify pipeline complete - job_id=XXXXXXXX` and exits 0. (Starts a local Ray cluster; takes a few seconds.)

- [ ] **Step 5: Lint and commit**

```bash
cd /home/bester/software/stokify
uv run ruff format . && uv run ruff check . --fix
git add -A
git commit -m "feat: runtime/cli.py thin 'stokify run' driver"
```

---

## Task 8: `demo.py` — end-to-end monitoring demonstration (RFC §12 stage 2.5)

**Files:**
- Create: `demo.py` (repo root)
- Create: `conftest.py` (repo root — lets the test import `demo`)
- Test: `tests/test_monitoring_e2e.py`

This is the artifact a SARAO reviewer runs. It drives the synthetic pipeline on a local Ray cluster with monitoring on, then queries the **existing** monitoring server's REST endpoints (in-process via FastAPI's `TestClient`) to prove real events, metrics, and the DAG flow end to end through the unchanged `apis` stack.

- [ ] **Step 1: Write `demo.py`**

Create `demo.py` at the repo root:

```python
"""End-to-end monitoring demonstration for the stokify pipeline (RFC §12 stage 2.5).

Runs the synthetic pipeline on a local Ray cluster with monitoring enabled, then
queries the hip-cargo monitoring server's REST endpoints (in-process via FastAPI's
TestClient) to prove that real progress events, metrics, and the DAG flow end to
end through the existing `apis` monitoring stack. Returns/exits non-zero if any
endpoint returns unexpected data, so it doubles as an automated check.

Honesty caveats (RFC §12 stage 2.5):
  * Steps run IN-PROCESS on a local cluster — the per-step container `runtime_env`
    in runtime/tasks.py is NOT applied (image_uri validation is a separate
    milestone, RFC §11).
  * On a single node, greedy vs conservative is cosmetic (plasma vs a local zarr
    on the same disk); this proves the contract + event flow, not the disk-bypass
    performance characteristic.
"""

import sys
import tempfile
import time

import ray
from fastapi.testclient import TestClient

from hip_cargo.monitoring.config import MonitorSettings
from hip_cargo.monitoring.ray_backend import RayProgressBackend, get_or_create_aggregator
from hip_cargo.monitoring.server import create_app
from hip_cargo.utils.progress import set_backend
from stokify.runtime.runner import run_pipeline


def run_demo() -> int:
    """Run the pipeline with monitoring and verify the server endpoints. Returns 0 on success."""
    ray.init(num_cpus=4, ignore_reinit_error=True)
    set_backend(RayProgressBackend(get_or_create_aggregator()))

    with tempfile.TemporaryDirectory() as tmp:
        job_id = run_pipeline(
            work_dir=tmp,
            memory_mode="conservative",
            monitor=True,
            n_band=2,
            n_stokes=2,
            n_x=64,
            n_y=64,
            n_steps=3,
            process_iterations=8,
            image_iterations=6,
        )

    # Worker events are pushed fire-and-forget from separate processes; give them
    # a moment to land in the detached aggregator actor before querying.
    time.sleep(1.5)

    # `with` runs the app's lifespan so the EventDispatcher (WebSocket fan-out) starts.
    with TestClient(create_app(MonitorSettings())) as client:
        latest = client.get(f"/api/progress/{job_id}").json()
        events = client.get(f"/api/progress/{job_id}/events").json()
        residual = client.get(f"/api/progress/{job_id}/metrics/residual").json()
        dag = client.get(f"/api/progress/{job_id}/dag").json()

        event_types = {e["event_type"] for e in events}
        print(f"\njob_id            : {job_id}")
        print(f"latest event      : {latest.get('event_type')!r}")
        print(f"total events      : {len(events)}")
        print(f"event types seen  : {sorted(event_types)}")
        print(f"residual samples  : {len(residual)}")
        print(f"dag nodes         : {dag.get('nodes')}")
        print(f"dag edges         : {dag.get('edges')}")

        ok = True
        ok = ok and len(events) > 0
        ok = ok and "pipeline_started" in event_types
        ok = ok and "completed" in event_types
        ok = ok and "metric" in event_types
        ok = ok and len(residual) > 0
        ok = ok and dag.get("nodes") == ["init", "process", "image"]

        # Best-effort WebSocket reachability. A late subscriber sees no history by
        # design (RFC §4 limitation), so we only confirm the endpoint accepts a
        # connection rather than asserting a streamed message.
        try:
            with client.websocket_connect(f"/ws/progress/{job_id}") as ws:
                print("websocket         : connected OK")
                ws.close()
        except Exception as exc:  # noqa: BLE001
            print(f"websocket         : connect failed ({exc})")

    ray.shutdown()
    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run_demo())
```

- [ ] **Step 2: Add a root `conftest.py` so tests can import `demo`**

Create `conftest.py` at the repo root:

```python
# Presence of this file adds the repo root to sys.path so tests can `import demo`.
```

- [ ] **Step 3: Write the integration test**

Create `tests/test_monitoring_e2e.py`:

```python
"""End-to-end check that progress flows through the monitoring stack.

Marked `integration` (stands up a local Ray cluster + the FastAPI app in-process).
"""

import pytest

from demo import run_demo


@pytest.mark.integration
def test_monitoring_end_to_end():
    assert run_demo() == 0
```

- [ ] **Step 4: Run the demo as a script**

Run:
```bash
cd /home/bester/software/stokify
uv run --extra full python demo.py
```
Expected: prints the summary block and `RESULT: PASS`, exit 0. If `create_app`/startup fails because it eagerly connects a Ray Jobs client, that is a real integration bug to fix in hip-cargo (per the constraint "if something doesn't work, that's a bug to fix") — capture the traceback and fix the smallest thing; do not work around the monitoring stack.

- [ ] **Step 5: Run the integration test**

Run: `cd /home/bester/software/stokify && uv run --extra full pytest tests/test_monitoring_e2e.py -v -m integration`
Expected: 1 passed.

- [ ] **Step 6: Lint and commit**

```bash
cd /home/bester/software/stokify
uv run ruff format . && uv run ruff check . --fix
git add -A
git commit -m "feat: end-to-end monitoring demo + integration test (stage 2.5)"
```

---

## Task 9: Quality bar, cleanup, and cross-repo docs (RFC §12 stage 3)

**Files:**
- Delete: `src/stokify/cli/onboard.py`, `src/stokify/core/onboard.py`, `src/stokify/cabs/onboard.yml`
- Modify: `src/stokify/cli/__init__.py`, `tests/test_roundtrip.py`
- Create: `DEMONSTRATOR.md`

- [ ] **Step 1: Remove the vestigial `onboard` scaffold command**

Delete the three onboard files:
```bash
cd /home/bester/software/stokify
rm src/stokify/cli/onboard.py src/stokify/core/onboard.py src/stokify/cabs/onboard.yml
```

Edit `src/stokify/cli/__init__.py` and remove the onboard import line and its `app.command(name="onboard")(onboard)` registration.

Edit `tests/test_roundtrip.py` and delete the `test_roundtrip_onboard` function.

- [ ] **Step 2: Verify the CLI still builds and round-trips**

Run:
```bash
cd /home/bester/software/stokify
uv run stokify --help
uv run --extra full pytest tests/test_roundtrip.py -v
```
Expected: help lists `init`, `process`, `image`, `run` (no `onboard`); 3 round-trip tests pass.

- [ ] **Step 3: Lightweight-install check (driver has no science stack, CLI still builds)**

Sync core-only (no `full` extra), confirm the science stack is absent yet the CLI builds, then restore:
```bash
cd /home/bester/software/stokify
uv sync --group dev
uv run python -c "import xarray" 2>&1 | grep -q "ModuleNotFoundError" && echo "xarray absent (good)" || echo "xarray present (unexpected)"
uv run stokify --help
uv run stokify run --help
uv sync --group dev --extra full
```
Expected: `xarray absent (good)`; both `--help` calls succeed (the CLI lazy-imports the science stack, so the driver stays light — RFC §9.5). Then the full stack is restored for the remaining steps.

- [ ] **Step 4: Security scan (bandit) — must be clean**

Run: `cd /home/bester/software/stokify && uv run bandit -r src/stokify/`
Expected: "No issues identified." (The generated/hand-written sources contain no `eval`/`exec`/`subprocess`/shell — this is the §2.2 negative result on the package's own source.)

- [ ] **Step 5: Ruff + full test suite**

Run:
```bash
cd /home/bester/software/stokify
uv run ruff format . && uv run ruff check .
uv run --extra full pytest -v
```
Expected: ruff clean; all tests pass (unit + the `integration`-marked Ray/monitoring tests).

- [ ] **Step 6: Confirm hip-cargo's own 314 tests still pass (no regressions)**

stokify is a separate repo; the only changes in the hip-cargo repo for this spike are the RFC and this plan (docs only). Confirm:
```bash
cd /home/bester/software/hip-cargo
git status --short          # expect only docs/design/* additions, no src/ changes
uv run pytest -q
```
Expected: `314 passed`. If the demo (Task 8) required a genuine bug fix in `hip_cargo.monitoring`, that change appears here too — re-run and ensure the count still passes (add a regression test in hip-cargo for any bug fixed).

- [ ] **Step 7: Write `DEMONSTRATOR.md`**

Create `DEMONSTRATOR.md` at the stokify repo root:

````markdown
# stokify — hip-cargo transpiler demonstrator

`stokify` is the runnable demonstrator for the hip-cargo `transpile` RFC
(`docs/design/transpile-rfc.md` in the hip-cargo repo). It is a three-step
linear pipeline (`init -> process -> image`) whose hand-written `runtime/`
modules exemplify what `hip-cargo transpile` *would* emit, streaming live
progress through hip-cargo's existing monitoring stack on **synthetic data**
(no casacore / measurement-set dependencies).

## Layout
- `src/stokify/core/`     — in-memory step bodies (`*_inmem`, used by the runner) + disk cab-entries
- `src/stokify/cli/`      — Typer wrappers that generate the cabs
- `src/stokify/cabs/`     — generated cab schemas
- `src/stokify/runtime/`  — hand-written would-be transpiler output (`tasks.py`/`runner.py`/`cli.py`)
- `src/stokify/recipes/stokify.yml` — restricted-grammar recipe (the transpiler's *input*)
- `demo.py`               — end-to-end, self-verifying monitoring demonstration

## Setup (two repos, side by side)
`stokify` depends on the local hip-cargo `apis` checkout (editable path source):

```bash
# ~/software/hip-cargo  (apis branch)
# ~/software/stokify

cd ~/software/stokify
uv sync --group dev --extra full
```

## One-command demo (self-verifying)
```bash
uv run --extra full python demo.py
# prints a summary and `RESULT: PASS`
```

## Live two-terminal monitoring
```bash
# Terminal 1 — start the monitoring server (from the hip-cargo repo)
cd ~/software/hip-cargo
uv run hip-cargo monitor --port 8321

# Terminal 2 — run the pipeline with monitoring (from the stokify repo)
cd ~/software/stokify
uv run --extra full stokify run --monitor --memory-mode conservative

# Terminal 3 / browser — observe
open http://localhost:8321/docs
curl http://localhost:8321/api/progress/<job_id>/events
```
> For live WebSocket history, connect to `ws://localhost:8321/ws/progress/<job_id>`
> *before* starting the run — a late subscriber only sees events after it joins
> (RFC §4 limitation).

## What is and isn't demonstrated (honesty caveats, RFC §12 stage 2.5)
- Steps run **in-process** on a local Ray cluster. The per-step container
  `runtime_env` in `runtime/tasks.py` is carried as data but **not applied** —
  validating per-task `image_uri` (experimental upstream) is a separate
  milestone (RFC §11).
- On a single node, `greedy` vs `conservative` is **cosmetic** (plasma vs a
  local zarr on the same disk). The demo proves the *contract + event flow*,
  not the disk-bypass performance characteristic (which needs a real cluster).

## Manual monitoring wiring (reference for the future `hip-cargo init` §9.7 templates)
`hip-cargo init` does not yet scaffold monitoring, so `stokify` wires it by hand.
The three load-bearing pieces a template should eventually emit:
1. **Dependency:** `hip-cargo[monitoring]` in `pyproject.toml`.
2. **Backend registration** (driver *and* each worker process):
   ```python
   from hip_cargo.monitoring.ray_backend import RayProgressBackend, get_or_create_aggregator
   from hip_cargo.utils.progress import set_backend
   set_backend(RayProgressBackend(get_or_create_aggregator()))
   ```
   — in `runtime/runner.py` (driver: pipeline/step events) and inside each
   `@ray.remote` task body in `runtime/tasks.py` (workers are separate processes).
3. **Instrumentation:** wrap each core step in
   `track_progress(worker_name, total_steps, job_id, pipeline_run_id)` and call
   `tracker.step()` / `.metric()` / `.artifact()` / `.log()`.
````

- [ ] **Step 8: Final lint and commit**

```bash
cd /home/bester/software/stokify
uv run ruff format . && uv run ruff check . --fix
git add -A
git commit -m "chore: drop onboard scaffold, add quality-bar checks and DEMONSTRATOR.md"
```

---

## Plan self-review — fragile points the executor must watch

This plan was reviewed against RFC §12 (stages 1, 2, 2.5, 3) and the task brief. Coverage: scaffold + 3 typed steps (Tasks 0–2), hand-written `tasks`/`runner`/`cli` (Tasks 5–7), restricted recipe (Task 4), runnable monitoring demo over the existing stack (Task 8), quality bar incl. lightweight install / bandit / hip-cargo's 314 tests (Task 9). Names are consistent across tasks: the **in-memory** functions are `*_inmem` (used by `tasks.py`); the **cab-entry** functions are `init`/`process`/`image` (the `command:` targets). Six points are genuinely fragile and are where execution may need to adapt — verify each empirically rather than assuming:

1. **Round-trip exactness (Task 3).** Byte-identical round-trip is guaranteed by the *canonicalize* step (regenerate each CLI from its cab and overwrite). If `generate-function` produces a different local variable name or import ordering than the hand-written seed (e.g. names the container-image variable `image` rather than `image_uri`), **adopt the regenerated file** — it is the source of truth. Only the signature + decorators must be correct by hand (they determine the cab).
2. **`RecipeDAG.edges` shape (Task 4).** The test assumes linear tuples `[("init","process"), ...]`. If the branch represents edges as dicts, adjust the assertion to the actual shape (the test's note shows how to inspect it).
3. **`create_app` startup (Task 8).** The monitoring server is exercised in-process via `TestClient(...)` under a `with` block (runs the lifespan / `EventDispatcher`). If startup eagerly connects a Ray Jobs client and fails on a dashboard-less local cluster, that is a real hip-cargo bug — fix the smallest thing in `hip_cargo.monitoring` and add a regression test there; do not work around the stack.
4. **zarr pin.** `xr.open_zarr(store, chunks=None)` (no-dask conservative handle) is pinned to `zarr>=2.17,<3` in the `[full]` extra; zarr 3 changed the API. If a different version is required, adjust `store_conservative` accordingly.
5. **Worker-event timing (Task 8).** Worker events are pushed fire-and-forget from separate processes; the demo sleeps 1.5 s before querying. If the metric/event assertions are flaky, increase the sleep or force a flush with `ray.get(get_or_create_aggregator().get_all_jobs.remote())` before querying.
6. **Ray resources for local runs.** `image_task` omits `num_gpus` so it schedules on a CPU-only local cluster; the `*_RUNTIME_ENV` constants (incl. a real step's GPU request) are carried as data only. Do not apply `runtime_env`/`num_gpus=1` in the local demo or tasks will hang waiting for resources that do not exist.

**Out of scope (do not drift into):** the transpiler itself; the React frontend; the §9.1 `ObjectRef`-input cab marker; any casacore/measurement-set dependency; any change to the restricted grammar. The hand-written `runtime/` is the exemplar of transpiler *output*, nothing more.

---

## Execution Handoff

Plan complete and saved to `docs/design/2026-06-04-stokify-spike-plan.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration. REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`.
2. **Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints for review.

Note: execution happens in the **new** `~/software/stokify` repo (created in Task 0); the only artifacts in the hip-cargo repo are this plan and the RFC (both docs). Which approach?
