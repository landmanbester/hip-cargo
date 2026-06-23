# RFC Revision + Stokify Demonstrator — Claude Code Task

## Context

Read the CLAUDE.md and README.md for full project context, then read the
file `transpile-rfc.md` in the project root (the current RFC draft). This
task has two parts:

**Part A**: Revise the RFC to address review feedback, add missing sections,
and strengthen the document before circulation to SARAO colleagues.

**Part B**: Build the stokify demonstrator as described in §11 stages 1–3
of the RFC, exercising the monitoring infrastructure on the `apis` branch
end-to-end. The demonstrator must be in a **working, demonstrable state**
before the RFC is shared — the RFC is a discussion document, but it is far
more convincing if reviewers can `pip install` the demonstrator and see
the monitoring dashboard streaming real progress events from a running
pipeline.

---

## Part A: RFC Revisions

### A.1 New Section: Design Evolution (insert after §2, before §3)

Add a new section (renumber subsequent sections) titled something like
"Design history and evolution" or "From monitoring dashboard to
transpiler." This section explains the lineage of the proposal. It
should cover:

**The original intent.** The project began as a monitoring layer for
hip-cargo. The goal was to give any hip-cargo-scaffolded project an
automatic web-based dashboard for observing long-running scientific
pipelines. Users should be able to check progress from their phone,
inspect convergence metrics, view intermediate images, and control
execution (kill/relaunch steps with modified parameters). The reference
use case was pfb-imaging's SARA deconvolution pipeline, and the design
was driven by the `sara.yml` stimela recipe.

**What was built.** The `apis` branch implements:
- A progress event protocol (`utils/progress.py`) with pipeline-level
  lifecycle events, zero-overhead NullBackend, and an ergonomic
  `track_progress()` context manager.
- A recipe parser (`monitoring/recipe_parser.py`) that extracts DAG
  structure, parameter bindings, and cab schemas from stimela recipe
  YAML.
- A Ray-based progress aggregator actor with ring-buffered event
  storage, metric history, and DAG-aware pipeline tracking.
- A FastAPI server with REST endpoints, push-based WebSocket streaming
  via a centralised EventDispatcher, and thin proxy over the Ray Jobs
  SDK.
- A cab resolver that follows `_include` references to extract full
  parameter schemas from installed packages.
- 160+ tests including end-to-end integration tests with a real local
  Ray cluster.

Note: while the monitoring infrastructure exists in hip-cargo itself,
`hip-cargo init` does not currently scaffold any of it into new projects.
Enabling monitoring is a manual wiring step — a gap the proposed §8.7
template changes address.

**Why the design evolved.** Three realisations pushed the design from
"monitoring dashboard that observes stimela pipelines" toward "transpiler
that compiles restricted recipes into Ray-orchestrated packages":

1. The `sara.yml` recipe — the reference pipeline — uses stimela features
   (the formula DSL, alias broadcasts, conditional expressions) that are
   opaque to static analysis and difficult to audit on shared HPC. Building
   a monitoring dashboard for pipelines that *interpret* these features at
   runtime is useful but does not address the security concern that is
   increasingly relevant as SARAO moves scientific workloads onto shared
   infrastructure.

2. The frontend design (attempted via Google Stitch) proved difficult to
   get right in isolation. It became clear that the dashboard would be more
   naturally produced *from* the pipeline structure rather than *discovering*
   it at runtime — a transpiler that knows the DAG at compile time can emit
   a frontend customised to the specific pipeline, which is both simpler and
   more useful than a generic dashboard that has to parse recipes on the fly.

3. The monitoring infrastructure already on the `apis` branch (the progress
   protocol, the Ray aggregator, the FastAPI server) is precisely the
   observability layer a transpiled package needs. Rather than building two
   separate systems (a monitoring dashboard for stimela, and later a
   transpiler), the monitoring work becomes the observability substrate the
   transpiler inherits. The ~70% of the system that exists is reused, not
   discarded.

