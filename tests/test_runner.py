"""Tests for container fallback runner."""

from pathlib import Path
from typing import Annotated, NewType
from unittest.mock import patch

import pytest
import typer

from hip_cargo.utils.runner import (
    _build_argv_with_native_backend,
    _build_container_cmd,
    _detect_runtime,
    _gpu_args,
    _is_path_type,
    _prune_child_mounts,
    _pull_image,
    _resolve_gpu_request,
    _resolve_mountable_ancestor,
    _resolve_mounts,
    run_in_container,
)

File = NewType("File", Path)
Directory = NewType("Directory", Path)
MS = NewType("MS", Path)


class TestIsPathType:
    """Test _is_path_type with various type hints."""

    @pytest.mark.unit
    def test_plain_path(self):
        assert _is_path_type(Path) is True

    @pytest.mark.unit
    def test_newtype_file(self):
        assert _is_path_type(File) is True

    @pytest.mark.unit
    def test_newtype_directory(self):
        assert _is_path_type(Directory) is True

    @pytest.mark.unit
    def test_newtype_ms(self):
        assert _is_path_type(MS) is True

    @pytest.mark.unit
    def test_str_not_path(self):
        assert _is_path_type(str) is False

    @pytest.mark.unit
    def test_int_not_path(self):
        assert _is_path_type(int) is False

    @pytest.mark.unit
    def test_float_not_path(self):
        assert _is_path_type(float) is False

    @pytest.mark.unit
    def test_optional_file(self):
        assert _is_path_type(File | None) is True

    @pytest.mark.unit
    def test_optional_str(self):
        assert _is_path_type(str | None) is False

    @pytest.mark.unit
    def test_list_file(self):
        assert _is_path_type(list[File]) is True

    @pytest.mark.unit
    def test_list_str(self):
        assert _is_path_type(list[str]) is False

    @pytest.mark.unit
    def test_annotated_file(self):
        assert _is_path_type(Annotated[File, typer.Option(help="test")]) is True

    @pytest.mark.unit
    def test_annotated_str(self):
        assert _is_path_type(Annotated[str, typer.Option(help="test")]) is False

    @pytest.mark.unit
    def test_annotated_optional_file(self):
        assert _is_path_type(Annotated[File | None, typer.Option(help="test")]) is True


class TestResolveMounts:
    """Test _resolve_mounts with decorated functions."""

    @pytest.mark.unit
    def test_input_file_mounted_readonly(self, tmp_path):
        from hip_cargo.utils.decorators import stimela_cab

        @stimela_cab(name="test", info="test")
        def func(input_file: Annotated[File, typer.Option(..., parser=Path, help="input")]):
            pass

        input_file = tmp_path / "data.ms"
        input_file.touch()
        mounts = _resolve_mounts(func, {"input_file": input_file})
        assert str(tmp_path) in mounts
        assert mounts[str(tmp_path)] is False  # read-only

    @pytest.mark.unit
    def test_output_dir_mounted_readwrite(self, tmp_path):
        from hip_cargo.utils.decorators import stimela_cab, stimela_output

        @stimela_cab(name="test", info="test")
        @stimela_output(name="output-dir", dtype="Directory", info="output")
        def func(output_dir: Annotated[Directory | None, typer.Option(parser=Path, help="output")] = None):
            pass

        output_dir = tmp_path / "results"
        output_dir.mkdir()
        mounts = _resolve_mounts(func, {"output_dir": output_dir})
        assert str(output_dir) in mounts
        assert mounts[str(output_dir)] is True  # read-write

    @pytest.mark.unit
    def test_write_parent_mounts_parent_rw(self, tmp_path):
        """When path_policies.write_parent is True, mount parent dir rw instead of the path itself."""
        from hip_cargo.utils.decorators import stimela_cab, stimela_output

        @stimela_cab(name="test", info="test")
        @stimela_output(
            name="output-dataset",
            dtype="Directory",
            info="output",
            must_exist=True,
            path_policies={"write_parent": True},
        )
        def func(
            output_dataset: Annotated[
                Directory,
                typer.Option(..., parser=Path, help="output"),
                {"stimela": {"must_exist": True, "path_policies": {"write_parent": True}}},
            ],
        ):
            pass

        output_dir = tmp_path / "results"
        output_dir.mkdir()
        mounts = _resolve_mounts(func, {"output_dataset": output_dir})
        # Parent should be mounted rw, NOT the directory itself
        assert str(tmp_path) in mounts
        assert mounts[str(tmp_path)] is True
        assert str(output_dir) not in mounts

    @pytest.mark.unit
    def test_nonexistent_output_mounts_parent(self, tmp_path):
        """When output path doesn't exist, mount parent directory."""
        from hip_cargo.utils.decorators import stimela_cab, stimela_output

        @stimela_cab(name="test", info="test")
        @stimela_output(name="output-dir", dtype="Directory", info="output")
        def func(output_dir: Annotated[Directory | None, typer.Option(parser=Path, help="output")] = None):
            pass

        output_dir = tmp_path / "does_not_exist"
        mounts = _resolve_mounts(func, {"output_dir": output_dir})
        assert str(tmp_path) in mounts
        assert mounts[str(tmp_path)] is True

    @pytest.mark.unit
    def test_none_params_skipped(self):
        from hip_cargo.utils.decorators import stimela_cab

        @stimela_cab(name="test", info="test")
        def func(output_dir: Annotated[Directory | None, typer.Option(parser=Path, help="output")] = None):
            pass

        mounts = _resolve_mounts(func, {"output_dir": None})
        assert len(mounts) == 0

    @pytest.mark.unit
    def test_non_path_params_skipped(self):
        from hip_cargo.utils.decorators import stimela_cab

        @stimela_cab(name="test", info="test")
        def func(threshold: Annotated[float, typer.Option(help="threshold")] = 0.5):
            pass

        mounts = _resolve_mounts(func, {"threshold": 0.5})
        assert len(mounts) == 0


