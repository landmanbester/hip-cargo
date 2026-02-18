"""Core logic for initializing a new hip-cargo project."""

import datetime
import subprocess
from pathlib import Path

from hip_cargo.templates import TEMPLATES_DIR

LICENSE_CLASSIFIERS = {
    "MIT": "License :: OSI Approved :: MIT License",
    "Apache-2.0": "License :: OSI Approved :: Apache Software License",
    "BSD-3-Clause": "License :: OSI Approved :: BSD License",
}


def init(
    project_name: str,
    github_user: str,
    description: str = "A Python project",
    author_name: str | None = None,
    author_email: str | None = None,
    cli_command: str | None = None,
    initial_version: str = "0.0.0",
    license_type: str = "MIT",
    cli_mode: str = "multi",
    default_branch: str = "main",
    project_dir: Path | None = None,
) -> None:
    """Initialize a new hip-cargo project.

    Args:
        project_name: Hyphenated project name (e.g. "my-project").
        github_user: GitHub username or organization.
        description: Short project description.
        author_name: Author name (auto-detected from git config if None).
        author_email: Author email (auto-detected from git config if None).
        cli_command: CLI entry point name (derived from project_name if None).
        initial_version: Starting version string.
        license_type: License type (MIT, Apache-2.0, BSD-3-Clause).
        cli_mode: CLI mode (single or multi).
        default_branch: Default git branch name.
        project_dir: Output directory (defaults to ./<project_name>/).
    """
    # Derive values
    package_name = project_name.replace("-", "_")
    github_url = f"https://github.com/{github_user}/{project_name}"
    if cli_command is None:
        cli_command = project_name.replace("-", "_")
    if project_dir is None:
        project_dir = Path(project_name)
    if not isinstance(project_dir, Path):
        project_dir = Path(project_dir)
    license_classifier = LICENSE_CLASSIFIERS.get(license_type, LICENSE_CLASSIFIERS["MIT"])
    year = str(datetime.datetime.now().year)

    # Auto-detect author info from git config
    if author_name is None:
        author_name = _get_git_config("user.name") or "Author Name"
    if author_email is None:
        author_email = _get_git_config("user.email") or "author@example.com"

    # Validate project_dir doesn't exist
    if project_dir.exists():
        raise RuntimeError(f"Directory already exists: {project_dir}")

    # Build substitution dict
    subs = {
        "<PROJECT_NAME>": project_name,
        "<PACKAGE_NAME>": package_name,
        "<GITHUB_USER>": github_user,
        "<GITHUB_URL>": github_url,
        "<DESCRIPTION>": description,
        "<AUTHOR_NAME>": author_name,
        "<AUTHOR_EMAIL>": author_email,
        "<CLI_COMMAND>": cli_command,
        "<INITIAL_VERSION>": initial_version,
        "<LICENSE_CLASSIFIER>": license_classifier,
        "<LICENSE_TYPE>": license_type,
        "<YEAR>": year,
        "<DEFAULT_BRANCH>": default_branch,
    }

    # Create directory tree
    src_pkg = project_dir / "src" / package_name
    for d in [
        src_pkg / "cli",
        src_pkg / "core",
        src_pkg / "cabs",
        project_dir / "tests",
        project_dir / "scripts",
        project_dir / ".github" / "workflows",
        project_dir / ".devcontainer",
    ]:
        d.mkdir(parents=True, exist_ok=True)

    # Write template files
    _write_template("pyproject.toml", project_dir / "pyproject.toml", subs)
    _write_template("tbump.toml", project_dir / "tbump.toml", subs)
    _write_template("Dockerfile", project_dir / "Dockerfile", subs)
    _write_template("pre-commit-config.yaml", project_dir / ".pre-commit-config.yaml", subs)
    _write_template("gitignore", project_dir / ".gitignore", subs)
    _write_template("dependabot.yml", project_dir / ".github" / "dependabot.yml", subs)
    _write_template("devcontainer/devcontainer.json", project_dir / ".devcontainer" / "devcontainer.json", subs)

    # Workflow files
    _write_template("workflows/ci.yml", project_dir / ".github" / "workflows" / "ci.yml", subs)
    _write_template("workflows/publish.yml", project_dir / ".github" / "workflows" / "publish.yml", subs)
    _write_template(
        "workflows/publish-container.yml", project_dir / ".github" / "workflows" / "publish-container.yml", subs
    )
    _write_template("workflows/update-cabs.yml", project_dir / ".github" / "workflows" / "update-cabs.yml", subs)

    # Generate cabs script
    _write_template("generate_cabs.py", project_dir / "scripts" / "generate_cabs.py", subs)

    # CLI __init__.py based on cli_mode
    cli_template = "cli_single.py" if cli_mode == "single" else "cli_multi.py"
    _write_template(cli_template, src_pkg / "cli" / "__init__.py", subs)

    # Onboard CLI and core
    _write_template("onboard_cli.py", src_pkg / "cli" / "onboard.py", subs)
    _write_template("onboard_core.py", src_pkg / "core" / "onboard.py", subs)

    # License file
    license_file_map = {
        "MIT": "licenses/mit.txt",
        "Apache-2.0": "licenses/apache-2.0.txt",
        "BSD-3-Clause": "licenses/bsd-3-clause.txt",
    }
    license_template = license_file_map.get(license_type)
    if license_template and (TEMPLATES_DIR / license_template).exists():
        _write_template(license_template, project_dir / "LICENSE", subs)

    # ci.yml adjustment for single mode: remove the "onboard --help" line
    if cli_mode == "single":
        ci_path = project_dir / ".github" / "workflows" / "ci.yml"
        ci_content = ci_path.read_text()
        # Remove the line with "onboard --help" since onboard is the root command in single mode
        ci_lines = ci_content.splitlines(keepends=True)
        ci_content = "".join(line for line in ci_lines if "onboard --help" not in line)
        ci_path.write_text(ci_content)

    # Write generated files (inline content)
    _write_file(
        src_pkg / "__init__.py",
        f'"""{description}"""\n\n__version__ = "{initial_version}"\n\n__all__ = ["__version__"]\n',
    )
    _write_file(src_pkg / "core" / "__init__.py", f'"""Core implementations for {project_name}."""\n')
    _write_file(
        src_pkg / "cabs" / "__init__.py",
        '"""Cab definitions for generated Stimela cabs."""\n\n'
        "from pathlib import Path\n\n"
        "CAB_DIR = Path(__file__).parent\n"
        'AVAILABLE_CABS = [p.stem for p in CAB_DIR.glob("*.yml")]\n\n\n'
        "def get_cab_path(name: str) -> Path:\n"
        '    """Get path to a cab definition.\n\n'
        "    Args:\n"
        "        name: Name of the cab (without .yml extension)\n\n"
        "    Returns:\n"
        "        Path to the cab YAML file\n\n"
        "    Raises:\n"
        "        FileNotFoundError: If the cab doesn't exist\n"
        '    """\n'
        '    cab_path = CAB_DIR / f"{name}.yml"\n'
        "    if not cab_path.exists():\n"
        '        raise FileNotFoundError(f"Cab not found: {name}")\n'
        "    return cab_path\n\n\n"
        '__all__ = ["CAB_DIR", "AVAILABLE_CABS", "get_cab_path"]\n',
    )
    _write_file(project_dir / "tests" / "__init__.py", "")
    _write_file(
        project_dir / "tests" / "test_install.py",
        f"def test_import():\n"
        f"    import {package_name}\n\n"
        f'    assert hasattr({package_name}, "__version__")\n\n\n'
        f"def test_version_is_string():\n"
        f"    from {package_name} import __version__\n\n"
        f"    assert isinstance(__version__, str)\n",
    )
    _write_file(
        project_dir / "README.md",
        f"# {project_name}\n\n"
        f"{description}\n\n"
        f"## Installation\n\n"
        f"```bash\n"
        f"pip install {project_name}\n"
        f"```\n\n"
        f"## Usage\n\n"
        f"```bash\n"
        f"{cli_command} --help\n"
        f"```\n",
    )

    # Post-generation steps
    print(f"\nProject created at: {project_dir}\n")

    _run_command(["uv", "sync", "--group", "dev"], cwd=project_dir)
    _run_command(["uv", "run", "pytest", "tests/test_install.py", "-v"], cwd=project_dir)
    _run_command(
        [
            "uv",
            "run",
            "hip-cargo",
            "generate-cabs",
            "--module",
            f"src/{package_name}/cli/onboard.py",
            "--output-dir",
            f"src/{package_name}/cabs/",
        ],
        cwd=project_dir,
    )
    _run_command(["uv", "run", "ruff", "format", "."], cwd=project_dir)
    _run_command(["uv", "run", "ruff", "check", ".", "--fix"], cwd=project_dir)
    _run_command(["git", "init", "-b", default_branch], cwd=project_dir)
    _run_command(["git", "add", "."], cwd=project_dir)
    _run_command(["git", "commit", "-m", "chore: initial project scaffold"], cwd=project_dir)
    _run_command(["uv", "run", "pre-commit", "install"], cwd=project_dir)

    print(f"\nDone! Project '{project_name}' is ready at {project_dir}")
    print(f"\n  cd {project_dir}")
    print(f"  uv run {cli_command} onboard")
    print("\nto see setup instructions for CI/CD and publishing.")


