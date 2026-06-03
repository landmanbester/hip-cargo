# Design: URI / Object-Store Support via fsspec + universal_pathlib

**Date:** 2026-04-19
**Status:** Approved (pending spec review)
**Author:** brainstorming session with @landmanbester

## Problem

hip-cargo's `URI` type is currently a cosmetic `NewType("URI", Path)` —
identical in behaviour to `File`/`Directory`/`MS`. Every downstream code path
(`_is_path_type`, `_resolve_mounts`, `cab_to_function`) follows `__supertype__`
straight to `pathlib.Path`, so a parameter declared as `URI` is silently
treated as a local filesystem path.

We want users to be able to pass object-store URIs (`s3://`, `gs://`, `az://`,
`http(s)://`, and arbitrary self-hosted schemes) directly into any
path-accepting parameter, have hip-cargo auto-detect the relevant credentials,
and have the container fallback plumb those credentials through correctly.

## Goals

1. `URI`, `File`, `Directory`, `MS` accept local or remote paths transparently.
2. User functions receive a path-like object they can use for IO directly
   (no string parsing, no client bootstrap).
3. Credentials are discovered from the user's normal environment — no hip-cargo
   config. Native runs defer to each SDK's credential chain; container runs
   get env vars + config directories forwarded automatically.
4. Minimal core install: hip-cargo adds two small pure-Python deps, and cloud
   backends stay opt-in as extras.
5. No changes to the generated cab YAML. Stimela's existing dtype handling is
   preserved.

## Non-goals

- Glob expansion of remote URIs (e.g. `s3://bkt/*.fits` → `list[File]`).
  Users call `fs.glob()` from their own code.
- Caching or prefetching remote objects before execution.
- Auto-uploading local outputs to remote stores after a run.
- Custom auth flows beyond what each backend's SDK already supports
  (IAM roles, workload identity, device login all work natively via the SDK
  chains — hip-cargo stays out of it).

## Design

### 1. Type system

In `src/hip_cargo/utils/introspector.py`:

```python
from upath import UPath

MS        = NewType("MS", UPath)
Directory = NewType("Directory", UPath)
File      = NewType("File", UPath)
URI       = NewType("URI", UPath)
```

`universal_pathlib.UPath("/tmp/x")` is path-equivalent to
`pathlib.Path("/tmp/x")` for local paths, and accepts remote schemes.

Typer does not know about `UPath`, so a shared parser is added to
`src/hip_cargo/utils/types.py`:

```python
def parse_upath(value: str) -> UPath:
    return UPath(value)
```

The parser is wired into generated CLI functions via `typer.Option(...,
parser=parse_upath)`, mirroring the existing `ListInt`/`ListFloat`/`ListStr`
pattern. `parse_upath` is re-exported from `hip_cargo/__init__.py` alongside
the existing list parsers, and `UPath` itself is re-exported for user
convenience (`from hip_cargo import UPath`).

### 2. Type detection

`_is_path_type` in `src/hip_cargo/utils/runner.py` currently terminates on
`issubclass(tp, Path)`. It is widened to `issubclass(tp, PurePath)` — `UPath`
is a `PurePath` subclass, so all NewType chains still resolve correctly.
`NewType.__supertype__` traversal is unchanged.

### 3. Native execution

No IO happens inside hip-cargo. The CLI parses the string into a `UPath`, the
user function receives it, and user code does its own reads/writes
(`upath.open()`, `.read_bytes()`, `.exists()`, `.glob()`, ...).

**`must_exist` pre-flight (remote only):** before dispatching to the user
function, hip-cargo iterates path-typed params and — only for remote UPaths
(`upath.protocol not in ("", "file", "local")`) — calls `upath.exists()`. On
miss, `typer.Exit(1)` with `"Parameter '{name}': '{uri}' does not exist"`.
Local paths keep today's mount-driven semantics (unchanged). `mkdir`,
`write_parent`, and `access_parent` are skipped for remote UPaths — they have
no crisp meaning on object stores.

