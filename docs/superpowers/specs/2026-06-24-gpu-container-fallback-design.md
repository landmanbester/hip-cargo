# GPU passthrough in the container-fallback path

**Issue:** [#78 — Enable GPU detection in container fallback](https://github.com/landmanbester/hip-cargo/issues/78)
**Date:** 2026-06-24
**Status:** Design approved, ready for implementation planning

## Problem

`run_in_container` → `_build_container_cmd` (in `src/hip_cargo/utils/runner.py`)
assembles the `docker`/`podman`/`apptainer`/`singularity` command with **no
GPU-passthrough flags**. When a package's container image is a CUDA/GPU image
(e.g. [kremetart](https://github.com/landmanbester/kremetart): Holoscan-cu13 +
CuPy-cuda13x on `nvidia/cuda:13.0.0-runtime`), commands dispatched into the
container run with no visible GPU — even on a host with a working GPU, drivers,
and the NVIDIA Container Toolkit. For GPU-only packages this defeats the whole
fallback: `docker run --gpus all <image>` works by hand, but the hip-cargo
fallback never adds `--gpus`.

The fix also opens a small, general escape hatch for other per-backend container
run arguments (e.g. `--ipc=host`, `--ulimit`, ports), since they are the same
class of problem.

## Constraints discovered during design

Two facts shaped the whole approach:

1. **Stimela's cab schema is closed.** The scabha `Cargo`/`Cab` dataclasses
   define a fixed top-level field set: `name, info, extra_info, inputs, outputs,
   defaults, backend, dynamic_schema, preamble, epilogue, image, command, args,
   flavour, parameter_passing, management, policies`. There is **no cab-level
   `metadata`/`extra` bucket** — only individual *parameters* carry
   `metadata: Dict[str, Any]`. Unknown top-level cab keys fail OmegaConf
   structured-config validation. So a `gpu:` (or `runtime_args:`) field at cab
   level would break Stimela.

2. **The CLI↔cab round-trip is byte-identity.** `generate-cabs` does
   `cab_body.update(decorator_kwargs)` (so any extra `@stimela_cab` kwarg leaks
   into the YAML), while the reverse `generate-function` only reconstructs
   `name`/`info`/`policies`. Therefore a declaration placed in the
   `@stimela_cab(...)` decorator either (a) leaks into the cab and breaks
   Stimela, or (b) is skipped from the cab and is then unrecoverable on
   reverse-generation, breaking the round-trip test. There is no clean third
   option *inside* the cab loop.

**Resolution:** declare GPU / run-args **outside** the cab + round-trip loop, in
the per-package `_container_image.py` module — already the hand-maintained
"container config, single source of truth," already imported by the runner via
`importlib`, and untouched by both the cab YAML and the round-trip test.

## Decisions

| Question | Decision |
|---|---|
| Scope | GPU passthrough **and** a general per-backend run-args escape hatch, both in `_container_image.py`. |
| Config surface | **No new CLI flag.** Declared in `_container_image.py`; overridable via env. |
| Detection model | **Package declares** intent; host auto-detection only gates the `"auto"` value. |
| Declaration home | `_container_image.py` (per-package). |
| `RUN_ARGS` granularity | **Per-backend** constants (HPC clusters commonly only have apptainer/singularity). |
| `GPU=True` semantics | Requests GPU **unconditionally** (honest hard-fail on a GPU-less host, with a message pointing at the toolkit). Only `"auto"` is gated by detection. |

## Declaration surface (`src/<pkg>/_container_image.py`)

```python
CONTAINER_IMAGE = "ghcr.io/<user>/<pkg>:latest"

# All optional. Absent ⇒ today's behaviour exactly (fully backward compatible).
GPU = True                      # True | False | "auto" | device spec ("device=0,1" / "0,1")
RUN_ARGS_DOCKER = []            # extra `docker run` args, verbatim
RUN_ARGS_PODMAN = []            # extra `podman run` args, verbatim
RUN_ARGS_APPTAINER = []         # extra `apptainer exec` args, verbatim
RUN_ARGS_SINGULARITY = []       # extra `singularity exec` args, verbatim
```

`GPU` is a single constant because GPU passthrough is translated per-runtime
(below). `RUN_ARGS_*` are free-form and inherently runtime-specific, so they are
per-backend. The runner selects the constant matching the *detected* runtime.

## Readers (`src/hip_cargo/utils/config.py`)

Beside `get_container_image`, same `importlib` pattern, safe defaults:

```python
def get_container_gpu(import_name: str) -> bool | str:        # default False
def get_container_run_args(import_name: str, runtime: str) -> list[str]:   # default []
```

`get_container_run_args` reads `RUN_ARGS_<RUNTIME.upper()>` from
`<import_name>._container_image`. Missing constant or missing module ⇒ default.

The runner derives the package from the decorated function with **no signature
or call-site change**: `import_name = func.__module__.split(".")[0]`
(`<pkg>.cli.<cmd>` → `<pkg>`).

## Resolution + env overrides (`src/hip_cargo/utils/runner.py`)

- `HIP_CARGO_GPUS` (if set) overrides the `GPU` constant.
- `HIP_CARGO_RUN_ARGS` (if set, `shlex`-split) **appends** to the selected
  backend's `RUN_ARGS_*`. Single env var; applies to whichever runtime is active
  for this invocation.

`GPU` value semantics:

| Value | Behaviour |
|---|---|
| `False` / `"none"` | No GPU flags (today's behaviour). |
| `True` / `"all"` | Request all GPUs **unconditionally**. Honest hard-fail on a GPU-less / toolkit-less host, with an error pointing at the NVIDIA Container Toolkit. |
| `"auto"` | Request all GPUs **only if** `_gpu_available()` and — for docker/podman — a toolkit signal is present. Otherwise no flags. |
| device spec (`"device=0,1"`, `"0,1"`) | Request those specific devices. |

Detection helpers:

```python
def _gpu_available() -> bool:
    return shutil.which("nvidia-smi") is not None or os.path.exists("/dev/nvidia0")

def _toolkit_available() -> bool:   # docker/podman only
    return shutil.which("nvidia-ctk") is not None or shutil.which("nvidia-container-runtime") is not None
```

For apptainer/singularity, `--nv` only binds the host driver libraries (no
container toolkit needed), so `"auto"` there is gated on `_gpu_available()`
alone.

## Per-runtime GPU mapping

| runtime | flag emitted |
|---|---|
| docker | `--gpus <all\|spec>` |
| podman | `--device nvidia.com/gpu=<all\|spec>` (CDI; host needs `nvidia-ctk cdi generate` — documented) |
| apptainer / singularity | `--nv`; a device spec is translated to a `CUDA_VISIBLE_DEVICES` env entry |

Host `CUDA_VISIBLE_DEVICES`, when set, is forwarded into the container for all
runtimes.

## Command assembly (`_build_container_cmd`)

GPU args and the selected `RUN_ARGS_*` are inserted **right after** the
`run`/`exec` subcommand, before mounts:

```python
# docker / podman
cmd = [runtime, "run", "--rm", "--user", uid_gid, "-w", cwd, *gpu_args, *run_args]
# apptainer / singularity
cmd = [runtime, "exec", "--pwd", cwd, *gpu_args, *run_args]
```

Resolution (reading constants/env, host detection, per-runtime translation)
lives in `run_in_container`; `_build_container_cmd` / `_gpu_args` only assemble
the already-resolved values. This keeps assembly pure and unit-testable.

## Blast radius

**Touched:**
- `src/hip_cargo/utils/runner.py` — resolution, detection, `_gpu_args`, assembly.
- `src/hip_cargo/utils/config.py` — `get_container_gpu`, `get_container_run_args`.
- `src/hip_cargo/core/init.py` — the inline `_container_image.py` writer (`init.py:157-158`) gains commented `GPU` / `RUN_ARGS_*` examples for discoverability in scaffolded packages.
- `.claude/rules/architecture.md` §4 — document the feature.
- `src/hip_cargo/templates/CLAUDE.md` §3 — document for scaffolded packages.

**Not touched (deliberately):** `generate-function` / `generate-cabs` templates,
the round-trip test, any cab YAML, the `run_in_container` signature, or its
generated call sites. **Downstream packages need no regeneration.** The
regex-based tag rewriters (`update-cabs`, `tbump`) match the `CONTAINER_IMAGE`
tag line specifically and are unaffected by the new constants.

## Testing

All unit-level, no GPU required in CI:
- `_gpu_args(runtime, spec)` per runtime (pure string assembly).
- Resolution precedence: `HIP_CARGO_GPUS` env > `GPU` constant; `HIP_CARGO_RUN_ARGS` appends to the active backend.
- Auto-detect via monkeypatched `shutil.which` / `os.path.exists`, including the docker/podman toolkit gate and the apptainer no-toolkit path.
- `get_container_gpu` / `get_container_run_args` against a temporary `_container_image`-style module.
- `_build_container_cmd` arg placement (gpu + run-args directly after the subcommand) for each runtime.

One opt-in live test gated on `HIP_CARGO_LIVE_GPU`, excluded from required CI
checks (mirrors the `HIP_CARGO_LIVE_S3` pattern).

## kremetart follow-up (separate PR, not in this change)

Add `GPU = True` to kremetart's `_container_image.py`. Its Dockerfile already
sets `NVIDIA_VISIBLE_DEVICES=all` / `NVIDIA_DRIVER_CAPABILITIES=compute,utility`,
so `--gpus all` / `--nv` is the only missing piece. No `RUN_ARGS_*` needed
unless Holoscan later requires `--ipc=host` or a stack `--ulimit`.

## Deferred / out of scope

- Per-command (rather than per-package) run-args. GPU-ness is a property of the
  image, so per-package is correct for GPU; per-command run-args can be added
  later if a real need appears.
- Newer-podman `--gpus` alias (try-both). CDI form is the portable choice for now.
- Non-NVIDIA accelerators (ROCm, etc.).