def _read_template(name: str) -> str:
    """Read a template file from the templates directory."""
    return (TEMPLATES_DIR / name).read_text()


def _apply_substitutions(content: str, subs: dict[str, str]) -> str:
    """Replace all <PLACEHOLDER> values in content."""
    for placeholder, value in subs.items():
        content = content.replace(placeholder, value)
    return content


def _write_template(template_name: str, target_path: Path, subs: dict[str, str]) -> None:
    """Read a template, apply substitutions, and write to target."""
    content = _read_template(template_name)
    content = _apply_substitutions(content, subs)
    _write_file(target_path, content)


def _write_file(path: Path, content: str) -> None:
    """Create parent directories and write content to file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _get_git_config(key: str) -> str | None:
    """Run git config --get <key>, return None on failure."""
    try:
        result = subprocess.run(
            ["git", "config", "--get", key],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except subprocess.CalledProcessError:
        return None


def _run_command(cmd: list[str], cwd: Path) -> None:
    """Run a subprocess with error handling and progress output."""
    cmd_str = " ".join(cmd)
    print(f"  Running: {cmd_str}")
    try:
        subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"  Warning: '{cmd_str}' failed:")
        if e.stdout:
            print(f"    stdout: {e.stdout.strip()}")
        if e.stderr:
            print(f"    stderr: {e.stderr.strip()}")
        raise