**Missing backend extra (e.g. user passes `s3://...` without
`hip-cargo[s3]`):** `UPath` instantiation raises `ImportError` for the
missing backend. The generated CLI's existing `try/except ImportError →
run_in_container()` pattern catches this:

- If a container runtime is present: falls through to containerised execution
  — the user gets the bundled image which has all backends installed.
- If no runtime is present: the runner's existing "install full package
  dependencies" error is augmented to also suggest `pip install hip-cargo[s3]`
  (or `[gcs]`/`[azure]`/`[all]`) based on the scheme detected in `sys.argv`.

### 4. Container fallback

Extends `src/hip_cargo/utils/runner.py`:

**Mount resolution.** `_resolve_mounts` iterates params as today, but skips
any UPath whose `.protocol` is not `""`/`"file"`/`"local"`. Remote URIs
contribute no bind mounts.

**Scheme detection.** A single pass over params collects the set of
non-local protocols in use, e.g. `{"s3"}`, `{"gs", "s3"}`.

**Per-scheme credential plumbing:**

| Scheme | Env vars forwarded | Config dir bind-mounted (ro) |
|---|---|---|
| `s3` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_PROFILE`, `AWS_REGION`, `AWS_DEFAULT_REGION`, `AWS_ENDPOINT_URL` | `~/.aws` |
| `gs` / `gcs` | `GOOGLE_APPLICATION_CREDENTIALS` (+ bind-mount the file it points at, ro) | `~/.config/gcloud` |
| `az` / `abfs` / `adl` | `AZURE_STORAGE_ACCOUNT`, `AZURE_STORAGE_KEY`, `AZURE_STORAGE_CONNECTION_STRING`, `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET` | `~/.azure` |
| `http` / `https` | (none by default; self-hosted endpoints that are S3-compatible are expected to use the `s3` scheme with `AWS_ENDPOINT_URL`) | — |

**Short-lived token heuristic.** If `AWS_SESSION_TOKEN` is set in the host
env when the `s3` scheme is in use, skip the `~/.aws` bind-mount. This avoids
stale profile files masking an active short-lived session.

**Command construction.** `_build_container_cmd` gains per-scheme `env`
forwards and extra bind-mounts:

- `docker` / `podman`: one `-e VAR` per forwarded env var, and one
  `-v HOST:HOST:ro` per config dir / keyfile.
- `apptainer` / `singularity`: one `--env VAR=VALUE` per forwarded env var,
  and one `--bind HOST:HOST:ro` per config dir / keyfile.

Env vars and mounts are only added when the corresponding scheme is detected
in the params — a command that passes only local paths produces no extra
flags.

`_pull_image`, the runtime-detection priority list (`apptainer` →
`singularity` → `docker` → `podman`), and the rest of the runner are
unchanged.

### 5. Reverse generation

`src/hip_cargo/utils/cab_to_function.py` is unchanged:

- `CUSTOM_STIMELA_TYPES = {"File", "Directory", "MS", "URI"}` stays as-is.
- Generated Python still emits `from hip_cargo import File, Directory, MS, URI`.
- Because those names now resolve to `NewType(..., UPath)`, regenerated
  functions are URI-capable by construction. No round-trip marker, no
  scheme-aware reverse logic.

### 6. Cab YAML

**No changes.** Generated YAML keeps emitting today's dtype strings
(`File`, `Directory`, `MS`, `URI`). Stimela's existing validation layer
handles URI-style strings correctly for these dtypes. This is a deliberate
decision — stimela is the source of truth for dtype semantics, and hip-cargo
stays out of it.

### 7. Packaging

`pyproject.toml`:

- Core deps gain `fsspec` and `universal_pathlib`. Both are small pure-Python
  packages with no native bits.
