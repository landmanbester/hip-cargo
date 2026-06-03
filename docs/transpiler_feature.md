I want your help drafting a preliminary design document for a new
feature under my hip-cargo package
(https://github.com/landmanbester/hip-cargo). The document will be
shared with colleagues at SARAO (South African Radio Astronomy
Observatory) for feedback before any production implementation work
begins.

I have another instance of Claude available as a technical reviewer;
I will periodically paste its feedback for you to address as we
iterate. Treat that reviewer's comments as binding unless I tell you
otherwise.

CONTEXT

I am a maintainer of stimela
(https://github.com/caracal-pipeline/stimela), a YAML-based workflow
framework widely used in radio astronomy. Over time I have come to
think stimela's design choices, while reasonable in their time, have
accumulated costs that justify a smaller, stricter alternative for a
specific subset of users:

- Recipes can execute arbitrary shell commands with full user
  privileges. This is a real security concern on shared HPC.
- YAML recipes cannot be statically analysed by tools like ruff or
  bandit. Stimela's formula DSL (=GLOB(...), =IF(...), nested
  substitutions, ${self:...} interpolations) makes recipe content
  effectively un-auditable.
- More structurally: stimela tries to be a universal framework that
  can wrap any executable with any CLI convention. The cost of that
  ambition — policy machinery, parameter-passing flavours, wrangler
  regexes, multiple cab flavours — is paid perpetually by stimela
  maintainers and by every user reading a recipe.

DESIGN PHILOSOPHY: STANDARDIZE AT THE WRAPPER, NOT AT THE FRAMEWORK

Hip-cargo's structure embodies a different choice. Every external
package gets wrapped once, in Python, by a maintainer who understands
it, into hip-cargo's three-layer shape:

  cli/   — Typer-based CLI with Annotated types (the user-facing CLI)
  core/  — Python implementation; handles any quirks of the wrapped
           tool internally
  cabs/  — auto-generated stimela cab definitions (currently); under
           the proposal, also the entry-point for the transpiler

Inside core/, the wrapper does whatever is needed to call the
external package — subprocess with weird flags, a native Python API,
whatever. From the outside, every hip-cargo-wrapped package looks
identical: a Typer CLI with typed annotations, a typed Python
function, and a generated cab schema. The orchestration framework
therefore sees a uniform world of typed Python functions, and the
cost of handling each external package's idiosyncrasies is paid once,
by the wrapper maintainer, rather than perpetually by the framework
maintainers.

This is a load-bearing observation for the proposal: the transpiler
described below need not implement any of stimela's policy
machinery, parameter-passing flavours, or wrangler layer, because
every cab it consumes is already a typed Python callable in a known
hip-cargo-shaped package. The transpiler is a beneficiary of the
wrapper standardization that hip-cargo already enforces, not an
architect of it.

CURRENT STATE OF THE apis BRANCH

There is significant prior work on the `apis` branch of hip-cargo
that this proposal builds on top of, not in place of. The branch
contains a working monitoring infrastructure for hip-cargo-style
pipelines:

- A progress event protocol (src/hip_cargo/utils/progress.py and
  progress_context.py) with zero dependencies, a NullBackend default
  for zero overhead when off, and a track_progress() context manager
  that emits structured events for pipeline-aware monitoring. Event
  types already include pipeline_started, step_started, step_completed,
  step_failed — forward-looking toward the transpiler.
- A Ray-based aggregation layer (src/hip_cargo/monitoring/
  ray_backend.py) using a named, detached Ray actor with a ring buffer.
- A FastAPI monitoring server (src/hip_cargo/monitoring/server.py) with
  endpoints for job management (proxied to Ray Jobs SDK), progress data
  (REST + WebSocket), recipe inspection, and cab schema introspection.
- A recipe parser (src/hip_cargo/monitoring/recipe_parser.py) and cab
  resolver (cab_resolver.py) that parse stimela YAML, classify
  parameter bindings, and resolve _include references to cab schemas.
- 160+ passing tests including end-to-end integration tests with a
  real Ray cluster.
- A planned but unbuilt frontend (initial Stitch attempt did not
  produce usable results; new direction is to integrate the frontend
  into transpiled packages).
- A known-fragile POST /api/pipelines/submit endpoint that builds
  `stimela run` command strings; this will be replaced by direct
  invocation of transpiled packages via Ray Job Submission.

A more detailed design summary of the apis branch is available at
[I will paste the existing design doc as a separate attachment].
The transpiler proposed below is to be integrated with this existing
infrastructure: progress instrumentation reuses utils/progress.py,
the monitoring server discovers transpiled pipelines via Python
entry-points, and the recipe parser is extended into the transpiler's
IR.

PROPOSAL

A new hip-cargo sub-feature, `hip-cargo transpile`, that converts a
deliberately restricted subset of stimela-style YAML recipes into
installable Python packages. Generated packages are:

- Ray-native — every step is a @ray.remote task; for_loops with
  scatter become straightforward fan-out patterns; resource requests
  flow from cab decorator metadata into Ray task decorators.
- Reproducible — the transpile-time uv.lock pins all cab-providing
  packages, and is shipped as the Ray runtime_env for the generated
  package.
- Statically analysable — generated Python passes ruff/bandit; the
  transpiler refuses to emit code that doesn't.
- Self-contained but consistent — each transpiled package is its own
  pip-installable artifact with a Typer CLI, but emits progress
  events through hip-cargo's existing protocol and is discoverable
  by the existing monitoring server.

The deliberate cuts from stimela: no shell commands, no wranglers,
no _use/_include modularity beyond hip-cargo cab references (use
Python imports), no formula DSL beyond simple namespace references
and f-string-style formatting, no assign_based_on/preamble/epilogue,
no CASA flavour, no binary flavour. Cabs are only typed Python
functions in hip-cargo-shaped packages.

THREE-LAYER ARCHITECTURE

The proposal is organized as three loosely-coupled layers, each
independently installable:

  hip_cargo.utils.progress    — event protocol (no dependencies)
  hip_cargo.runtime           — execution layer for transpiled
                                packages (Ray submit helper, types,
                                decorator extensions)
  hip_cargo.monitoring        — server, aggregator, dashboard
                                (optional install; already exists)

Transpiled packages depend on hip_cargo.runtime and emit events
through hip_cargo.utils.progress. The monitoring server (which a
cluster admin runs once) subscribes to events from all transpiled
pipelines on the cluster and presents a unified dashboard. This is
the bridge between Ray's task-level observability (which Ray
already provides well) and pipeline-level observability (which is
the new value added).