**Why stokify rather than sara.** The canonical SARA recipe
(`sara.yml`) uses `=IF`, `=IFSET`, arithmetic expressions, and alias
broadcasts throughout. These are precisely the stimela features the
restricted subset excludes. Rather than beginning with a recipe that must
be extensively rewritten to fit the restricted grammar, the demonstrator
is a new, purpose-built three-step package (`stokify`) that adheres to
the restricted subset from the start. This lets the spike validate the
target shape — the ObjectRef chaining, the per-step `runtime_env`, the
driver-never-materialises principle, the monitoring integration — without
conflating "does the architecture work?" with "can we port an existing
recipe?" The porting question is real and is addressed separately
(§10 on conditional-by-specialisation; §8 on the pfb-imaging Ray
ownership refactor), but it is not the right first question.

The existing monitoring infrastructure is fully exercised by the
demonstrator: stokify's runner emits `PIPELINE_STARTED`/`STEP_STARTED`/
`STEP_COMPLETED`/`COMPLETED` events through `track_progress()`, which flow
through the `RayProgressBackend` to the `ProgressAggregator` actor and
onward to the FastAPI server's REST and WebSocket endpoints. The monitoring
dashboard (once built) will display the stokify DAG, stream progress in
real time, and allow job control — exactly the original vision, but
delivered as a property of the transpiled package rather than as a
standalone tool.

### A.2 New Section: Frontend via Transpilation (insert in §4 or §8)

Add a section explaining how transpilation makes the frontend easier and
better. This is a significant advantage the current RFC underplays.

The key insight: at transpile time, the full pipeline structure is known
statically. The transpiler has the complete DAG — steps, edges, parameter
schemas, resource requirements, container images, memory modes — resolved
and validated. It could emit not just `tasks.py`/`runner.py`/`cli.py` but
also frontend assets where:

- The React Flow DAG is generated from known-at-compile-time node/edge
  data rather than discovered at runtime via API calls.
- Parameter forms for each step are pre-typed components generated from
  the resolved cab schemas, not dynamically rendered from an API response.
- The metric chart layout knows which metrics each step emits (because
  the core functions are inspectable at transpile time).
- The pipeline topology is embedded as static JSON, not streamed on first
  WebSocket connect.

The monitoring *server* (the FastAPI API on the `apis` branch) still
handles the dynamic parts: live progress streaming, metric updates,
job control (kill/relaunch). But the *structure* of what's being monitored
is known at compile time and baked into the frontend. This is a genuine
architectural win over the original design where the frontend discovered
the pipeline structure at runtime.

The §8.7 template changes should note that `hip-cargo init` scaffolds a
monitoring view as part of the template, and `hip-cargo transpile` can
optionally emit a pre-built, pipeline-specific monitoring frontend
alongside the runner. This connects the transpiler work back to the
original monitoring vision and gives the frontend a concrete delivery
mechanism.

### A.3 Revisions to Existing Sections

**§3 (Current state of the apis branch):**
- Note the test count is now ~160 tests (the document says 314 which
  may be stale or include other tests; verify the actual count on the
  branch with `uv run pytest --co -q | tail -1`).
- Add an explicit note that `hip-cargo init` does **not** currently
  scaffold any monitoring infrastructure. The monitoring subpackage
  (`hip_cargo.monitoring`), the progress protocol (`utils/progress.py`,
  `utils/progress_context.py`), and the CLI command (`hip-cargo monitor`)
  exist in hip-cargo itself, but a project scaffolded via `hip-cargo init`
  does not get a `monitoring/` directory, a DESIGN.md, a `.env.example`,
  or any wiring that connects the project's workers to the progress
  backend. This means enabling monitoring for a scaffolded project is
  currently a manual step: the developer must add `hip-cargo[monitoring]`
  as a dependency, wire up `set_backend(RayProgressBackend(aggregator))`
  in their entry point, and instrument their `core/` functions with
  `track_progress()` calls. The §8.7 template changes proposed in the RFC
  address this — `hip-cargo init` should scaffold a monitoring-ready
  project — but as of the current `apis` branch, this scaffolding does
  not exist. The stokify demonstrator wires up monitoring by hand,
  which is both a necessary step for the spike and a concrete example
  of what the template changes should automate.

