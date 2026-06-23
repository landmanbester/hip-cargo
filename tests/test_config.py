"""Tests for container image resolution from package metadata."""

import pytest

from hip_cargo.utils.config import get_container_gpu, get_container_image, get_container_run_args


class TestGetContainerImage:
    """Test get_container_image reads from _container_image module."""

    @pytest.mark.unit
    def test_returns_image_for_hip_cargo(self):
        """hip-cargo's own _container_image.py has a CONTAINER_IMAGE constant."""
        image = get_container_image("hip-cargo")
        assert image is not None
        assert image.startswith("ghcr.io/")

    @pytest.mark.unit
    def test_returns_none_for_package_without_container(self):
        """Packages without a _container_image module should return None."""
        image = get_container_image("pytest")
        assert image is None

    @pytest.mark.unit
    def test_returns_none_for_nonexistent_package(self):
        """Non-existent package should return None (not raise)."""
        image = get_container_image("nonexistent-package-xyz-12345")
        assert image is None


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
