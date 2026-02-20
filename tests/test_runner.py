"""Tests for container fallback runner."""

from pathlib import Path
from typing import Annotated, NewType
from unittest.mock import patch

import pytest
import typer

from hip_cargo.utils.runner import (
    _build_argv_with_native_backend,
    _build_container_cmd,
    _is_path_type,
    _resolve_mounts,
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
