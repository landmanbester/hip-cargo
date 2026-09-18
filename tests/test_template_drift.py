"""Guard the ``hip-cargo init`` templates against drifting from hip-cargo's own config.

The templates mirror hip-cargo's own workflows and tooling, but Dependabot only
bumps the real files, so the copies under ``src/hip_cargo/templates`` fall behind
silently. These tests fail as soon as the two disagree.
"""

import json
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

WORKFLOWS = ["ci.yml", "publish.yml", "publish-container.yml", "update-cabs.yml"]


def _uses(path: Path) -> set[str]:
    return set(re.findall(r"uses:\s*(\S+)", path.read_text()))


def _precommit_revs(text: str) -> dict[str, str]:
    """Map each pre-commit repo URL to its pinned rev."""
    return dict(re.findall(r"repo:\s*(\S+)\s*\n\s*rev:\s*(\S+)", text))


@pytest.mark.parametrize(
    "template",
    sorted(p for p in TEMPLATES.rglob("*") if p.suffix in {".toml", ".yml", ".yaml", ".json"}),
    ids=lambda p: str(p.relative_to(TEMPLATES)),
)
def test_structured_templates_parse(template: Path):
    """Templates must stay valid before substitution; GitHub's dependency graph parses them as-is."""
    if template.suffix == ".toml":
        tomllib.loads(template.read_text())
    elif template.suffix == ".json":
        json.loads(template.read_text())
    else:
        yaml.safe_load(template.read_text())


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_workflow_action_versions_match(workflow: str):
    assert _uses(TEMPLATES / "workflows" / workflow) == _uses(ROOT / ".github" / "workflows" / workflow)


def test_dependabot_config_matches():
    assert (TEMPLATES / "dependabot.yml").read_text() == (ROOT / ".github" / "dependabot.yml").read_text()


def test_template_requirements_are_pep508():
    """GitHub's dependency graph rejects the whole file if any requirement is not PEP 508."""
    from packaging.requirements import Requirement

    project = tomllib.loads((TEMPLATES / "pyproject.toml").read_text())
    reqs = project["project"]["dependencies"] + project["build-system"]["requires"]
    for extra in project["project"].get("optional-dependencies", {}).values():
        reqs += extra
    for req in reqs:
        Requirement(req)


def test_template_hip_cargo_floor_is_current_release():
    """tbump bumps this floor alongside __version__; generated code needs the release that wrote it."""
    from hip_cargo import __version__

    deps = tomllib.loads((TEMPLATES / "pyproject.toml").read_text())["project"]["dependencies"]
    assert f"hip-cargo>={__version__}" in deps


def test_build_backend_constraint_matches():
    own = tomllib.loads((ROOT / "pyproject.toml").read_text())["build-system"]["requires"]
    template = tomllib.loads((TEMPLATES / "pyproject.toml").read_text())["build-system"]["requires"]
    assert template == own


def test_precommit_revs_match():
    from hip_cargo.core.init import _CONVENTIONAL_PRECOMMIT_BLOCK

    own = _precommit_revs((ROOT / ".pre-commit-config.yaml").read_text())
    template = _precommit_revs((TEMPLATES / "pre-commit-config.yaml").read_text() + _CONVENTIONAL_PRECOMMIT_BLOCK)
    assert template == own


def test_precommit_ruff_matches_locked_ruff():
    """The pre-commit ruff must format exactly like the ruff that generate-function runs."""
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    locked = next(p["version"] for p in lock["package"] if p["name"] == "ruff")
    rev = _precommit_revs((ROOT / ".pre-commit-config.yaml").read_text())[
        "https://github.com/astral-sh/ruff-pre-commit"
    ]
    assert rev == f"v{locked}"
