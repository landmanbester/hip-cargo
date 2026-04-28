"""Tests for container image resolution from package metadata."""

import pytest

from hip_cargo.utils.config import get_container_image


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