class TestBuildArgv:
    """Test _build_argv_with_native_backend."""

    @pytest.mark.unit
    def test_appends_backend_native(self):
        with patch("hip_cargo.utils.runner.sys") as mock_sys:
            mock_sys.argv = ["/usr/bin/pkg", "my-cmd", "--input-file", "/data/input.ms"]
            args = _build_argv_with_native_backend()
        assert args == ["pkg", "my-cmd", "--input-file", "/data/input.ms", "--backend", "native"]

    @pytest.mark.unit
    def test_replaces_existing_backend(self):
        with patch("hip_cargo.utils.runner.sys") as mock_sys:
            mock_sys.argv = ["/usr/bin/pkg", "my-cmd", "--backend", "auto", "--input-file", "/data/input.ms"]
            args = _build_argv_with_native_backend()
        assert args == ["pkg", "my-cmd", "--backend", "native", "--input-file", "/data/input.ms"]

    @pytest.mark.unit
    def test_replaces_equals_form_backend(self):
        with patch("hip_cargo.utils.runner.sys") as mock_sys:
            mock_sys.argv = ["/usr/bin/pkg", "my-cmd", "--backend=auto", "--input-file", "/data/input.ms"]
            args = _build_argv_with_native_backend()
        assert args == ["pkg", "my-cmd", "--backend=native", "--input-file", "/data/input.ms"]


class TestBuildContainerCmd:
    """Test _build_container_cmd for different runtimes."""

    @pytest.mark.unit
    def test_apptainer_cmd(self):
        mounts = {"/data": False, "/output": True}
        cli_args = ["pkg", "my-cmd", "--input-file", "/data/in.ms", "--backend", "native"]
        cmd = _build_container_cmd("apptainer", "ghcr.io/user/pkg:latest", mounts, "/work", cli_args)

        assert cmd[0] == "apptainer"
        assert cmd[1] == "exec"
        assert "--pwd" in cmd
        assert "docker://ghcr.io/user/pkg:latest" in cmd
        # Check mounts
        assert "--bind" in cmd
        bind_idx = [i for i, x in enumerate(cmd) if x == "--bind"]
        bind_values = [cmd[i + 1] for i in bind_idx]
        assert "/data:/data:ro" in bind_values
        assert "/output:/output:rw" in bind_values
        # CLI args at the end
        assert cmd[-len(cli_args) :] == cli_args

    @pytest.mark.unit
    def test_docker_cmd(self):
        mounts = {"/data": False}
        cli_args = ["pkg", "my-cmd", "--backend", "native"]
        cmd = _build_container_cmd("docker", "ghcr.io/user/pkg:latest", mounts, "/work", cli_args)

        assert cmd[0] == "docker"
        assert cmd[1] == "run"
        assert "--rm" in cmd
        assert "-w" in cmd
        assert "ghcr.io/user/pkg:latest" in cmd  # no docker:// prefix
        assert "-v" in cmd

    @pytest.mark.unit
    def test_sif_image_no_prefix(self):
        cmd = _build_container_cmd("apptainer", "/path/to/image.sif", {}, "/work", ["pkg"])
        assert "/path/to/image.sif" in cmd
        assert "docker:///path/to/image.sif" not in cmd


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

    @pytest.mark.unit
    def test_always_pull_images_triggers_pull(self, tmp_path):
        """When always_pull_images=True, _pull_image should be called before run."""
        from hip_cargo.utils.decorators import stimela_cab

        @stimela_cab(name="test-cmd", info="test")
        def func(input_file: Annotated[File, typer.Option(..., parser=Path, help="input")]):
            pass

        input_file = tmp_path / "data.ms"
        input_file.touch()

        with (
            patch("hip_cargo.utils.runner._detect_runtime", return_value="docker"),
            patch("hip_cargo.utils.runner._pull_image") as mock_pull,
            patch("hip_cargo.utils.runner.subprocess.run"),
            patch("hip_cargo.utils.runner.sys") as mock_sys,
        ):
            mock_sys.argv = ["/usr/bin/test-cmd", "--input-file", str(input_file)]
            run_in_container(
                func,
                {"input_file": input_file},
                image="ghcr.io/test/pkg:v1.0",
                backend="docker",
                always_pull_images=True,
            )
            mock_pull.assert_called_once_with("docker", "ghcr.io/test/pkg:v1.0")

    @pytest.mark.unit
    def test_no_pull_by_default(self, tmp_path):
        """When always_pull_images is False (default), _pull_image should not be called."""
        from hip_cargo.utils.decorators import stimela_cab

        @stimela_cab(name="test-cmd", info="test")
        def func(input_file: Annotated[File, typer.Option(..., parser=Path, help="input")]):
            pass

        input_file = tmp_path / "data.ms"
        input_file.touch()

        with (
            patch("hip_cargo.utils.runner._detect_runtime", return_value="docker"),
            patch("hip_cargo.utils.runner._pull_image") as mock_pull,
            patch("hip_cargo.utils.runner.subprocess.run"),
            patch("hip_cargo.utils.runner.sys") as mock_sys,
        ):
            mock_sys.argv = ["/usr/bin/test-cmd", "--input-file", str(input_file)]
            run_in_container(
                func,
                {"input_file": input_file},
                image="ghcr.io/test/pkg:v1.0",
                backend="docker",
            )
            mock_pull.assert_not_called()


