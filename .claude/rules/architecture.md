# Architectural Rules & Domain Logic

Read this when editing `src/hip_cargo/**/*.py` files.

## 1. Code Parsing & Comment Preservation (LibCST)
* **Strict Requirement:** The project uses LibCST (Concrete Syntax Tree) for parsing Python code to preserve formatting, whitespace, and inline comments. **Do not use `eval()` or standard AST for parsing code.**
* **Core Functions:** Rely on `parse_decorator_libcst()`, `extract_input_libcst()`, `parse_annotated_libcst()`, and `get_cst_value()` for AST operations.
* **Comment Handling:** Inline comments are detected via the regex pattern `r'\s{2,}#'` (PEP 8 standard) and must be preserved through the full CLI → YAML → CLI roundtrip.
* **Multi-line Info Fields:** Multi-line info fields format each sentence on a new line, with the comment placed on the last line. You must use `format_info_fields()` to ensure proper YAML formatting with comment preservation.

## 2. Type Handling & Stimela Metadata
* **Comma-Separated Lists:** Typer cannot natively handle variable-length lists as a single option. Use the dedicated `NewType` wrappers (`ListInt`, `ListFloat`, `ListStr`) and their paired parsers from `utils/types.py`. These wrap `str` for Typer but parse into `list[int]`, etc., at runtime.
* **The Stimela Dictionary:** Input parameters can optionally include a `{"stimela": {...}}` dict inside `Annotated` type hints.
  * Values in this dict explicitly override inferred metadata (e.g., overriding `Path` to `Directory`).
  * It merges with inferred policies (positional, repeat).
  * Use `{"stimela": {"skip": True}}` to completely exclude a parameter from the generated cab YAML.
* **UPath-backed path types:** `File`, `Directory`, `MS`, and `URI` are all `NewType(..., UPath)`. User functions receive a `universal_pathlib.UPath` instance and call `.open()` / `.read_bytes()` / `.exists()` directly — hip-cargo does no IO. Local paths behave exactly like `pathlib.Path`; remote URIs (`s3://`, `gs://`, `az://`, `http(s)://`) are handled by the matching fsspec backend. Only the `File` / `Directory` / `MS` / `URI` wrappers emit the `parse_upath` parser in generated Typer CLIs; lists keep their comma-separated parsers.

## 3. Code Generation & Subprocesses
* **Parameter Sanitization:** Python identifiers cannot contain hyphens. When doing reverse generation, all parameter names must automatically sanitize hyphens to underscores (`model-name` → `model_name`), including F-string references in outputs.
* **Ruff Working Directory:** When `generate_function()` runs Ruff via subprocess to format generated code, it **must** run from the config file's parent directory (`cwd=config_file.parent`). This ensures Ruff accurately infers first-party packages for import grouping, which is critical for tests against external projects like `pfb-imaging`.
* **Path parser emission:** For custom path types (`File`, `Directory`, `MS`, `URI`), the generator emits `parser=parse_upath` (not `parser=Path`) in `typer.Option(...)`, and adds `parse_upath` to the generated `from hip_cargo import ...` block. This lets generated CLIs accept both local paths and remote URIs without any other change on the user's side.

## 4. Runtime Execution & Fallback
* **Image Tag Lifecycle:** The single source of truth for the container image is the `CONTAINER_IMAGE` constant in `_container_image.py`. It is loaded dynamically via `importlib` (no CWD dependency). Three mechanisms keep the tag in sync:
  1. **Feature branches (manual):** Developer edits `_container_image.py` to change the tag to the branch name. No `uv sync` needed since `get_container_image()` imports the module directly.
  2. **Merge to main (`update-cabs` workflow):** Resets the tag to `latest` via regex, regenerates cabs, and commits both `_container_image.py` and cab YAML files.
  3. **Releases (`tbump`):** Updates the tag to the semantic version (e.g. `0.2.0`) via before-commit hooks in `tbump.toml`.