**§4.7 (IR sketch):**
- Strengthen the statement about RecipeDAG/RecipeSpec convergence. The
  monitoring-side `RecipeDAG` and the codegen-side `RecipeSpec` must share
  a parser front-end. The monitoring parser already classifies bindings,
  extracts `recipe.*` references, builds edges, and resolves cab schemas.
  The transpiler needs exactly this, plus validation that the recipe stays
  within the restricted subset, plus the ability to resolve restricted
  bindings to concrete Python expressions. The right architecture is a
  shared front-end that parses, classifies, and optionally validates
  restriction compliance, with the monitoring view and the codegen view
  as two consumers. Do not build two parsers for the same YAML format.

**§10 (Open questions):**
- Add a note that the `image_uri` experimental dependency should be
  explicitly validated as part of the §11 spike. The stokify demonstrator
  should include a milestone: "does `image_uri` actually work on SARAO's
  target Ray version with the container runtime we use?" This is cheap to
  test and load-bearing.
- On version skew: note that a version-skew policy is needed *before* the
  first transpiled package ships to external users, not after. A semver
  contract on `hip_cargo.runtime`'s public API surface is the minimum.

**§11 (Proposed next steps):**
- Add a stage between stages 2 and 3 (or fold into stage 2): exercise the
  monitoring server with the hand-written stokify runner. This means
  starting `hip-cargo monitor`, running the stokify pipeline, and verifying
  that the FastAPI endpoints stream real progress events. The demonstrator
  should be demonstrable — a reviewer can `pip install` both packages,
  run `hip-cargo monitor` in one terminal, run `stokify run` in another,
  and see live progress at `localhost:8321/docs` (or eventually, a real
  dashboard). Add this explicitly as a deliverable.

### A.4 Tone/Framing Notes

The RFC is already well-written. A few minor framing adjustments:

- Where the document says "the frontend is pending" or "the Stitch attempt
  was abandoned," reframe positively: the frontend design is being
  rethought as a transpiler-emitted artifact, which is architecturally
  better (known at compile time) and practically simpler (no separate
  build/deploy).
- Where the document discusses the monitoring infrastructure as background,
  emphasise that it is actively exercised by the demonstrator — it is not
  legacy infrastructure, it is the observability layer reviewers will see
  working.
- Make sure the document reads as "here is a working system that is ~70%
  built and demonstrated, and here is a focused proposal for the remaining
  ~30%" rather than "here is a proposal for a new system." The `apis`
  branch work is a strength, not just context.

---

## Part B: Stokify Demonstrator

### B.1 What to Build

Follow §11 stages 1–3 of the RFC. The deliverable is a working, end-to-end
demonstrator, not a sketch. A SARAO reviewer should be able to:

1. `pip install` stokify (from a local path) and hip-cargo with the
   monitoring extra
2. Run `hip-cargo monitor` in one terminal
3. Run the stokify pipeline in another terminal
4. See real progress events streaming through the FastAPI endpoints

### B.2 Stage 1: Scaffold stokify

Use `hip-cargo init` to scaffold a new package called `stokify`. It should
be a multi-command project with three steps:

- `init` — reads a measurement set (or, for the demonstrator, simulates
  reading one by creating a synthetic `xr.Dataset` with realistic shape)
- `process` — transforms coherencies into image-ready Stokes visibilities
  (for the demonstrator, a synthetic transformation on the dataset)
- `image` — grids and images the Stokes visibilities (for the demonstrator,
  a synthetic imaging step)

Each step is a `core/` function that:
- Accepts a `memory_mode: Literal["greedy", "conservative"]` argument
- Returns an `xr.Dataset`
- For the demonstrator, uses synthetic data with realistic shapes and
  simulated computation time (sleep) to exercise the progress protocol
- Uses `track_progress()` to emit progress events with realistic metrics

**Critical: the core functions must emit progress events.** This is what
makes the monitoring demonstration work. Example for the `process` step:

