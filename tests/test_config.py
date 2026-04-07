"""Tests for container image resolution from package metadata."""

import pytest

from hip_cargo.utils.config import get_container_image


class TestGetContainerImage:
    """Test get_container_image reads from importlib.metadata."""

    @pytest.mark.unit
    def test_returns_image_for_hip_cargo(self):
        """hip-cargo's own pyproject.toml has a Container URL."""
        image = get_container_image("hip-cargo")
        assert image is not None
        assert image.startswith("ghcr.io/")

    @pytest.mark.unit
    def test_returns_none_for_package_without_container(self):
        """Packages without a Container URL should return None."""
        image = get_container_image("pytest")
        assert image is None

    @pytest.mark.unit
    def test_raises_for_nonexistent_package(self):
        """Non-existent package should raise PackageNotFoundError."""
        from importlib.metadata import PackageNotFoundError

        with pytest.raises(PackageNotFoundError):
            get_container_image("nonexistent-package-xyz-12345")
