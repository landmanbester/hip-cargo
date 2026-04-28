"""Tests for the container image tag regex used in update-cabs workflow and tbump.

The regex rewrites the tag portion of the CONTAINER_IMAGE constant in
_container_image.py. It must handle registries with ports (e.g.
localhost:5000/org/img:tag) by matching the *last* colon before the closing
quote, not the first.
"""

import re

import pytest

# This is the regex used in .github/workflows/update-cabs.yml and tbump.toml
CONTAINER_TAG_REGEX = r'(CONTAINER_IMAGE\s*=\s*".*:)[^"]+'


class TestContainerTagRegex:
    """Test the regex pattern that rewrites container image tags."""

    @pytest.mark.unit
    def test_standard_ghcr_url(self):
        line = 'CONTAINER_IMAGE = "ghcr.io/user/repo:feature-branch"'
        result = re.sub(CONTAINER_TAG_REGEX, r"\g<1>latest", line)
        assert result == 'CONTAINER_IMAGE = "ghcr.io/user/repo:latest"'

    @pytest.mark.unit
    def test_registry_with_port(self):
        """Registries like localhost:5000 must not be truncated."""
        line = 'CONTAINER_IMAGE = "localhost:5000/org/img:feature-branch"'
        result = re.sub(CONTAINER_TAG_REGEX, r"\g<1>latest", line)
        assert result == 'CONTAINER_IMAGE = "localhost:5000/org/img:latest"'

    @pytest.mark.unit
    def test_registry_with_port_and_nested_path(self):
        line = 'CONTAINER_IMAGE = "registry.example.com:8080/team/project/img:v1.2.3"'
        result = re.sub(CONTAINER_TAG_REGEX, r"\g<1>0.2.0", line)
        assert result == 'CONTAINER_IMAGE = "registry.example.com:8080/team/project/img:0.2.0"'

    @pytest.mark.unit
    def test_latest_to_semver(self):
        line = 'CONTAINER_IMAGE = "ghcr.io/user/repo:latest"'
        result = re.sub(CONTAINER_TAG_REGEX, r"\g<1>0.1.8", line)
        assert result == 'CONTAINER_IMAGE = "ghcr.io/user/repo:0.1.8"'

    @pytest.mark.unit
    def test_semver_to_latest(self):
        line = 'CONTAINER_IMAGE = "ghcr.io/user/repo:0.1.8"'
        result = re.sub(CONTAINER_TAG_REGEX, r"\g<1>latest", line)
        assert result == 'CONTAINER_IMAGE = "ghcr.io/user/repo:latest"'

    @pytest.mark.unit
    def test_branch_name_with_slashes(self):
        line = 'CONTAINER_IMAGE = "ghcr.io/user/repo:fix/my-bug"'
        result = re.sub(CONTAINER_TAG_REGEX, r"\g<1>latest", line)
        assert result == 'CONTAINER_IMAGE = "ghcr.io/user/repo:latest"'

    @pytest.mark.unit
    def test_preserves_surrounding_content(self):
        """Regex should only affect the CONTAINER_IMAGE line, not surrounding text."""
        py_file = '"""Container image for my-pkg."""\nCONTAINER_IMAGE = "ghcr.io/user/repo:dev"\n'
        result = re.sub(CONTAINER_TAG_REGEX, r"\g<1>latest", py_file)
        assert 'CONTAINER_IMAGE = "ghcr.io/user/repo:latest"' in result
        assert '"""Container image for my-pkg."""' in result

    @pytest.mark.unit
    def test_whitespace_around_equals(self):
        """Regex handles optional whitespace around = sign."""
        line = 'CONTAINER_IMAGE  =  "ghcr.io/user/repo:old-tag"'
        result = re.sub(CONTAINER_TAG_REGEX, r"\g<1>latest", line)
        assert result == 'CONTAINER_IMAGE  =  "ghcr.io/user/repo:latest"'

    @pytest.mark.unit
    def test_no_match_without_colon_in_url(self):
        """URL without a tag colon should not be matched."""
        line = 'CONTAINER_IMAGE = "ghcr.io/user/repo"'
        result = re.sub(CONTAINER_TAG_REGEX, r"\g<1>latest", line)
        # No colon in the image ref means no match — line unchanged
        assert result == line