```python
from hip_cargo.utils.progress_context import track_progress

def process(dataset: xr.Dataset, memory_mode: Literal["greedy", "conservative"],
            n_iterations: int = 10, ...) -> xr.Dataset:
    with track_progress("process", total_steps=n_iterations) as tracker:
        for i in range(n_iterations):
            # ... synthetic processing ...
            tracker.step(message=f"Iteration {i+1}/{n_iterations}")
            tracker.metric("residual", 1.0 / (i + 1))
            tracker.metric("convergence", 1.0 - 1.0 / (i + 1))
    return result_dataset
```

Each step should also be wrapped with the standard hip-cargo decorators
(`@stimela_cab`, `@stimela_output`) and have corresponding cab YAML
generated via `hip-cargo generate-cabs`.

### B.3 Stage 2: Hand-write the transpiled output

Create `stokify/runtime/` (or `stokify/pipeline/`) containing:

- **`tasks.py`** — three `@ray.remote` functions, each with per-step
  `runtime_env` and resource requests. The heavy import is inside the
  task body. Each task wraps the core function and threads `memory_mode`
  through.

- **`runner.py`** — chains tasks via ObjectRef:
  ```
  ref0 = init_task.remote(...)
  ref1 = process_task.remote(ref0, ...)
  ref2 = image_task.remote(ref1, ...)
  ```
  Emits pipeline-level progress events (`PIPELINE_STARTED`, `STEP_STARTED`,
  `STEP_COMPLETED`, `COMPLETED`) using `track_progress()` and direct
  `emit()` calls. **Does not call `ray.get()` on intermediate refs** —
  the driver-never-materialises principle.

- **`cli.py`** — Typer app generated from the recipe's top-level inputs.
  Parses CLI arguments, optionally starts the monitoring backend
  (`set_backend(RayProgressBackend(aggregator))`), and invokes the runner.

### B.4 Stage 2.5: Exercise the monitoring server

This is critical for the demonstration. After the hand-written runner works:

1. Start the monitoring server: `hip-cargo monitor --port 8321`
2. In the runner's `cli.py`, add a `--monitor` flag that:
   - Gets or creates the `ProgressAggregator` actor
   - Sets the `RayProgressBackend` as the active backend
   - Runs the pipeline
3. Verify the following endpoints return correct data while the pipeline
   runs:
   - `GET /api/progress/{job_id}` — latest progress event
   - `GET /api/progress/{job_id}/events` — all events
   - `GET /api/progress/{job_id}/metrics/residual` — metric time series
   - `GET /api/progress/{job_id}/dag` — pipeline DAG structure
   - `WS /ws/progress/{job_id}` — real-time event streaming

Write a small integration test or demo script that runs the pipeline with
monitoring enabled and queries the API endpoints to verify data flows
end-to-end. This test should:
- Start Ray locally
- Create the aggregator
- Wire up the progress backend
- Run the stokify pipeline
- Query the REST API and verify events, metrics, and DAG structure
- Print a summary showing it all works

This demo script is the thing you show to SARAO reviewers.

### B.5 Stage 3: Validate the quality bar

- The stokify package installs cleanly via `pip install -e .`
- The CLI builds and `stokify --help` works
- `uv run ruff format .` and `uv run ruff check .` pass
- `uv run bandit -r src/stokify/` passes (no security findings)
- The pipeline runs end-to-end on synthetic data
- Progress events flow through the monitoring stack correctly
- All existing hip-cargo tests still pass (stokify is a separate package,
  it should not break hip-cargo)

### B.6 Write a Restricted Recipe