* **Container Fallback:** Generated CLI functions must wrap lazy core imports in a `try/except ImportError`. On failure, `run_in_container()` reconstructs `sys.argv` and runs the command inside a container.
* **Mount Resolution:** Volume mounts are resolved automatically from Path-like type hints (ro) and `@stimela_output` decorators (rw). Backend priority is: `apptainer` → `singularity` → `docker` → `podman`.
* **GPU passthrough (container fallback):** A package opts in by declaring `GPU` in its `_container_image.py` (`True` / `False` / `"auto"` / a device spec). `run_in_container` reads it via `get_container_gpu(func.__module__.split(".")[0])`, resolves it through `_resolve_gpu_request` (the `HIP_CARGO_GPUS` env var overrides the constant; `"auto"` adds flags only when `_gpu_available()` and — for docker/podman — `_toolkit_available()`), and maps it per-runtime via `_gpu_args`: docker `--gpus`, podman CDI `--device nvidia.com/gpu=...` (host needs `nvidia-ctk cdi generate`), apptainer/singularity `--nv` (device specs become `CUDA_VISIBLE_DEVICES`). Host `CUDA_VISIBLE_DEVICES` is forwarded. None of this touches the cab YAML or the round-trip — `GPU` lives only in `_container_image.py`. Explicit device specs (e.g. `device=0,1`) target docker and apptainer/singularity; on podman prefer `True`/`"auto"`/`"all"` since CDI uses a different device grammar.
* **Per-backend run-args (container fallback):** `RUN_ARGS_DOCKER` / `RUN_ARGS_PODMAN` / `RUN_ARGS_APPTAINER` / `RUN_ARGS_SINGULARITY` in `_container_image.py` are read via `get_container_run_args` and inserted verbatim right after the `run`/`exec` subcommand for the matching runtime. `HIP_CARGO_RUN_ARGS` (shlex-split) appends to whichever backend is active. Default `[]`.
* **Fallback Parameters:** When a cab has an `image` field, the generated parameters must include `--backend` (Literal choice of `auto`, `native`, `apptainer`, `singularity`, `docker`, `podman`) and `--always-pull-images`. Both of these must be marked with `{"stimela": {"skip": True}}` so they do not appear in the generated cab YAML.
* **Remote URIs:** When a path-typed param carries a non-local UPath (`protocol not in {"", "file", "local"}`):
  * `_resolve_mounts` skips it — remote URIs contribute no bind mounts.
  * `preflight_remote_must_exist` calls `upath.exists()` before dispatch when `must_exist=True`. Missing → `typer.Exit(1)`. `mkdir` / `write_parent` / `access_parent` are skipped (no meaning on object stores).
  * `run_in_container` forwards per-scheme credentials into the container:

    | Scheme | Env vars forwarded | Config dir mounted (ro) |
    |---|---|---|
    | `s3` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_PROFILE`, `AWS_REGION`, `AWS_DEFAULT_REGION`, `AWS_ENDPOINT_URL` | `~/.aws` (skipped if `AWS_SESSION_TOKEN` is set) |
    | `gs` / `gcs` | `GOOGLE_APPLICATION_CREDENTIALS` | `~/.config/gcloud` + the keyfile |
    | `az` / `abfs` / `adl` | `AZURE_STORAGE_ACCOUNT`, `AZURE_STORAGE_KEY`, `AZURE_STORAGE_CONNECTION_STRING`, `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET` | `~/.azure` |
* **Missing backend extras:** If a user passes `s3://...` without `hip-cargo[s3]` installed, UPath raises `ImportError`. The generated wrapper's existing `try/except ImportError → run_in_container` pattern catches this, so users with a runtime installed fall through to containerised execution; users without a runtime get an enhanced error that suggests `pip install hip-cargo[s3]` (or `[gcs]`/`[azure]`).

## 5. Shared IR and `generate-schemas`
* **One CST walk, two consumers.** `hip_cargo.utils.spec` defines frozen dataclasses (`ParamSpec`, `CommandSpec`, `ModuleSpec`) that capture the *neutral* facts of a parsed CLI module. `parse_module(path) -> ModuleSpec` (in `utils/introspector.py`) is the single entry point both `generate-cabs` and `generate-schemas` go through. The IR carries no cab- or schema-specific shaping; that lives in adaptor functions next to each generator.
* **Cab-shaping adaptor.** `param_spec_to_cab_input(spec) -> (name, dict)` in `utils/introspector.py` applies cab semantics (dtype inference vs explicit override, Literal → choices, policies, info+inline-comment merge, `metadata.rich_help_panel`, the final `stimela_metadata` merge). `extract_input_libcst` is now a thin compose of `extract_param_spec` + `param_spec_to_cab_input`, retained for backward compat.
* **Tunable parameters live under `metadata`.** Stimela has a finite set of allowed top-level fields on a parameter definition — we cannot invent new ones. `tunable: true` rides inside the `metadata` dict (the same dict that carries `rich_help_panel`). In Python source: `StimelaMeta(metadata={"tunable": True})`. In cab YAML: `metadata: {tunable: true}`. The forward path merges `StimelaMeta.metadata` into `input_def["metadata"]` (it does not replace it). The reverse path (`generate_parameter_signature` in `utils/cab_to_function.py`) extracts `rich_help_panel` into `typer.Option(rich_help_panel=...)` and routes the rest of `metadata` back into `StimelaMeta(metadata=...)`.
* **Tunable type whitelist.** `core/generate_schemas.py::_to_pydantic_type` accepts only `int`, `float`, `str`, `bool`, `Literal[...]`, `ListInt`/`ListFloat`/`ListStr`, `list[int|float|str|bool]`, optionally `| None`. Path types (`File`/`Directory`/`MS`/`URI`) and any tunable with a typer `callback=` raise `TunableTypeError`. Non-tunable parameters of any type are ignored.
* **Schema generation is idempotent.** `_render_schema_module` returns deterministic output; the writer reads the existing file and skips the write if the formatted source is byte-identical (preserves mtime).

## 6. Project Scaffolding (`hip-cargo init`)
* Templates reside in `src/hip_cargo/templates/` and use `<PLACEHOLDER>` substitution.
* **CLI Mode Branching:** `--cli-mode single` uses `cli_single.py`, while `--cli-mode multi` uses `cli_multi.py`. **Do not unify the post-init print paths** in `core/init.py`; they must remain branched based on this mode.
* **Post-Generation Sequence:** The exact order of operations in `core/init.py` must be strictly followed: `uv sync` → `pytest` → `hip-cargo generate-cabs` → `ruff format/check` → `git init/add/commit` → `pre-commit install`.