class TestDetectRuntime:
    """Test _detect_runtime for auto-detection and explicit backends."""

    @pytest.mark.unit
    def test_explicit_backend_found(self):
        with patch("hip_cargo.utils.runner.shutil.which", return_value="/usr/bin/docker"):
            assert _detect_runtime("docker") == "docker"

    @pytest.mark.unit
    def test_explicit_backend_not_found(self):
        with patch("hip_cargo.utils.runner.shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="not found on PATH"):
                _detect_runtime("docker")

    @pytest.mark.unit
    def test_auto_finds_first_available(self):
        """Auto mode should return the first runtime found in priority order."""

        def which_side_effect(name):
            # Simulate only docker being available
            return "/usr/bin/docker" if name == "docker" else None

        with patch("hip_cargo.utils.runner.shutil.which", side_effect=which_side_effect):
            assert _detect_runtime("auto") == "docker"

    @pytest.mark.unit
    def test_auto_prefers_apptainer(self):
        """Apptainer should be preferred over docker when both are available."""

        def which_side_effect(name):
            return f"/usr/bin/{name}" if name in ("apptainer", "docker") else None

        with patch("hip_cargo.utils.runner.shutil.which", side_effect=which_side_effect):
            assert _detect_runtime("auto") == "apptainer"

    @pytest.mark.unit
    def test_auto_no_runtime_found(self):
        with patch("hip_cargo.utils.runner.shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="No container runtime found"):
                _detect_runtime("auto")


class TestPullImage:
    """Test _pull_image for different runtimes."""

    @pytest.mark.unit
    def test_docker_pull(self):
        with patch("hip_cargo.utils.runner.subprocess.run") as mock_run:
            _pull_image("docker", "ghcr.io/user/repo:latest")
        mock_run.assert_called_once_with(["docker", "pull", "ghcr.io/user/repo:latest"], check=True)

    @pytest.mark.unit
    def test_podman_pull(self):
        with patch("hip_cargo.utils.runner.subprocess.run") as mock_run:
            _pull_image("podman", "ghcr.io/user/repo:latest")
        mock_run.assert_called_once_with(["podman", "pull", "ghcr.io/user/repo:latest"], check=True)

    @pytest.mark.unit
    def test_apptainer_pull_adds_docker_prefix(self):
        with patch("hip_cargo.utils.runner.subprocess.run") as mock_run:
            _pull_image("apptainer", "ghcr.io/user/repo:latest")
        mock_run.assert_called_once_with(
            ["apptainer", "pull", "--force", "docker://ghcr.io/user/repo:latest"], check=True
        )

    @pytest.mark.unit
    def test_apptainer_pull_sif_no_prefix(self):
        with patch("hip_cargo.utils.runner.subprocess.run") as mock_run:
            _pull_image("apptainer", "/path/to/image.sif")
        mock_run.assert_called_once_with(["apptainer", "pull", "--force", "/path/to/image.sif"], check=True)

    @pytest.mark.unit
    def test_singularity_pull_adds_docker_prefix(self):
        with patch("hip_cargo.utils.runner.subprocess.run") as mock_run:
            _pull_image("singularity", "ghcr.io/user/repo:v1")
        mock_run.assert_called_once_with(
            ["singularity", "pull", "--force", "docker://ghcr.io/user/repo:v1"], check=True
        )

    @pytest.mark.unit
    def test_apptainer_pull_with_protocol_no_extra_prefix(self):
        """If image already has a protocol prefix, don't add docker://."""
        with patch("hip_cargo.utils.runner.subprocess.run") as mock_run:
            _pull_image("apptainer", "oras://ghcr.io/user/repo:v1")
        mock_run.assert_called_once_with(["apptainer", "pull", "--force", "oras://ghcr.io/user/repo:v1"], check=True)


class TestPruneChildMounts:
    """Test _prune_child_mounts removes redundant child mounts."""

    @pytest.mark.unit
    def test_child_removed_when_parent_has_same_privilege(self):
        mounts = {"/data": False, "/data/subdir": False}
        _prune_child_mounts(mounts)
        assert "/data" in mounts
        assert "/data/subdir" not in mounts

    @pytest.mark.unit
    def test_child_removed_when_parent_has_higher_privilege(self):
        mounts = {"/data": True, "/data/subdir": False}
        _prune_child_mounts(mounts)
        assert "/data" in mounts
        assert "/data/subdir" not in mounts

    @pytest.mark.unit
    def test_child_kept_when_it_has_higher_privilege(self):
        """rw child under ro parent should be kept."""
        mounts = {"/data": False, "/data/subdir": True}
        _prune_child_mounts(mounts)
        assert "/data" in mounts
        assert "/data/subdir" in mounts

    @pytest.mark.unit
    def test_deeply_nested_child_removed(self):
        mounts = {"/data": True, "/data/a/b/c": False}
        _prune_child_mounts(mounts)
        assert "/data" in mounts
        assert "/data/a/b/c" not in mounts

    @pytest.mark.unit
    def test_unrelated_paths_unaffected(self):
        mounts = {"/data": False, "/output": True}
        _prune_child_mounts(mounts)
        assert "/data" in mounts
        assert "/output" in mounts

    @pytest.mark.unit
    def test_empty_mounts(self):
        mounts = {}
        _prune_child_mounts(mounts)
        assert mounts == {}


class TestResolveMountableAncestor:
    """Test _resolve_mountable_ancestor walk-up helper."""

    @pytest.mark.unit
    def test_returns_path_itself_when_existing(self, tmp_path):
        assert _resolve_mountable_ancestor(tmp_path) == tmp_path

    @pytest.mark.unit
    def test_walks_up_one_level(self, tmp_path):
        missing = tmp_path / "missing"
        assert _resolve_mountable_ancestor(missing) == tmp_path

    @pytest.mark.unit
    def test_walks_up_multiple_levels(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c"
        assert _resolve_mountable_ancestor(deep) == tmp_path

    @pytest.mark.unit
    def test_raises_when_only_root_exists(self):
        """If walk-up reaches the filesystem root without finding a directory, refuse."""
        with patch.object(Path, "is_dir", return_value=False):
            with pytest.raises(RuntimeError, match="No mountable directory ancestor"):
                _resolve_mountable_ancestor(Path("/foo/bar/baz"))

    @pytest.mark.unit
    def test_walks_past_a_regular_file(self, tmp_path):
        """A file at an intermediate position is walked past, not returned as a mount point."""
        intermediate_file = tmp_path / "not_a_dir"
        intermediate_file.write_text("hi")
        # Path goes through the file as if it were a dir — pathologically constructed.
        through_file = intermediate_file / "child" / "leaf"
        # Should walk up past the file and return tmp_path (the nearest real directory).
        assert _resolve_mountable_ancestor(through_file) == tmp_path


class TestResolveGpuRequest:
    """Test _resolve_gpu_request normalisation, env override, and auto gating."""

    @pytest.fixture(autouse=True)
    def _clear_env(self, monkeypatch):
        monkeypatch.delenv("HIP_CARGO_GPUS", raising=False)

    @pytest.mark.unit
    def test_false_is_none(self):
        assert _resolve_gpu_request(False, "docker") is None

    @pytest.mark.unit
    def test_true_is_all(self):
        assert _resolve_gpu_request(True, "docker") == "all"

    @pytest.mark.unit
    def test_string_all_and_none(self):
        assert _resolve_gpu_request("all", "docker") == "all"
        assert _resolve_gpu_request("none", "docker") is None

    @pytest.mark.unit
    def test_device_spec_passthrough(self):
        assert _resolve_gpu_request("device=0,1", "docker") == "device=0,1"

    @pytest.mark.unit
    def test_env_override_wins(self, monkeypatch):
        monkeypatch.setenv("HIP_CARGO_GPUS", "none")
        assert _resolve_gpu_request(True, "docker") is None

    @pytest.mark.unit
    def test_env_override_to_all(self, monkeypatch):
        from hip_cargo.utils.runner import _resolve_gpu_request

        monkeypatch.setenv("HIP_CARGO_GPUS", "all")
        assert _resolve_gpu_request(False, "docker") == "all"

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
        assert runner._resolve_gpu_request("auto", "singularity") == "all"

    @pytest.mark.unit
    def test_gpu_available_detects_nvidia_smi(self, monkeypatch):
        from hip_cargo.utils import runner

        monkeypatch.setattr(
            runner.shutil, "which", lambda name: "/usr/bin/nvidia-smi" if name == "nvidia-smi" else None
        )
        monkeypatch.setattr(runner.os.path, "exists", lambda p: False)
        assert runner._gpu_available() is True

    @pytest.mark.unit
    def test_gpu_available_false_when_absent(self, monkeypatch):
        from hip_cargo.utils import runner

        monkeypatch.setattr(runner.shutil, "which", lambda name: None)
        monkeypatch.setattr(runner.os.path, "exists", lambda p: False)
        assert runner._gpu_available() is False

    @pytest.mark.unit
    def test_gpu_available_detects_dev_node(self, monkeypatch):
        from hip_cargo.utils import runner

        monkeypatch.setattr(runner.shutil, "which", lambda name: None)
        monkeypatch.setattr(runner.os.path, "exists", lambda p: p == "/dev/nvidia0")
        assert runner._gpu_available() is True

    @pytest.mark.unit
    def test_walks_past_a_broken_symlink(self, tmp_path):
        """A broken symlink at an intermediate position is walked past."""
        target = tmp_path / "deleted"
        target.write_text("hi")
        link = tmp_path / "broken_link"
        link.symlink_to(target)
        target.unlink()  # link now points at nothing
        # is_dir() returns False on a broken symlink
        assert _resolve_mountable_ancestor(link / "child") == tmp_path


class TestResolveMountsWalkUp:
    """_resolve_mounts should walk up to an existing ancestor when intermediate dirs are missing."""

    @pytest.mark.unit
    def test_nested_missing_output_walks_up(self, tmp_path):
        """Output path with multiple missing ancestors mounts the deepest existing one."""
        from hip_cargo.utils.decorators import stimela_cab, stimela_output

        @stimela_cab(name="test", info="test")
        @stimela_output(name="output_dir", dtype="Directory", info="output")
        def func(output_dir: Annotated[Directory | None, typer.Option(parser=Path, help="o")] = None):
            pass

        deep = tmp_path / "a" / "b" / "c" / "results"
        mounts = _resolve_mounts(func, {"output_dir": deep})
        assert str(tmp_path) in mounts
        assert mounts[str(tmp_path)] is True

    @pytest.mark.unit
    def test_mkdir_with_missing_parent_walks_up(self, tmp_path):
        """mkdir=True with a missing parent should still find an existing ancestor to mount rw."""
        from hip_cargo.utils.decorators import stimela_cab

        @stimela_cab(name="test", info="test")
        def func(
            output_dir: Annotated[
                Directory | None,
                typer.Option(parser=Path, help="o"),
                {"stimela": {"mkdir": True}},
            ] = None,
        ):
            pass

        deep = tmp_path / "missing_intermediate" / "leaf"
        mounts = _resolve_mounts(func, {"output_dir": deep})
        assert str(tmp_path) in mounts
        assert mounts[str(tmp_path)] is True

    @pytest.mark.unit
    def test_write_parent_with_missing_parent_walks_up(self, tmp_path):
        """write_parent with a missing parent should walk up to the deepest existing ancestor."""
        from hip_cargo.utils.decorators import stimela_cab, stimela_output

        @stimela_cab(name="test", info="test")
        @stimela_output(
            name="result",
            dtype="Directory",
            info="r",
            path_policies={"write_parent": True},
        )
        def func(
            result: Annotated[
                Directory,
                typer.Option(..., parser=Path, help="r"),
                {"stimela": {"path_policies": {"write_parent": True}}},
            ],
        ):
            pass

        deep = tmp_path / "a" / "b" / "result_dir"
        mounts = _resolve_mounts(func, {"result": deep})
        assert str(tmp_path) in mounts
        assert mounts[str(tmp_path)] is True

    @pytest.mark.unit
    def test_walk_up_prunes_existing_child_mounts(self, tmp_path):
        """When walk-up adds a broader rw ancestor, narrower mounts are pruned (existing behavior)."""
        from hip_cargo.utils.decorators import stimela_cab, stimela_output

        existing_input = tmp_path / "inputs"
        existing_input.mkdir()

        @stimela_cab(name="test", info="test")
        @stimela_output(name="output_dir", dtype="Directory", info="o")
        def func(
            input_dir: Annotated[Directory, typer.Option(..., parser=Path, help="i")],
            output_dir: Annotated[Directory | None, typer.Option(parser=Path, help="o")] = None,
        ):
            pass

        # Output path's parent doesn't exist — walk-up lands on tmp_path
        deep_output = tmp_path / "missing" / "results"
        mounts = _resolve_mounts(func, {"input_dir": existing_input, "output_dir": deep_output})
        # tmp_path mounted rw subsumes the inputs subdir
        assert mounts.get(str(tmp_path)) is True
        assert str(existing_input) not in mounts


class TestResolveMountsImplicit:
    """Test _resolve_mounts handles implicit outputs (no corresponding CLI param)."""

    @pytest.mark.unit
    def test_string_template_mounts_parent_rw(self, tmp_path):
        """File template renders against params; parent of result is mounted rw."""
        from hip_cargo.utils.decorators import stimela_cab, stimela_output

        @stimela_cab(name="test", info="test")
        @stimela_output(name="result", dtype="File", implicit="{outdir}/run.fits")
        def func(outdir: Annotated[Directory, typer.Option(..., parser=Path, help="out")]):
            pass

        outdir = tmp_path / "outputs"
        outdir.mkdir()
        mounts = _resolve_mounts(func, {"outdir": outdir})
        assert str(outdir) in mounts
        assert mounts[str(outdir)] is True

    @pytest.mark.unit
    def test_implicit_true_skipped(self, tmp_path):
        """implicit=True (no path template) should not produce a mount."""
        from hip_cargo.utils.decorators import stimela_cab, stimela_output

        @stimela_cab(name="test", info="test")
        @stimela_output(name="result", dtype="File", implicit=True)
        def func(prefix: Annotated[str, typer.Option(..., help="p")]):
            pass

        mounts = _resolve_mounts(func, {"prefix": "run1"})
        assert mounts == {}

    @pytest.mark.unit
    def test_non_path_dtype_skipped(self):
        """Implicit output with non-path dtype should not produce a mount even with a template."""
        from hip_cargo.utils.decorators import stimela_cab, stimela_output

        @stimela_cab(name="test", info="test")
        @stimela_output(name="metric", dtype="float", implicit="{prefix}_metric.txt")
        def func(prefix: Annotated[str, typer.Option(..., help="p")]):
            pass

        mounts = _resolve_mounts(func, {"prefix": "run1"})
        assert mounts == {}

    @pytest.mark.unit
    def test_existing_directory_mounted_rw_directly(self, tmp_path):
        """Implicit Directory that already exists should be mounted rw on itself."""
        from hip_cargo.utils.decorators import stimela_cab, stimela_output

        existing = tmp_path / "outputs"
        existing.mkdir()

        @stimela_cab(name="test", info="test")
        @stimela_output(name="output_dir", dtype="Directory", implicit=str(existing))
        def func(prefix: Annotated[str, typer.Option(..., help="p")]):
            pass

        mounts = _resolve_mounts(func, {"prefix": "run1"})
        assert str(existing) in mounts
        assert mounts[str(existing)] is True

    @pytest.mark.unit
    def test_mkdir_mounts_parent_rw(self, tmp_path):
        """Implicit Directory with mkdir=True should mount parent rw."""
        from hip_cargo.utils.decorators import stimela_cab, stimela_output

        @stimela_cab(name="test", info="test")
        @stimela_output(
            name="output_dir",
            dtype="Directory",
            implicit="{outdir}/results",
            mkdir=True,
        )
        def func(outdir: Annotated[Directory, typer.Option(..., parser=Path, help="out")]):
            pass

        outdir = tmp_path / "wrk"
        outdir.mkdir()
        mounts = _resolve_mounts(func, {"outdir": outdir})
        # parent of {outdir}/results == outdir, mounted rw because of mkdir
        assert str(outdir) in mounts
        assert mounts[str(outdir)] is True

    @pytest.mark.unit
    def test_must_exist_missing_raises(self, tmp_path):
        """Implicit output with must_exist=True and missing path should raise."""
        from hip_cargo.utils.decorators import stimela_cab, stimela_output

        @stimela_cab(name="test", info="test")
        @stimela_output(
            name="result",
            dtype="File",
            implicit="{outdir}/result.fits",
            must_exist=True,
        )
        def func(outdir: Annotated[Directory, typer.Option(..., parser=Path, help="out")]):
            pass

        outdir = tmp_path / "wrk"
        outdir.mkdir()  # parent exists, but result.fits does not
        with pytest.raises(RuntimeError, match="does not exist"):
            _resolve_mounts(func, {"outdir": outdir})

    @pytest.mark.unit
    def test_unresolvable_template_silently_skipped(self):
        """Template referencing a missing param should be silently skipped."""
        from hip_cargo.utils.decorators import stimela_cab, stimela_output

        @stimela_cab(name="test", info="test")
        @stimela_output(
            name="result",
            dtype="File",
            implicit="{nonexistent}/result.fits",
        )
        def func(prefix: Annotated[str, typer.Option(..., help="p")]):
            pass

        mounts = _resolve_mounts(func, {"prefix": "run1"})
        assert mounts == {}

    @pytest.mark.unit
    def test_remote_scheme_skipped(self):
        """Implicit output that resolves to a remote URI should be skipped."""
        from hip_cargo.utils.decorators import stimela_cab, stimela_output

        @stimela_cab(name="test", info="test")
        @stimela_output(name="result", dtype="File", implicit="s3://bucket/{prefix}.fits")
        def func(prefix: Annotated[str, typer.Option(..., help="p")]):
            pass

        mounts = _resolve_mounts(func, {"prefix": "run1"})
        assert mounts == {}

    @pytest.mark.unit
    def test_write_parent_policy(self, tmp_path):
        """Implicit output with path_policies.write_parent=True mounts parent rw."""
        from hip_cargo.utils.decorators import stimela_cab, stimela_output

        target = tmp_path / "outputs"
        target.mkdir()

        @stimela_cab(name="test", info="test")
        @stimela_output(
            name="result",
            dtype="Directory",
            implicit=str(target),
            path_policies={"write_parent": True},
        )
        def func(prefix: Annotated[str, typer.Option(..., help="p")]):
            pass

        mounts = _resolve_mounts(func, {"prefix": "run1"})
        # write_parent → parent of target mounted rw, target itself NOT mounted
        assert str(tmp_path) in mounts
        assert mounts[str(tmp_path)] is True
        assert str(target) not in mounts

    @pytest.mark.unit
    def test_name_collision_with_param_uses_param_loop(self, tmp_path):
        """If the output name matches a CLI param, the param loop handles it (no double-process)."""
        from hip_cargo.utils.decorators import stimela_cab, stimela_output

        @stimela_cab(name="test", info="test")
        @stimela_output(name="output_dir", dtype="Directory", implicit="{prefix}_out")
        def func(
            output_dir: Annotated[Directory | None, typer.Option(parser=Path, help="out")] = None,
            prefix: Annotated[str, typer.Option(..., help="p")] = "x",
        ):
            pass

        explicit_out = tmp_path / "explicit"
        explicit_out.mkdir()
        mounts = _resolve_mounts(func, {"output_dir": explicit_out, "prefix": "x"})
        # The explicit param's path is mounted rw via the param loop
        assert str(explicit_out) in mounts
        assert mounts[str(explicit_out)] is True
        # The implicit-rendered path must NOT also appear as a separate mount
        rendered = (Path.cwd() / "x_out").resolve()
        assert str(rendered) not in mounts

    @pytest.mark.unit
    def test_implicit_walks_up_through_missing_ancestors(self, tmp_path):
        """Implicit output rendering to a path with missing ancestors walks up."""
        from hip_cargo.utils.decorators import stimela_cab, stimela_output

        @stimela_cab(name="test", info="test")
        @stimela_output(name="result", dtype="File", implicit="{outdir}/missing/leaf.fits")
        def func(outdir: Annotated[Directory, typer.Option(..., parser=Path, help="o")]):
            pass

        outdir = tmp_path / "wrk"
        outdir.mkdir()
        # rendered: {outdir}/missing/leaf.fits — neither leaf nor "missing" exist
        mounts = _resolve_mounts(func, {"outdir": outdir})
        assert str(outdir) in mounts
        assert mounts[str(outdir)] is True

    @pytest.mark.unit
    def test_ms_dtype_treated_as_path(self, tmp_path):
        """MS dtype should be treated as a path."""
        from hip_cargo.utils.decorators import stimela_cab, stimela_output

        @stimela_cab(name="test", info="test")
        @stimela_output(name="output_ms", dtype="MS", implicit="{outdir}/run.ms")
        def func(outdir: Annotated[Directory, typer.Option(..., parser=Path, help="out")]):
            pass

        outdir = tmp_path / "wrk"
        outdir.mkdir()
        mounts = _resolve_mounts(func, {"outdir": outdir})
        assert str(outdir) in mounts
        assert mounts[str(outdir)] is True


class TestResolveMountsAccessParent:
    """Test _resolve_mounts with access_parent policy."""

    @pytest.mark.unit
    def test_access_parent_adds_parent_ro(self, tmp_path):
        """access_parent should add the input directory's parent as read-only."""
        from hip_cargo.utils.decorators import stimela_cab

        @stimela_cab(name="test", info="test")
        def func(
            input_dir: Annotated[
                Directory,
                typer.Option(..., parser=Path, help="input"),
                {"stimela": {"path_policies": {"access_parent": True}}},
            ],
        ):
            pass

        input_dir = tmp_path / "parent" / "subdir"
        input_dir.mkdir(parents=True)
        mounts = _resolve_mounts(func, {"input_dir": input_dir})
        # access_parent should add the parent of the input directory as ro
        # (the subdir mount itself is pruned since its parent is mounted with equal privilege)
        assert str(tmp_path / "parent") in mounts
        assert mounts[str(tmp_path / "parent")] is False

    @pytest.mark.unit
    def test_must_exist_raises_for_missing_path(self, tmp_path):
        """must_exist should raise RuntimeError when path doesn't exist."""
        from hip_cargo.utils.decorators import stimela_cab

        @stimela_cab(name="test", info="test")
        def func(
            input_file: Annotated[
                File,
                typer.Option(..., parser=Path, help="input"),
                {"stimela": {"must_exist": True}},
            ],
        ):
            pass

        missing = tmp_path / "nonexistent.ms"
        with pytest.raises(RuntimeError, match="does not exist"):
            _resolve_mounts(func, {"input_file": missing})

    @pytest.mark.unit
    def test_mkdir_mounts_parent_rw(self, tmp_path):
        """mkdir policy should mount parent directory read-write."""
        from hip_cargo.utils.decorators import stimela_cab

        @stimela_cab(name="test", info="test")
        def func(
            output_dir: Annotated[
                Directory | None,
                typer.Option(parser=Path, help="output"),
                {"stimela": {"mkdir": True}},
            ] = None,
        ):
            pass

        output_dir = tmp_path / "new_output"
        mounts = _resolve_mounts(func, {"output_dir": output_dir})
        assert str(tmp_path) in mounts
        assert mounts[str(tmp_path)] is True


class TestGpuArgs:
    """Test _gpu_args per-runtime flag mapping."""

    @pytest.mark.unit
    def test_none_spec_yields_nothing(self):
        assert _gpu_args("docker", None) == ([], {})
        assert _gpu_args("apptainer", None) == ([], {})

    @pytest.mark.unit
    def test_docker_all(self):
        assert _gpu_args("docker", "all") == (["--gpus", "all"], {})

    @pytest.mark.unit
    def test_docker_device_spec_passthrough(self):
        assert _gpu_args("docker", "device=0,1") == (["--gpus", "device=0,1"], {})

    @pytest.mark.unit
    def test_podman_cdi_all(self):
        assert _gpu_args("podman", "all") == (["--device", "nvidia.com/gpu=all"], {})

    @pytest.mark.unit
    def test_apptainer_nv_all(self):
        assert _gpu_args("apptainer", "all") == (["--nv"], {})

    @pytest.mark.unit
    def test_singularity_nv_all(self):
        assert _gpu_args("singularity", "all") == (["--nv"], {})

    @pytest.mark.unit
    def test_apptainer_device_spec_sets_cuda_env(self):
        args, env = _gpu_args("apptainer", "device=0,1")
        assert args == ["--nv"]
        assert env == {"CUDA_VISIBLE_DEVICES": "0,1"}

    @pytest.mark.unit
    def test_apptainer_bare_device_spec_sets_cuda_env(self):
        args, env = _gpu_args("apptainer", "0,1")
        assert args == ["--nv"]
        assert env == {"CUDA_VISIBLE_DEVICES": "0,1"}


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
        import os

        from hip_cargo.utils.runner import _build_container_cmd

        cmd = _build_container_cmd("docker", "img:latest", {}, "/work", ["pkg"])
        assert "--gpus" not in cmd
        assert cmd[0:2] == ["docker", "run"]
        assert cmd == [
            "docker",
            "run",
            "--rm",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-w",
            "/work",
            "img:latest",
            "pkg",
        ]


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
    def test_full_container_command_is_printed(self, tmp_path, monkeypatch, capsys):
        from hip_cargo.utils import runner

        func = self._make_func()
        input_file = tmp_path / "data.ms"
        input_file.touch()

        monkeypatch.setattr(runner, "get_container_gpu", lambda import_name: True)
        monkeypatch.setattr(runner, "get_container_run_args", lambda import_name, rt: [])
        with (
            patch("hip_cargo.utils.runner._detect_runtime", return_value="docker"),
            patch("hip_cargo.utils.runner.subprocess.run"),
            patch("hip_cargo.utils.runner.sys") as mock_sys,
        ):
            mock_sys.argv = ["/usr/bin/test-cmd", "--input-file", str(input_file)]
            runner.run_in_container(func, {"input_file": input_file}, image="img:v1", backend="docker")

        out = capsys.readouterr().out
        assert "Full command:" in out
        assert "--gpus all" in out

    @pytest.mark.unit
    def test_full_command_redacts_forwarded_credentials(self, tmp_path, monkeypatch, capsys):
        from hip_cargo.utils import runner

        func = self._make_func()
        input_file = tmp_path / "data.ms"
        input_file.touch()

        monkeypatch.setattr(runner, "get_container_gpu", lambda import_name: True)
        monkeypatch.setattr(runner, "get_container_run_args", lambda import_name, rt: [])
        # Force a forwarded AWS secret into the command.
        monkeypatch.setattr(
            runner, "_build_credential_env", lambda protocols, env: {"AWS_SECRET_ACCESS_KEY": "supersecret"}
        )
        with (
            patch("hip_cargo.utils.runner._detect_runtime", return_value="docker"),
            patch("hip_cargo.utils.runner.subprocess.run"),
            patch("hip_cargo.utils.runner.sys") as mock_sys,
        ):
            mock_sys.argv = ["/usr/bin/test-cmd", "--input-file", str(input_file)]
            runner.run_in_container(func, {"input_file": input_file}, image="img:v1", backend="docker")

        out = capsys.readouterr().out
        assert "supersecret" not in out
        assert "AWS_SECRET_ACCESS_KEY=<redacted>" in out
        assert "--gpus all" in out  # non-secret flags still visible

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
