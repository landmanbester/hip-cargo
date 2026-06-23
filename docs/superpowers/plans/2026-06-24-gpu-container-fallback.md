# GPU Container-Fallback Passthrough Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the container-fallback path attach the host GPU (and optional per-backend extra run-args) when a hip-cargo package declares it needs one.

**Architecture:** A package declares `GPU` and per-backend `RUN_ARGS_*` constants in its `_container_image.py`. `runner.py` reads them (via the decorated function's `__module__`), applies env overrides (`HIP_CARGO_GPUS`, `HIP_CARGO_RUN_ARGS`), resolves a per-runtime GPU flag (`--gpus` / CDI `--device` / `--nv`) gated by conservative host auto-detection for the `"auto"` value, and inserts them into the runtime command. Nothing touches the cab schema or the CLI↔cab round-trip.

**Tech Stack:** Python 3.10+, stdlib only (`shutil`, `os`, `shlex`, `importlib`), pytest, typer.

## Global Constraints

- Python 3.10+ only; modern syntax (`X | Y`, `list[int]`).
- **No new dependencies.** Everything used here is stdlib.
- Absent constants ⇒ today's behaviour exactly (backward compatible).
- After every code change run: `uv run ruff format . && uv run ruff check . --fix`.
- Conventional Commits (`feat:`, `test:`, `docs:`, …); first line < 72 chars.
- Tests use `tmp_path` / `monkeypatch`; no artifacts in the repo tree.
- The live GPU test is opt-in (gated on `HIP_CARGO_LIVE_GPU`) and excluded from required CI checks.
- Reference spec: `docs/superpowers/specs/2026-06-24-gpu-container-fallback-design.md`.

## File Structure

- `src/hip_cargo/utils/config.py` — add `get_container_gpu`, `get_container_run_args` (+ private `_load_container_image_module`).
- `src/hip_cargo/utils/runner.py` — add `_gpu_available`, `_toolkit_available`, `_resolve_gpu_request`, `_gpu_args`; extend `_build_container_cmd` and `run_in_container`.
- `src/hip_cargo/core/init.py` — scaffold commented `GPU` / `RUN_ARGS_*` in generated `_container_image.py`.
- `.claude/rules/architecture.md` — document under §4.
- `src/hip_cargo/templates/CLAUDE.md` — document under §3.
- `tests/test_config.py` — reader tests.
- `tests/test_runner.py` — resolution, mapping, assembly, dispatch tests.
- `tests/test_gpu_live.py` — opt-in live test.

---

## Task 1: Container-config readers (`config.py`)

**Files:**
- Modify: `src/hip_cargo/utils/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `get_container_gpu(import_name: str) -> bool | str` — reads `GPU` from `<import_name>._container_image`; default `False`.
  - `get_container_run_args(import_name: str, runtime: str) -> list[str]` — reads `RUN_ARGS_<RUNTIME.upper()>`; default `[]`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_config.py`:

```python
from hip_cargo.utils.config import get_container_gpu, get_container_run_args


class TestGetContainerGpu:
    """Test get_container_gpu reads the GPU constant with safe defaults."""

    @pytest.mark.unit
    def test_default_false_for_hip_cargo(self):
        # hip-cargo's own _container_image.py declares no GPU constant.
        assert get_container_gpu("hip_cargo") is False

    @pytest.mark.unit
    def test_false_for_missing_module(self):
        assert get_container_gpu("nonexistent_pkg_xyz_12345") is False

    @pytest.mark.unit
    def test_reads_declared_value(self, monkeypatch):
        import sys
        import types

        mod = types.ModuleType("fakegpupkg._container_image")
        mod.CONTAINER_IMAGE = "ghcr.io/x/fakegpupkg:latest"
        mod.GPU = True
        monkeypatch.setitem(sys.modules, "fakegpupkg._container_image", mod)
        parent = types.ModuleType("fakegpupkg")
        monkeypatch.setitem(sys.modules, "fakegpupkg", parent)
        assert get_container_gpu("fakegpupkg") is True


class TestGetContainerRunArgs:
    """Test get_container_run_args reads per-backend RUN_ARGS_* constants."""

    @pytest.mark.unit
    def test_default_empty_for_hip_cargo(self):
        assert get_container_run_args("hip_cargo", "docker") == []

    @pytest.mark.unit
    def test_empty_for_missing_module(self):
        assert get_container_run_args("nonexistent_pkg_xyz_12345", "apptainer") == []

    @pytest.mark.unit
    def test_reads_backend_specific_args(self, monkeypatch):
        import sys
        import types

        mod = types.ModuleType("fakeargpkg._container_image")
        mod.CONTAINER_IMAGE = "ghcr.io/x/fakeargpkg:latest"
        mod.RUN_ARGS_APPTAINER = ["--ipc=host"]
        monkeypatch.setitem(sys.modules, "fakeargpkg._container_image", mod)
        parent = types.ModuleType("fakeargpkg")
        monkeypatch.setitem(sys.modules, "fakeargpkg", parent)
        assert get_container_run_args("fakeargpkg", "apptainer") == ["--ipc=host"]
        # A backend with no constant declared falls back to [].
        assert get_container_run_args("fakeargpkg", "docker") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ImportError: cannot import name 'get_container_gpu'`.

- [ ] **Step 3: Implement the readers**

Append to `src/hip_cargo/utils/config.py`:

```python
def _load_container_image_module(import_name: str):
    """Import ``<import_name>._container_image`` or return None if absent.

    Mirrors the ModuleNotFoundError discrimination in get_container_image:
    a missing package/module returns None, while an unrelated import failure
    inside the module propagates.
    """
    module_name = f"{import_name}._container_image"
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name and module_name.startswith(exc.name):
            return None
        raise


def get_container_gpu(import_name: str) -> bool | str:
    """Return a package's declared GPU passthrough setting.

    Reads the ``GPU`` constant from ``<import_name>._container_image``.

    Args:
        import_name: Python import name of the package (e.g. 'kremetart').

    Returns:
        The ``GPU`` value (True/False or a string spec), or False if the
        package declares none.
    """
    mod = _load_container_image_module(import_name)
    if mod is None:
        return False
    return getattr(mod, "GPU", False)


def get_container_run_args(import_name: str, runtime: str) -> list[str]:
    """Return a package's declared extra run-args for a container runtime.

    Reads the ``RUN_ARGS_<RUNTIME>`` constant (e.g. ``RUN_ARGS_APPTAINER``)
    from ``<import_name>._container_image``.

    Args:
        import_name: Python import name of the package.
        runtime: Container runtime name (docker/podman/apptainer/singularity).

    Returns:
        A list of extra arguments, or an empty list if none are declared.
    """
    mod = _load_container_image_module(import_name)
    if mod is None:
        return []
    return list(getattr(mod, f"RUN_ARGS_{runtime.upper()}", []))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (all config tests).

- [ ] **Step 5: Lint**

Run: `uv run ruff format . && uv run ruff check . --fix`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/hip_cargo/utils/config.py tests/test_config.py
git commit -m "feat(runner): read GPU/RUN_ARGS from package _container_image"
```

---

## Task 2: GPU request resolution + host detection (`runner.py`)

**Files:**
- Modify: `src/hip_cargo/utils/runner.py` (add helpers; add `import shlex` if not present)
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `_gpu_available() -> bool` — True if `nvidia-smi` on PATH or `/dev/nvidia0` exists.
  - `_toolkit_available() -> bool` — True if `nvidia-ctk` or `nvidia-container-runtime` on PATH.
  - `_resolve_gpu_request(gpu_setting: bool | str, runtime: str) -> str | None` — returns `None` (no GPU), `"all"`, or a raw device-spec string. Honours the `HIP_CARGO_GPUS` env override and gates `"auto"` on detection.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_runner.py` (extend the import block from runner to include the new names, then add the class):

```python
class TestResolveGpuRequest:
    """Test _resolve_gpu_request normalisation, env override, and auto gating."""

    @pytest.fixture(autouse=True)
    def _clear_env(self, monkeypatch):
        monkeypatch.delenv("HIP_CARGO_GPUS", raising=False)

    @pytest.mark.unit
    def test_false_is_none(self):
        from hip_cargo.utils.runner import _resolve_gpu_request

        assert _resolve_gpu_request(False, "docker") is None

    @pytest.mark.unit
    def test_true_is_all(self):
        from hip_cargo.utils.runner import _resolve_gpu_request

        assert _resolve_gpu_request(True, "docker") == "all"

    @pytest.mark.unit
    def test_string_all_and_none(self):
        from hip_cargo.utils.runner import _resolve_gpu_request

        assert _resolve_gpu_request("all", "docker") == "all"
        assert _resolve_gpu_request("none", "docker") is None

    @pytest.mark.unit
    def test_device_spec_passthrough(self):
        from hip_cargo.utils.runner import _resolve_gpu_request

        assert _resolve_gpu_request("device=0,1", "docker") == "device=0,1"

    @pytest.mark.unit
    def test_env_override_wins(self, monkeypatch):
        from hip_cargo.utils.runner import _resolve_gpu_request

        monkeypatch.setenv("HIP_CARGO_GPUS", "none")
        assert _resolve_gpu_request(True, "docker") is None

    @pytest.mark.unit
    def test_auto_docker_requires_gpu_and_toolkit(self, monkeypatch):
        from hip_cargo.utils import runner

        monkeypatch.setattr(runner, "_gpu_available", lambda: True)
        monkeypatch.setattr(runner, "_toolkit_available", lambda: True)
        assert runner._resolve_gpu_request("auto", "docker") == "all"

        monkeypatch.setattr(runner, "_toolkit_available", lambda: False)
        assert runner._resolve_gpu_request("auto", "docker") is None

        monkeypatch.setattr(runner, "_gpu_available", lambda: False)
        monkeypatch.setattr(runner, "_toolkit_available", lambda: True)
        assert runner._resolve_gpu_request("auto", "docker") is None

    @pytest.mark.unit
    def test_auto_apptainer_needs_only_gpu(self, monkeypatch):
        from hip_cargo.utils import runner

        monkeypatch.setattr(runner, "_gpu_available", lambda: True)
        monkeypatch.setattr(runner, "_toolkit_available", lambda: False)
        assert runner._resolve_gpu_request("auto", "apptainer") == "all"

    @pytest.mark.unit
    def test_gpu_available_detects_nvidia_smi(self, monkeypatch):
        from hip_cargo.utils import runner

        monkeypatch.setattr(runner.shutil, "which", lambda name: "/usr/bin/nvidia-smi" if name == "nvidia-smi" else None)
        monkeypatch.setattr(runner.os.path, "exists", lambda p: False)
        assert runner._gpu_available() is True

    @pytest.mark.unit
    def test_gpu_available_false_when_absent(self, monkeypatch):
        from hip_cargo.utils import runner

        monkeypatch.setattr(runner.shutil, "which", lambda name: None)
        monkeypatch.setattr(runner.os.path, "exists", lambda p: False)
        assert runner._gpu_available() is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_runner.py::TestResolveGpuRequest -v`
Expected: FAIL with `ImportError`/`AttributeError` for `_resolve_gpu_request`.

- [ ] **Step 3: Implement the helpers**

In `src/hip_cargo/utils/runner.py`, ensure `import shlex` is in the top imports (add it alphabetically near `import shutil`). Then add, just above `_build_container_cmd` (near line 598):

```python
def _gpu_available() -> bool:
    """Return True if a GPU is plausibly present on the host."""
    return shutil.which("nvidia-smi") is not None or os.path.exists("/dev/nvidia0")


def _toolkit_available() -> bool:
    """Return True if the NVIDIA container toolkit is plausibly installed."""
    return shutil.which("nvidia-ctk") is not None or shutil.which("nvidia-container-runtime") is not None


def _resolve_gpu_request(gpu_setting: bool | str, runtime: str) -> str | None:
    """Resolve the effective GPU spec for a runtime.

    Precedence: the ``HIP_CARGO_GPUS`` env var overrides ``gpu_setting``.

    Returns:
        ``None`` for no GPU, ``"all"`` to request all devices, or a raw
        device-spec string (the runtime's native syntax).
    """
    raw: bool | str | None = os.environ.get("HIP_CARGO_GPUS")
    if raw is None:
        raw = gpu_setting

    if raw is True:
        token = "all"
    elif raw is False or raw is None:
        token = "none"
    else:
        token = str(raw).strip()

    low = token.lower()
    if low in ("", "none", "false", "0"):
        return None
    if low in ("all", "true"):
        return "all"
    if low == "auto":
        if not _gpu_available():
            return None
        if runtime in ("docker", "podman") and not _toolkit_available():
            return None
        return "all"
    return token  # explicit device spec, in the runtime's native syntax
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_runner.py::TestResolveGpuRequest -v`
Expected: PASS.

- [ ] **Step 5: Lint**

Run: `uv run ruff format . && uv run ruff check . --fix`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/hip_cargo/utils/runner.py tests/test_runner.py
git commit -m "feat(runner): resolve GPU request with env override and auto-detect"
```

---
## Task 3: Per-runtime GPU arg mapping (`runner.py`)

**Files:**
- Modify: `src/hip_cargo/utils/runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes: nothing (operates on an already-resolved spec).
- Produces:
  - `_gpu_args(runtime: str, gpu_spec: str | None) -> tuple[list[str], dict[str, str]]` — returns `(runtime_flags, extra_env)`. `extra_env` may carry `CUDA_VISIBLE_DEVICES` for apptainer/singularity device specs.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_runner.py`:

```python
class TestGpuArgs:
    """Test _gpu_args per-runtime flag mapping."""

    @pytest.mark.unit
    def test_none_spec_yields_nothing(self):
        from hip_cargo.utils.runner import _gpu_args

        assert _gpu_args("docker", None) == ([], {})
        assert _gpu_args("apptainer", None) == ([], {})

    @pytest.mark.unit
    def test_docker_all(self):
        from hip_cargo.utils.runner import _gpu_args

        assert _gpu_args("docker", "all") == (["--gpus", "all"], {})

    @pytest.mark.unit
    def test_docker_device_spec_passthrough(self):
        from hip_cargo.utils.runner import _gpu_args

        assert _gpu_args("docker", "device=0,1") == (["--gpus", "device=0,1"], {})

    @pytest.mark.unit
    def test_podman_cdi_all(self):
        from hip_cargo.utils.runner import _gpu_args

        assert _gpu_args("podman", "all") == (["--device", "nvidia.com/gpu=all"], {})

    @pytest.mark.unit
    def test_apptainer_nv_all(self):
        from hip_cargo.utils.runner import _gpu_args

        assert _gpu_args("apptainer", "all") == (["--nv"], {})

    @pytest.mark.unit
    def test_singularity_nv_all(self):
        from hip_cargo.utils.runner import _gpu_args

        assert _gpu_args("singularity", "all") == (["--nv"], {})

    @pytest.mark.unit
    def test_apptainer_device_spec_sets_cuda_env(self):
        from hip_cargo.utils.runner import _gpu_args

        args, env = _gpu_args("apptainer", "device=0,1")
        assert args == ["--nv"]
        assert env == {"CUDA_VISIBLE_DEVICES": "0,1"}

    @pytest.mark.unit
    def test_apptainer_bare_device_spec_sets_cuda_env(self):
        from hip_cargo.utils.runner import _gpu_args

        args, env = _gpu_args("apptainer", "0,1")
        assert args == ["--nv"]
        assert env == {"CUDA_VISIBLE_DEVICES": "0,1"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_runner.py::TestGpuArgs -v`
Expected: FAIL with `ImportError` for `_gpu_args`.

- [ ] **Step 3: Implement `_gpu_args`**

Add to `src/hip_cargo/utils/runner.py`, directly after `_resolve_gpu_request`:

```python
def _gpu_args(runtime: str, gpu_spec: str | None) -> tuple[list[str], dict[str, str]]:
    """Map a resolved GPU spec to runtime flags and any extra env.

    Args:
        runtime: Container runtime name.
        gpu_spec: ``None`` (no GPU), ``"all"``, or a device-spec string.

    Returns:
        ``(flags, env)`` where ``flags`` are inserted after the run/exec
        subcommand and ``env`` is merged into the forwarded environment
        (used to translate device specs for apptainer/singularity).
    """
    if gpu_spec is None:
        return [], {}
    if runtime == "docker":
        return ["--gpus", gpu_spec], {}
    if runtime == "podman":
        return ["--device", f"nvidia.com/gpu={gpu_spec}"], {}
    if runtime in ("apptainer", "singularity"):
        env: dict[str, str] = {}
        if gpu_spec != "all":
            # --nv selects all visible devices; narrow via CUDA_VISIBLE_DEVICES.
            env["CUDA_VISIBLE_DEVICES"] = gpu_spec.replace("device=", "")
        return ["--nv"], env
    return [], {}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_runner.py::TestGpuArgs -v`
Expected: PASS.

- [ ] **Step 5: Lint**

Run: `uv run ruff format . && uv run ruff check . --fix`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/hip_cargo/utils/runner.py tests/test_runner.py
git commit -m "feat(runner): map resolved GPU spec to per-runtime flags"
```

---
## Task 4: Wire GPU + run-args into command assembly and dispatch (`runner.py`)

**Files:**
- Modify: `src/hip_cargo/utils/runner.py` (top imports; `_build_container_cmd` ~lines 598-645; `run_in_container` ~lines 37-71)
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes: `_resolve_gpu_request`, `_gpu_args` (Tasks 2-3); `get_container_gpu`, `get_container_run_args` (Task 1).
- Produces:
  - `_build_container_cmd(..., gpu_args: list[str] | None = None, run_args: list[str] | None = None)` — inserts `gpu_args` then `run_args` immediately after the `run`/`exec` subcommand.
  - `run_in_container(...)` (signature unchanged) — now resolves GPU/run-args from `func.__module__` + env and forwards `CUDA_VISIBLE_DEVICES`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_runner.py`:

```python
class TestBuildContainerCmdGpuRunArgs:
    """Test gpu_args / run_args placement in _build_container_cmd."""

    @pytest.mark.unit
    def test_docker_gpu_and_run_args_after_subcommand(self):
        from hip_cargo.utils.runner import _build_container_cmd

        cmd = _build_container_cmd(
            "docker",
            "img:latest",
            {},
            "/work",
            ["pkg", "cmd"],
            gpu_args=["--gpus", "all"],
            run_args=["--ipc=host"],
        )
        # run is at index 1; gpu+run args follow the -w <cwd> block, before the image
        assert cmd[0:2] == ["docker", "run"]
        assert "--gpus" in cmd and "all" in cmd
        assert "--ipc=host" in cmd
        # gpu args precede the image reference
        assert cmd.index("--gpus") < cmd.index("img:latest")
        assert cmd.index("--ipc=host") < cmd.index("img:latest")

    @pytest.mark.unit
    def test_apptainer_gpu_and_run_args_after_exec(self):
        from hip_cargo.utils.runner import _build_container_cmd

        cmd = _build_container_cmd(
            "apptainer",
            "img:latest",
            {},
            "/work",
            ["pkg", "cmd"],
            gpu_args=["--nv"],
            run_args=["--ipc=host"],
        )
        assert cmd[0:2] == ["apptainer", "exec"]
        assert "--nv" in cmd
        assert "--ipc=host" in cmd
        assert cmd.index("--nv") < cmd.index("docker://img:latest")

    @pytest.mark.unit
    def test_no_gpu_or_run_args_is_unchanged(self):
        from hip_cargo.utils.runner import _build_container_cmd

        cmd = _build_container_cmd("docker", "img:latest", {}, "/work", ["pkg"])
        assert "--gpus" not in cmd
        assert cmd[0:2] == ["docker", "run"]


class TestRunInContainerGpu:
    """Test run_in_container threads GPU/run-args/env into the command."""

    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch):
        monkeypatch.delenv("HIP_CARGO_GPUS", raising=False)
        monkeypatch.delenv("HIP_CARGO_RUN_ARGS", raising=False)
        monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)

    def _make_func(self):
        from hip_cargo.utils.decorators import stimela_cab

        @stimela_cab(name="test-cmd", info="test")
        def func(input_file: Annotated[File, typer.Option(..., parser=Path, help="input")]):
            pass

        return func

    @pytest.mark.unit
    def test_declared_gpu_adds_docker_flag(self, tmp_path, monkeypatch):
        from hip_cargo.utils import runner

        func = self._make_func()
        input_file = tmp_path / "data.ms"
        input_file.touch()

        monkeypatch.setattr(runner, "get_container_gpu", lambda import_name: True)
        monkeypatch.setattr(runner, "get_container_run_args", lambda import_name, rt: [])
        with (
            patch("hip_cargo.utils.runner._detect_runtime", return_value="docker"),
            patch("hip_cargo.utils.runner.subprocess.run") as mock_run,
            patch("hip_cargo.utils.runner.sys") as mock_sys,
        ):
            mock_sys.argv = ["/usr/bin/test-cmd", "--input-file", str(input_file)]
            runner.run_in_container(func, {"input_file": input_file}, image="img:v1", backend="docker")

        cmd = mock_run.call_args[0][0]
        assert "--gpus" in cmd
        assert cmd[cmd.index("--gpus") + 1] == "all"

    @pytest.mark.unit
    def test_run_args_env_override_appends(self, tmp_path, monkeypatch):
        from hip_cargo.utils import runner

        func = self._make_func()
        input_file = tmp_path / "data.ms"
        input_file.touch()

        monkeypatch.setattr(runner, "get_container_gpu", lambda import_name: False)
        monkeypatch.setattr(runner, "get_container_run_args", lambda import_name, rt: ["--shm-size=1g"])
        monkeypatch.setenv("HIP_CARGO_RUN_ARGS", "--ipc=host")
        with (
            patch("hip_cargo.utils.runner._detect_runtime", return_value="docker"),
            patch("hip_cargo.utils.runner.subprocess.run") as mock_run,
            patch("hip_cargo.utils.runner.sys") as mock_sys,
        ):
            mock_sys.argv = ["/usr/bin/test-cmd", "--input-file", str(input_file)]
            runner.run_in_container(func, {"input_file": input_file}, image="img:v1", backend="docker")

        cmd = mock_run.call_args[0][0]
        assert "--shm-size=1g" in cmd
        assert "--ipc=host" in cmd

    @pytest.mark.unit
    def test_host_cuda_visible_devices_forwarded(self, tmp_path, monkeypatch):
        from hip_cargo.utils import runner

        func = self._make_func()
        input_file = tmp_path / "data.ms"
        input_file.touch()

        monkeypatch.setattr(runner, "get_container_gpu", lambda import_name: True)
        monkeypatch.setattr(runner, "get_container_run_args", lambda import_name, rt: [])
        monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "1")
        with (
            patch("hip_cargo.utils.runner._detect_runtime", return_value="docker"),
            patch("hip_cargo.utils.runner.subprocess.run") as mock_run,
            patch("hip_cargo.utils.runner.sys") as mock_sys,
        ):
            mock_sys.argv = ["/usr/bin/test-cmd", "--input-file", str(input_file)]
            runner.run_in_container(func, {"input_file": input_file}, image="img:v1", backend="docker")

        cmd = mock_run.call_args[0][0]
        assert "-e" in cmd
        assert "CUDA_VISIBLE_DEVICES=1" in cmd
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_runner.py::TestBuildContainerCmdGpuRunArgs tests/test_runner.py::TestRunInContainerGpu -v`
Expected: FAIL (`_build_container_cmd` rejects `gpu_args` kwarg; `runner` has no `get_container_gpu`).

- [ ] **Step 3a: Add the top-level import**

In `src/hip_cargo/utils/runner.py`, add to the imports near the top (after the existing `from hip_cargo.utils.metadata import StimelaMeta` line):

```python
from hip_cargo.utils.config import get_container_gpu, get_container_run_args
```

(`shlex` was already added in Task 2. If not, add `import shlex` alongside `import shutil`.)

- [ ] **Step 3b: Replace `_build_container_cmd`**

Replace the entire `_build_container_cmd` function with:

```python
def _build_container_cmd(
    runtime: str,
    image: str,
    mounts: dict[str, bool],
    cwd: str,
    cli_args: list[str],
    cred_env: dict[str, str] | None = None,
    cred_mounts: dict[str, bool] | None = None,
    gpu_args: list[str] | None = None,
    run_args: list[str] | None = None,
) -> list[str]:
    """Assemble the full container execution command.

    Args:
        runtime: Container runtime (apptainer, singularity, docker, podman).
        image: Container image reference.
        mounts: Dict of mount paths → read-write flag.
        cwd: Working directory inside the container.
        cli_args: The CLI command + arguments to run inside the container.
        cred_env: Optional env vars to forward into the container (e.g. cloud creds).
        cred_mounts: Optional read-only credential mounts merged with ``mounts``.
        gpu_args: Optional GPU-passthrough flags, inserted after the run/exec subcommand.
        run_args: Optional extra runtime args, inserted after ``gpu_args``.
    """
    cred_env = cred_env or {}
    cred_mounts = cred_mounts or {}
    gpu_args = gpu_args or []
    run_args = run_args or []
    all_mounts = {**mounts, **cred_mounts}

    if runtime in ("apptainer", "singularity"):
        cmd = [runtime, "exec", "--pwd", cwd, *gpu_args, *run_args]
        for path, rw in sorted(all_mounts.items()):
            mode = "rw" if rw else "ro"
            cmd.extend(["--bind", f"{path}:{path}:{mode}"])
        for var, value in sorted(cred_env.items()):
            cmd.extend(["--env", f"{var}={value}"])
        # Add docker:// prefix for OCI image references
        if not image.endswith(".sif") and "://" not in image:
            image = f"docker://{image}"
        cmd.append(image)
    else:  # docker, podman
        # Run as current user so output files have correct ownership
        uid_gid = f"{os.getuid()}:{os.getgid()}"
        cmd = [runtime, "run", "--rm", "--user", uid_gid, "-w", cwd, *gpu_args, *run_args]
        for path, rw in sorted(all_mounts.items()):
            mode = "rw" if rw else "ro"
            cmd.extend(["-v", f"{path}:{path}:{mode}"])
        for var, value in sorted(cred_env.items()):
            cmd.extend(["-e", f"{var}={value}"])
        cmd.append(image)

    cmd.extend(cli_args)
    return cmd
```

- [ ] **Step 3c: Replace the body of `run_in_container`**

Replace the body of `run_in_container` (keep the existing signature and docstring) with:

```python
    runtime = _detect_runtime(backend)
    mounts = _resolve_mounts(func, params)
    protocols = _collect_remote_protocols(func, params)
    cred_env = _build_credential_env(protocols, dict(os.environ))
    cred_mounts, _gcs_keyfile = _build_credential_mounts(protocols, dict(os.environ), home=os.path.expanduser("~"))
    cwd = os.getcwd()
    # Ensure cwd is mounted read-write
    mounts[cwd] = True
    cli_args = _build_argv_with_native_backend()

    # Resolve GPU passthrough and per-backend extra run-args declared by the
    # package in its _container_image module, with env overrides.
    import_name = func.__module__.split(".")[0]
    gpu_spec = _resolve_gpu_request(get_container_gpu(import_name), runtime)
    gpu_args, gpu_env = _gpu_args(runtime, gpu_spec)
    run_args = list(get_container_run_args(import_name, runtime))
    extra_run_args = os.environ.get("HIP_CARGO_RUN_ARGS")
    if extra_run_args:
        run_args.extend(shlex.split(extra_run_args))

    # Forward host CUDA_VISIBLE_DEVICES into the container; an explicit device
    # spec (apptainer/singularity) takes precedence.
    run_env = dict(cred_env)
    host_cvd = os.environ.get("CUDA_VISIBLE_DEVICES")
    if host_cvd is not None:
        run_env.setdefault("CUDA_VISIBLE_DEVICES", host_cvd)
    run_env.update(gpu_env)

    if always_pull_images:
        _pull_image(runtime, image)

    cmd = _build_container_cmd(
        runtime,
        image,
        mounts,
        cwd,
        cli_args,
        cred_env=run_env,
        cred_mounts=cred_mounts,
        gpu_args=gpu_args,
        run_args=run_args,
    )

    print(f"Falling back to container execution ({runtime})")
    print(f"  Image: {image}")
    print(f"  Command: {' '.join(cli_args)}")
    subprocess.run(cmd, check=True)
```

- [ ] **Step 4: Run the full runner + config suite to verify it passes**

Run: `uv run pytest tests/test_runner.py tests/test_config.py tests/test_remote_uri_runner.py tests/test_container_fallback_integration.py -v`
Expected: PASS (new GPU tests pass; all pre-existing runner/credential tests still pass — defaults insert nothing).

- [ ] **Step 5: Lint**

Run: `uv run ruff format . && uv run ruff check . --fix`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/hip_cargo/utils/runner.py tests/test_runner.py
git commit -m "feat(runner): pass GPU and per-backend run-args into container cmd"
```

---
## Task 5: Scaffold the GPU / RUN_ARGS knobs in `hip-cargo init`

**Files:**
- Modify: `src/hip_cargo/core/init.py` (the `_container_image.py` writer, ~lines 156-159)
- Test: `tests/test_init.py` (extend the existing `test_init_produces_clean_project`)

**Interfaces:**
- Consumes: nothing (independent surface change).
- Produces: scaffolded `_container_image.py` carries commented `GPU` / `RUN_ARGS_*` examples; the active line remains only `CONTAINER_IMAGE = ...`.

- [ ] **Step 1: Add the failing assertion to the existing scaffold test**

In `tests/test_init.py`, inside `test_init_produces_clean_project`, immediately after the `for filepath in expected_files:` loop (before the ruff-format subprocess call), add:

```python
        # GPU / RUN_ARGS knobs are scaffolded (commented) for discoverability.
        container_image = (project_dir / f"src/{pkg}/_container_image.py").read_text()
        assert "CONTAINER_IMAGE = " in container_image
        assert "# GPU = True" in container_image
        assert "RUN_ARGS_APPTAINER" in container_image
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_init.py -v`
Expected: FAIL on `assert "# GPU = True" in container_image` (scaffold lacks the hint).

- [ ] **Step 3: Update the scaffold writer**

In `src/hip_cargo/core/init.py`, replace the `_container_image.py` writer:

```python
    _write_file(
        src_pkg / "_container_image.py",
        f'CONTAINER_IMAGE = "ghcr.io/{github_user}/{project_name}:latest"\n',
    )
```

with:

```python
    _write_file(
        src_pkg / "_container_image.py",
        (
            f'CONTAINER_IMAGE = "ghcr.io/{github_user}/{project_name}:latest"\n'
            "\n"
            "# Optional GPU passthrough for the container-fallback path.\n"
            '# Set GPU = True for a CUDA/GPU image, or "auto" to request a GPU only\n'
            "# when one is detected (and, for docker/podman, the NVIDIA Container\n"
            "# Toolkit is present). Absent => no GPU flags (the default).\n"
            "# GPU = True\n"
            "\n"
            "# Optional per-backend extra arguments, passed verbatim to the container\n"
            '# runtime during fallback. Example: RUN_ARGS_APPTAINER = ["--ipc=host"].\n'
            "# RUN_ARGS_DOCKER = []\n"
            "# RUN_ARGS_PODMAN = []\n"
            "# RUN_ARGS_APPTAINER = []\n"
            "# RUN_ARGS_SINGULARITY = []\n"
        ),
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_init.py -v`
Expected: PASS (scaffold still passes ruff format/lint; new assertions hold).

- [ ] **Step 5: Lint**

Run: `uv run ruff format . && uv run ruff check . --fix`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/hip_cargo/core/init.py tests/test_init.py
git commit -m "feat(init): scaffold commented GPU/RUN_ARGS in _container_image.py"
```

---

## Task 6: Document the feature

**Files:**
- Modify: `.claude/rules/architecture.md` (§4)
- Modify: `src/hip_cargo/templates/CLAUDE.md` (§3)

**Interfaces:**
- Consumes: nothing.
- Produces: documentation only — no code.

- [ ] **Step 1: Add two bullets to `.claude/rules/architecture.md` §4**

In `.claude/rules/architecture.md`, find the bullet that begins
`* **Mount Resolution:**` (under `## 4. Runtime Execution & Fallback`) and insert
these two bullets immediately after it:

````markdown
* **GPU passthrough (container fallback):** A package opts in by declaring `GPU` in its `_container_image.py` (`True` / `False` / `"auto"` / a device spec). `run_in_container` reads it via `get_container_gpu(func.__module__.split(".")[0])`, resolves it through `_resolve_gpu_request` (the `HIP_CARGO_GPUS` env var overrides the constant; `"auto"` adds flags only when `_gpu_available()` and — for docker/podman — `_toolkit_available()`), and maps it per-runtime via `_gpu_args`: docker `--gpus`, podman CDI `--device nvidia.com/gpu=...` (host needs `nvidia-ctk cdi generate`), apptainer/singularity `--nv` (device specs become `CUDA_VISIBLE_DEVICES`). Host `CUDA_VISIBLE_DEVICES` is forwarded. None of this touches the cab YAML or the round-trip — `GPU` lives only in `_container_image.py`.
* **Per-backend run-args (container fallback):** `RUN_ARGS_DOCKER` / `RUN_ARGS_PODMAN` / `RUN_ARGS_APPTAINER` / `RUN_ARGS_SINGULARITY` in `_container_image.py` are read via `get_container_run_args` and inserted verbatim right after the `run`/`exec` subcommand for the matching runtime. `HIP_CARGO_RUN_ARGS` (shlex-split) appends to whichever backend is active. Default `[]`.
````

- [ ] **Step 2: Add a subsection to `src/hip_cargo/templates/CLAUDE.md` §3**

In `src/hip_cargo/templates/CLAUDE.md`, find the line `### Remote URIs (S3 / GCS / Azure)` (inside `## 3. Container Fallback & Backends`) and insert this subsection immediately **before** it:

````markdown
### GPU passthrough & extra run-args

For a GPU image, declare it in `src/<PACKAGE_NAME>/_container_image.py` alongside
`CONTAINER_IMAGE`:

```python
GPU = True                  # True | False | "auto" | a device spec ("device=0,1")
RUN_ARGS_APPTAINER = []     # per-backend extras: _DOCKER / _PODMAN / _APPTAINER / _SINGULARITY
```

On the container-fallback path the runner translates `GPU` per runtime (`--gpus`
for docker, CDI `--device nvidia.com/gpu=...` for podman, `--nv` for
apptainer/singularity) and appends the matching `RUN_ARGS_*` verbatim. `"auto"`
only requests a GPU when one is detected (and, for docker/podman, the NVIDIA
Container Toolkit is present). Override per-invocation with `HIP_CARGO_GPUS`
(e.g. `HIP_CARGO_GPUS=none`) and `HIP_CARGO_RUN_ARGS`. These constants live only
in `_container_image.py` — they are deliberately kept out of the cab YAML, since
Stimela manages its own container execution.

````

- [ ] **Step 3: Verify the inserts landed**

Run:
```bash
grep -n "GPU passthrough (container fallback)" .claude/rules/architecture.md
grep -n "GPU passthrough & extra run-args" src/hip_cargo/templates/CLAUDE.md
```
Expected: one match each.

- [ ] **Step 4: Lint**

Run: `uv run ruff format . && uv run ruff check . --fix`
Expected: no errors (docs only; nothing for ruff to change).

- [ ] **Step 5: Commit**

```bash
git add .claude/rules/architecture.md src/hip_cargo/templates/CLAUDE.md
git commit -m "docs: document GPU passthrough and per-backend run-args"
```

---
## Task 7: Opt-in live GPU smoke test

**Files:**
- Create: `tests/test_gpu_live.py`

**Interfaces:**
- Consumes: `_detect_runtime`, `_resolve_gpu_request`, `_gpu_args`, `_build_container_cmd` (Tasks 2-4).
- Produces: nothing consumed downstream.

This test is **excluded from required CI** — it only runs when `HIP_CARGO_LIVE_GPU`
is set, and skips cleanly when there is no runtime or no GPU. It is the one check
that confirms the assembled command actually exposes the GPU inside a container.

- [ ] **Step 1: Create the test file**

Create `tests/test_gpu_live.py`:

```python
"""Opt-in live GPU smoke test for the container fallback.

Runs only when HIP_CARGO_LIVE_GPU is set; excluded from required CI. Confirms
that a command assembled with our GPU flags actually sees the GPU inside a
container. Override the test image with HIP_CARGO_LIVE_GPU_IMAGE.
"""

import os
import subprocess

import pytest

from hip_cargo.utils.runner import (
    _build_container_cmd,
    _detect_runtime,
    _gpu_args,
    _resolve_gpu_request,
)

LIVE = os.environ.get("HIP_CARGO_LIVE_GPU")
IMAGE = os.environ.get("HIP_CARGO_LIVE_GPU_IMAGE", "nvidia/cuda:13.0.0-runtime-ubuntu24.04")


@pytest.mark.skipif(not LIVE, reason="set HIP_CARGO_LIVE_GPU=1 to run the live GPU test")
def test_gpu_visible_in_container():
    try:
        runtime = _detect_runtime("auto")
    except RuntimeError:
        pytest.skip("no container runtime available")

    spec = _resolve_gpu_request("auto", runtime)
    if spec is None:
        pytest.skip("no GPU / container toolkit detected on host")

    gpu_args, gpu_env = _gpu_args(runtime, spec)
    cmd = _build_container_cmd(
        runtime,
        IMAGE,
        {},
        "/",
        ["nvidia-smi", "-L"],
        cred_env=gpu_env,
        gpu_args=gpu_args,
    )

    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"command failed:\n{' '.join(cmd)}\n{result.stderr}"
    assert "GPU" in result.stdout, f"no GPU listed in output:\n{result.stdout}"
```

- [ ] **Step 2: Confirm it skips by default**

Run: `uv run pytest tests/test_gpu_live.py -v`
Expected: SKIPPED ("set HIP_CARGO_LIVE_GPU=1 ...").

- [ ] **Step 3: (Manual, on a GPU host only) confirm it passes live**

Run: `HIP_CARGO_LIVE_GPU=1 uv run pytest tests/test_gpu_live.py -v`
Expected on a GPU host with a runtime + toolkit: PASS. Elsewhere: SKIPPED.

- [ ] **Step 4: Lint**

Run: `uv run ruff format . && uv run ruff check . --fix`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add tests/test_gpu_live.py
git commit -m "test: add opt-in live GPU container smoke test"
```

---

## Final verification

- [ ] **Run the full suite (excluding the live test, which self-skips):**

Run: `uv run pytest -v`
Expected: all PASS; `tests/test_gpu_live.py::test_gpu_visible_in_container` SKIPPED.

- [ ] **Final lint:**

Run: `uv run ruff format . && uv run ruff check .`
Expected: clean.

---

## Spec Coverage Map

| Spec section | Task(s) |
|---|---|
| Declaration surface (`GPU`, per-backend `RUN_ARGS_*`) | 1 (readers), 5 (scaffold) |
| Readers (`get_container_gpu`, `get_container_run_args`) | 1 |
| Resolution + env overrides (`HIP_CARGO_GPUS`, `HIP_CARGO_RUN_ARGS`) | 2 (gpu), 4 (run-args) |
| Conservative auto-detection (`_gpu_available` + `_toolkit_available`) | 2 |
| Per-runtime GPU mapping (`--gpus` / CDI / `--nv`, `CUDA_VISIBLE_DEVICES`) | 3 (mapping), 4 (host-env forward) |
| Command assembly (placement after subcommand) | 4 |
| Reads via `func.__module__` (no signature/call-site change) | 4 |
| Backward compatibility (absent constants → today's behaviour) | 1, 4 (defaults), verified across 4's regression run |
| Testing (unit) | 1, 2, 3, 4, 5 |
| Testing (opt-in live) | 7 |
| Docs (`architecture.md`, template `CLAUDE.md`) | 6 |

**kremetart follow-up** (separate PR, not in this plan): add `GPU = True` to
kremetart's `_container_image.py`.
