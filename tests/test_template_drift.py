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


def test_publish_container_matches_template():
    """hip-cargo's own publish-container workflow is the template with the default branch filled in."""
    template = (TEMPLATES / "workflows" / "publish-container.yml").read_text()
    own = (ROOT / ".github" / "workflows" / "publish-container.yml").read_text()
    assert template.replace("<DEFAULT_BRANCH>", "main") == own


def test_publish_container_never_runs_on_pull_requests():
    """Feature-branch images are built on manual dispatch only, never on PR pushes."""
    triggers = yaml.safe_load((TEMPLATES / "workflows" / "publish-container.yml").read_text())[True]
    assert "pull_request" not in triggers
    assert "workflow_dispatch" in triggers


def _floor(pyproject: Path) -> str:
    requires = tomllib.loads(pyproject.read_text())["project"]["requires-python"]
    assert requires.startswith(">="), requires
    return requires[2:].split(",")[0].strip()


def _version_key(v: str) -> tuple[int, ...]:
    return tuple(map(int, v.split(".")))


def test_ci_tests_the_oldest_supported_python():
    """hip-cargo has no lightweight mode, so its full test matrix starts at the requires-python floor."""
    matrix = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())["jobs"]["test"]["strategy"][
        "matrix"
    ]
    assert min(matrix["python-version"], key=_version_key) == _floor(ROOT / "pyproject.toml")


def test_template_ci_runs_lightweight_install_at_the_floor():
    """Scaffolded packages support only the lightweight install on the floor Python; the full matrix starts above it."""
    jobs = yaml.safe_load((TEMPLATES / "workflows" / "ci.yml").read_text())["jobs"]
    floor = _floor(TEMPLATES / "pyproject.toml")
    setup = [s for s in jobs["lightweight"]["steps"] if s.get("uses", "").startswith("actions/setup-python")]
    assert [s["with"]["python-version"] for s in setup] == [floor]
    assert jobs["lightweight"]["name"] == f"Lightweight install ({floor})"
    full = jobs["test"]["strategy"]["matrix"]["python-version"]
    assert _version_key(min(full, key=_version_key)) > _version_key(floor)


def test_publish_container_labels_every_architecture_image() -> None:
    """Labels live in each image's config, so the per-arch build must set them (merge only tags).

    Lost when the build was split per architecture (#121); tags, labels and
    annotations now come from one ``meta`` job so they cannot disagree.
    """
    jobs = yaml.safe_load((TEMPLATES / "workflows" / "publish-container.yml").read_text())["jobs"]
    build = next(s for s in jobs["build"]["steps"] if s.get("id") == "build")
    assert build["with"]["labels"] == "${{ needs.meta.outputs.labels }}"
    assert "meta" in jobs["build"]["needs"] and "meta" in jobs["merge"]["needs"]
    manifest = next(s for s in jobs["merge"]["steps"] if s["name"] == "Create multi-arch manifest")
    assert manifest["env"]["ANNOTATIONS"] == "${{ needs.meta.outputs.annotations }}"
    assert "--annotation" in manifest["run"]
    assert not any("metadata-action" in s.get("uses", "") for s in jobs["merge"]["steps"])


@pytest.mark.parametrize("dockerfile", [TEMPLATES / "Dockerfile", ROOT / "Dockerfile"], ids=["template", "own"])
def test_dockerfile_installs_from_the_lock(dockerfile: Path) -> None:
    """Both architectures must get the locked versions, not resolve independently."""
    text = dockerfile.read_text()
    assert "COPY pyproject.toml uv.lock ./" in text
    assert "uv export --locked --no-dev" in text
    assert "uv pip install --system --no-cache --no-deps ." in text


@pytest.mark.parametrize("dockerfile", [TEMPLATES / "Dockerfile", ROOT / "Dockerfile"], ids=["template", "own"])
def test_dockerfile_uv_is_a_stage_dependabot_can_bump(dockerfile: Path) -> None:
    """Dependabot reads only FROM lines, so uv must be a named stage, not `COPY --from=<image>`."""
    text = dockerfile.read_text()
    assert re.search(r"^FROM ghcr\.io/astral-sh/uv:\d+\.\d+\.\d+ AS uv$", text, re.MULTILINE)
    assert "COPY --from=uv " in text
    assert "COPY --from=ghcr.io" not in text


def test_dependabot_tracks_docker_images_but_not_the_python_minor() -> None:
    """The uv stage gets version updates; the image's Python minor stays a deliberate choice."""
    updates = yaml.safe_load((TEMPLATES / "dependabot.yml").read_text())["updates"]
    docker = next(u for u in updates if u["package-ecosystem"] == "docker")
    assert docker["open-pull-requests-limit"] > 0
    python = next(i for i in docker["ignore"] if i["dependency-name"] == "python")
    assert "version-update:semver-minor" in python["update-types"]