- New optional extras:
  - `s3 = ["s3fs"]`
  - `gcs = ["gcsfs"]`
  - `azure = ["adlfs"]`
  - `all = ["hip-cargo[s3,gcs,azure]"]`
- Existing deps (`typer`, `pyyaml`, `libcst`, `ruff`, `typing-extensions`,
  `tomli`) unchanged.
- The container image referenced by `_container_image.py` (used for fallback
  execution) installs `hip-cargo[all]` so container fallback works for every
  scheme without further configuration. The relevant Dockerfile / image
  build must be updated as part of the implementation.

## Testing

All tests follow the existing rule: `tempfile.TemporaryDirectory()` only, no
artifacts in the repo.

- **Unit-level (always run):**
  - Local UPath round-trips through the CLI → user function path.
  - `must_exist` pre-flight with a tempdir: local present / local missing /
    remote present / remote missing.
  - Scheme detection from a mixed bag of params (local + one or more
    remotes).
  - Credential env-var and bind-mount construction: set fake env vars and a
    fake `HOME` with stub `.aws`/`.config/gcloud`/`.azure` directories,
    assert the command built by `_build_container_cmd` contains the expected
    `-e` / `--bind` / `--env` flags. Do not actually invoke a container
    runtime.
  - Short-lived token heuristic: `AWS_SESSION_TOKEN` set → no `~/.aws`
    bind-mount; unset → bind-mount present.
- **Remote-path behaviour without real clouds:** use fsspec's built-in
  `MemoryFileSystem` (the `memory://` protocol) to exercise the
  "remote UPath skips mounts + performs pre-flight `exists()`" paths. Zero
  external deps; always runs in CI.
- **Comment-preservation roundtrips** (existing tests): re-run against
  functions that use UPath-backed NewTypes to confirm LibCST parsing is
  unaffected by the new supertype.
- **Optional live-cloud tests:** gated on env vars
  (`HIP_CARGO_LIVE_S3=1`, `HIP_CARGO_LIVE_GCS=1`, `HIP_CARGO_LIVE_AZURE=1`).
  Skipped in CI unless explicitly enabled. Not part of required checks.

## Documentation

Documentation updates are part of the implementation, not a follow-up:

- **`README.md`** — add a "Remote URIs and object stores" section covering:
  the four NewType wrappers are UPath-backed; the install extras
  (`hip-cargo[s3]`, `[gcs]`, `[azure]`, `[all]`); the credential chains used
  natively and the env vars / config dirs forwarded in container fallback;
  a short example of a user function taking an `Annotated[File, ...]` and
  being invoked with `s3://bucket/key.fits`.
- **`.claude/rules/architecture.md`** — update §2 ("Type Handling & Stimela
  Metadata") and §4 ("Runtime Execution & Fallback") to reflect that
  `File`/`Directory`/`MS`/`URI` are UPath-backed; document the
  `must_exist` pre-flight rule for remote URIs; document the credential
  forwarding table in §4 (source of truth for the mapping). Add a note that
  `mkdir` / `write_parent` / `access_parent` are skipped for remote UPaths.
- **`.claude/rules/python-standards.md`** — extend §3 ("Lazy Imports") with a
  note on backend extras (`s3fs` etc.) being imported lazily by fsspec; no
  direct imports of backend packages in CLI modules.
- **`.claude/rules/testing-and-ci.md`** — add a note that `memory://` via
  fsspec is the preferred way to unit-test remote-URI behaviour, and that
  real-cloud tests must be gated on `HIP_CARGO_LIVE_*` env vars and excluded
  from required checks.

## Open questions

None at design time. Implementation-level decisions (exact Typer parser
wiring, precise error messages, whether the container image bundles `[all]`
vs a slimmer subset by default) will be resolved during the implementation
plan.

## Out of scope

- Glob expansion for remote URIs passed to `list[File]`.
- Remote-path caching / prefetch.
- Auto-upload of local outputs to object stores.
- Auth flows beyond env + default config dirs.