Create `stokify/recipes/stokify.yml` — a stimela-style recipe in the
restricted grammar. This is the recipe the *eventual* transpiler would
consume. It should:
- Use only `_include` cab references (to stokify's own cabs)
- Use only `=recipe.x` bindings and `{recipe.x}` interpolation
- No `=IF`, `=IFSET`, arithmetic, aliases, or any excluded features
- Chain the three steps: init → process → image

This recipe exists to show what the transpiler's input looks like. The
hand-written `tasks.py`/`runner.py`/`cli.py` are what the transpiler
*would have emitted* from this recipe. The reviewer can compare the two
and see that the codegen is mechanical.

### B.7 Where to Put Stokify

Create stokify as a separate repository or as a subdirectory of hip-cargo
(e.g. `examples/stokify/`). The second option is simpler for the
demonstrator and keeps everything in one place for reviewers. Use
whichever approach `hip-cargo init` naturally produces.

If it's a separate directory, make sure the `apis` branch README or a
top-level `DEMONSTRATOR.md` explains how to set it up:

```bash
# Install hip-cargo with monitoring
pip install -e ".[monitoring]"

# Install stokify
cd examples/stokify && pip install -e .

# Terminal 1: start monitoring
hip-cargo monitor --port 8321

# Terminal 2: run the pipeline
stokify run --monitor --memory-mode greedy

# Terminal 3 (or browser): observe
# Open http://localhost:8321/docs and try the endpoints
# Or: curl http://localhost:8321/api/progress/<job_id>/events
```

---

## Design Constraints

- **The stokify core functions use synthetic data.** Do not depend on
  casacore, measurement sets, or any radio astronomy packages. Use
  `xarray` and `numpy` to create synthetic datasets with realistic shapes
  (e.g. `(n_band=4, n_stokes=2, n_x=256, n_y=256)` — small enough to
  run quickly but structured like a real imaging pipeline).
- **The runner hand-written code should look exactly like what a transpiler
  would emit.** No clever abstractions, no helper classes, no imports that
  wouldn't appear in generated code. Plain, mechanical, readable Python.
- **Exercise the existing monitoring infrastructure — do not modify it.**
  The `apis` branch monitoring code (`utils/progress.py`,
  `monitoring/ray_backend.py`, `monitoring/server.py`, etc.) should be
  used as-is. If something doesn't work, that's a bug to fix, not a reason
  to work around it.
- **Monitoring wiring is manual for now.** Since `hip-cargo init` does not
  currently scaffold monitoring infrastructure, the stokify demonstrator
  must wire up monitoring by hand: adding `hip-cargo[monitoring]` as a
  dependency, calling `get_or_create_aggregator()` and
  `set_backend(RayProgressBackend(...))` in the runner/CLI entry point,
  and instrumenting core functions with `track_progress()`. This manual
  wiring is both necessary for the spike and serves as a concrete reference
  for what the §8.7 template changes should eventually automate. Document
  each manual step clearly so it can be turned into template code later.
- **The demonstrator must be runnable.** Not "the code looks right," but
  "a reviewer can pip install it, run it, and see progress events flowing."
  This is what makes the RFC convincing.

## Files to Create/Modify

### Part A (RFC revisions):
- MODIFY: `transpile-rfc.md` (all changes described in A.1–A.4)

### Part B (stokify demonstrator):
- CREATE: `examples/stokify/` (or wherever hip-cargo init puts it)
  - Full hip-cargo package structure
  - `core/init.py`, `core/process.py`, `core/image.py`
  - `cli/__init__.py` with Typer app
  - `cabs/` with generated cab YAMLs
  - `runtime/tasks.py`, `runtime/runner.py`, `runtime/cli.py`
    (the hand-written transpiled output)
  - `recipes/stokify.yml` (restricted grammar recipe)
  - `pyproject.toml`
- CREATE: `examples/stokify/demo.py` (or `scripts/demo.py`)
  — the end-to-end monitoring demonstration script
- CREATE: `DEMONSTRATOR.md` (setup and usage instructions)
- POSSIBLY MODIFY: existing hip-cargo monitoring code (only bug fixes)

## Do NOT

- Build the actual transpiler (that's the next proposal, after the spike)
- Build the React frontend (that's after the RFC is accepted)
- Depend on casacore, python-casacore, or measurement set libraries
- Modify the restricted grammar or relax the exclusions
- Skip the monitoring integration — the whole point is to demonstrate
  the monitoring stack working with a real pipeline