WHAT I NEED FROM YOU

Please draft a preliminary design document, around 10–18 pages,
with the following structure. We will iterate on each section
together. I have another Claude instance available as a reviewer;
I'll periodically paste its feedback for you to address.

  1. Executive summary (½ page) — what we're proposing and why,
     written so a SARAO PI or sysadmin gets the point in 60
     seconds. Foreground the apis-branch foundation: this is a
     completion of existing work, not a green-field project.
  2. Motivation — the case for a smaller, stricter tool. Cover:
     security on shared HPC; static analysability; the wrapper-
     standardization argument (this should be its own subsection
     and is load-bearing). This must not read as a hit piece on
     stimela. I am a stimela maintainer; many of my colleagues
     use and depend on stimela; the goal is to articulate a niche
     where a smaller, stricter tool is genuinely better for a
     subset of users, not to dismiss the existing one.
  3. Current state of the apis branch — what already works, what
     it provides, what its limitations are. This section is
     important: it establishes that the proposal is a completion
     of a 70%-built system, not a new project. Be specific about
     which files and modules exist.
  4. Proposed architecture — the three-layer split (utils.progress
     / runtime / monitoring), how transpiled packages fit in, how
     the existing FastAPI server is reframed to serve transpiled
     pipelines. Include the IR design at a sketch level. Be
     concrete enough that an engineer can sanity-check it; do not
     try to write the full implementation.
  5. What we deliberately exclude — explicit list of stimela
     features that are out of scope and why each one is out. This
     is load-bearing; it is the document's main scope-setting
     argument. Connect each exclusion back to the wrapper-
     standardization principle where applicable.
  6. Pros — security model rooted in wrapper discipline,
     reproducibility via uv.lock as Ray runtime_env, smaller
     maintenance surface, alignment with SARAO's Ray migration,
     static analysability, observability via the existing
     monitoring server.
  7. Cons and risks — fragmenting the radio-astronomy workflow
     ecosystem, migration friction for existing recipes,
     dependence on Ray (version skew, deployment story for non-
     Ray HPC sites), limited expressiveness of the restricted
     subset, small-team sustainability, the fact that this is
     adjacent to stimela rather than superseding it. Be honest;
     do not soften.
  8. Required changes to hip-cargo — new CLI command (`hip-cargo
     transpile`), decorator extensions for resource specs and
     runtime hints, the runtime helper subpackage, packaging
     conventions, modifications to the monitoring server's
     submission endpoint, changes to `hip-cargo init` templates.
  9. Alternatives considered — for each, briefly state why it was
     not chosen, fairly:
       (a) contribute upstream to stimela to add stricter modes
           or static analysis features
       (b) build atop Snakemake or Nextflow
       (c) skip transpilation entirely and write pipelines as
           Python from the start
       (d) use Prefect/Flyte/Airflow as the workflow engine
       (e) extend the existing monitoring server to launch
           pipelines from YAML directly, without the transpiler
           step
 10. Open questions — things we genuinely do not know yet and want
     the SARAO working group to weigh in on. Include at minimum:
       - the packaging boundary between hip-cargo (development
         tool), hip-cargo-runtime (transpiled-package dep), and
         hip-cargo[monitoring] (cluster service)
       - governance: who maintains the transpiler, the runtime,
         the monitoring server; what happens if these diverge
       - how to handle nested recipes in the IR
       - what locality and resource hints belong on cabs vs on
         for_loops
       - Ray version compatibility strategy across the cluster,
         the transpiler, and transpiled packages
       - the migration story for existing stimela users at SARAO
         (transpile attempt + graceful failure on unsupported
         features?)
 11. Proposed next steps — a small, concrete spike (2 weeks) to
     validate the IR design against five representative recipes
     drawn from pfb-imaging and other hip-cargo-shaped packages,
     before any production implementation begins. The spike
     should produce hand-written examples of what transpiled code
     should look like for each recipe shape (linear, for_loop,
     scatter, nested), not a working transpiler.

TONE

Technical, sober, not promotional. Honest about uncertainty.
This is a discussion document, not a pitch. Assume readers are
technically sophisticated radio astronomers and software engineers
familiar with stimela, Ray, and the SARAO compute environment. You
need not explain MeerKAT, measurement sets, or basic interferometry
concepts. You should explain the wrapper-standardization argument
clearly because it is the heart of the proposal and may be the
piece readers find least familiar.

PROCESS

Start by reading the existing hip-cargo source code on the apis
branch so you have concrete context. Pay particular attention to:
- the three-layer pattern in src/hip_cargo/cli/, core/, and cabs/
- the progress protocol in src/hip_cargo/utils/progress.py
- the monitoring server in src/hip_cargo/monitoring/server.py
- the recipe parser in src/hip_cargo/monitoring/recipe_parser.py

Then draft sections 1 (executive summary), 2 (motivation, with
particular care on the wrapper-standardization subsection), and 5
(deliberate exclusions). These three together set the document's
framing and scope; everything else is supporting structure. Show
me those three sections first, we will iterate, and then proceed
section by section.

The document should live at docs/design/transpile-rfc.md in the
hip-cargo repo. Use a date- and version-stamped header at the top
in the style of an RFC or ADR.
