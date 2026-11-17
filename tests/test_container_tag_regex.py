"""Tests for the container image tag regex used in update-cabs workflow and tbump.

The regex rewrites the tag portion of the CONTAINER_IMAGE constant in
_container_image.py. It must handle registries with ports (e.g.
localhost:5000/org/img:tag) by matching the *last* colon before the closing
quote, not the first. The pattern under test is read from the shipped files
(hip-cargo's own and the ``hip-cargo init`` templates), so drift between them
fails here.
"""

import re
import sys
from pathlib import Path

import pytest
import yaml

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "src" / "hip_cargo" / "templates"


def _pattern_from_shell(cmd: str) -> str:
    """Pull the ``re.sub(r'...'`` pattern out of a ``python -c "..."`` shell command."""
    match = re.search(r"re\.sub\(r'(.+?)', r'\\g<1>", cmd)
    assert match, f"no re.sub pattern in: {cmd}"
    return match.group(1).replace('\\"', '"')  # undo the shell's \" escaping


def _tbump_pattern(path: Path) -> str:
    hooks = tomllib.loads(path.read_text())["before_commit"]
    (cmd,) = [h["cmd"] for h in hooks if "CONTAINER_IMAGE" in h["cmd"]]
    return _pattern_from_shell(cmd)


def _update_cabs_pattern(path: Path) -> str:
    steps = yaml.safe_load(path.read_text())["jobs"]["update-cabs"]["steps"]
    (cmd,) = [s["run"] for s in steps if "CONTAINER_IMAGE" in s.get("run", "")]
    return _pattern_from_shell(cmd)


SOURCES = {
    "tbump.toml": _tbump_pattern(ROOT / "tbump.toml"),
    "templates/tbump.toml": _tbump_pattern(TEMPLATES / "tbump.toml"),
    "update-cabs.yml": _update_cabs_pattern(ROOT / ".github" / "workflows" / "update-cabs.yml"),
    "templates/update-cabs.yml": _update_cabs_pattern(TEMPLATES / "workflows" / "update-cabs.yml"),
}
CONTAINER_TAG_REGEX = SOURCES["tbump.toml"]


def test_all_sources_use_the_same_pattern():
    assert set(SOURCES.values()) == {CONTAINER_TAG_REGEX}, SOURCES


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
