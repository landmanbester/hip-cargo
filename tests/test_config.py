"""Tests for the monitoring configuration module."""

from pathlib import Path

import pytest

pytest.importorskip("pydantic_settings", reason="monitoring extra is Python 3.11+")

from hip_cargo.monitoring.config import MonitorSettings  # noqa: E402
from hip_cargo.utils.config import (  # noqa: E402  # noqa: E402
    get_container_gpu,
    get_container_image,
    get_container_run_args,
)


def test_defaults():
    """MonitorSettings defaults are correct without any env vars or .env file."""
    settings = MonitorSettings(_env_file=None)
    assert settings.port == 8321
    assert settings.host == "0.0.0.0"
    assert settings.auth_token is None
    assert settings.ray_address is None
    assert settings.ray_dashboard_url == "http://localhost:8265"
    assert settings.aggregator_name == "progress_aggregator"
    assert settings.max_events_per_job == 1000
    assert settings.websocket_poll_interval == 0.5


def test_env_var_override(monkeypatch):
    """Environment variables with HIPCARGO_ prefix override defaults."""
    monkeypatch.setenv("HIPCARGO_PORT", "9999")
    monkeypatch.setenv("HIPCARGO_AUTH_TOKEN", "secret")
    settings = MonitorSettings(_env_file=None)
    assert settings.port == 9999
    assert settings.auth_token == "secret"


def test_env_prefix(monkeypatch):
    """Unprefixed env vars do NOT affect settings."""
    monkeypatch.setenv("PORT", "1234")
    monkeypatch.delenv("HIPCARGO_PORT", raising=False)
    settings = MonitorSettings(_env_file=None)
    assert settings.port == 8321  # default, not 1234


def test_dotenv_file(tmp_path: Path):
    """Settings are read from a .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text("HIPCARGO_PORT=7777\nHIPCARGO_AUTH_TOKEN=fromfile\n")
    settings = MonitorSettings(_env_file=str(env_file))
    assert settings.port == 7777
    assert settings.auth_token == "fromfile"


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

    @pytest.mark.unit
    def test_string_run_args_raises_typeerror(self, monkeypatch):
        import sys
        import types

        mod = types.ModuleType("badargpkg._container_image")
        mod.CONTAINER_IMAGE = "ghcr.io/x/badargpkg:latest"
        mod.RUN_ARGS_DOCKER = "--ipc=host"  # mistake: a bare string, not a list
        monkeypatch.setitem(sys.modules, "badargpkg._container_image", mod)
        monkeypatch.setitem(sys.modules, "badargpkg", types.ModuleType("badargpkg"))
        with pytest.raises(TypeError, match="RUN_ARGS_DOCKER"):
            get_container_run_args("badargpkg", "docker")
