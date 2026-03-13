"""Core logic for generating Stimela cab definitions from Python modules."""

import subprocess
from pathlib import Path

import libcst as cst
import yaml

from hip_cargo.utils.config import get_project_image
from hip_cargo.utils.introspector import extract_input_libcst, format_info_fields, parse_decorator_libcst

# Large width prevents YAML line wrapping, which would break trailing comments.
# YAML dumper would split long lines and lose the comment.
YAML_MAX_WIDTH = 10000


def get_image_tag(default_branch: str = "main") -> str:
    """Get the image tag for the current context.

    During a tbump release, reads the version from the .tbump_version sentinel
    file (written by tbump's before_push hook) and deletes it so that subsequent
    commits revert to branch-based tagging. Otherwise derives the tag from the
    current git branch: 'latest' for the default branch, branch name for feature
    branches.

    Args:
        default_branch: Branch name that maps to the 'latest' tag.
    """
    sentinel = Path(".tbump_version")
    if sentinel.exists():
        version = sentinel.read_text().strip()
        sentinel.unlink()
        return version

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        branch = result.stdout.strip()
        if branch == default_branch:
            return "latest"
        return branch.replace("/", "-")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "latest"


def generate_cabs(module: list[Path], image: str | None = None, output_dir: Path | None = None) -> None:
    """Generate Stimela cab definitions from Python modules.

    Args:
        module: List of Python module paths (e.g., "package/cli/command.py").
            Supports glob wildcards in filenames.
        image: Full container image name (with tag) to set in cab definitions.
            If None, resolved from [tool.hip-cargo].image in pyproject.toml
            combined with the current git-derived tag.
        output_dir: Directory where YAML cab files should be written.
            If None, prints to stdout.

    Raises:
        RuntimeError: If module paths are invalid or don't follow expected layout.
    """
    # glob if wildcard in module
    modlist = []
    for modpath in module:
        if not isinstance(modpath, Path):
            modpath = Path(modpath)
        if "*" in str(modpath):
            base_path = modpath.parent
            pattern = modpath.name
            modlist.extend([f for f in base_path.glob(pattern) if f.is_file() and not f.name.startswith("__")])
            if len(modlist) == 0:
                raise RuntimeError(f"No modules found matching {modpath}")
        else:
            if not modpath.is_file():
                raise RuntimeError(f"No module file found at {modpath}")
            modlist.append(modpath)

    # Resolve image from pyproject.toml when not explicitly provided
    if image is None:
        image_base = get_project_image()
        if image_base:
            image = f"{image_base}:{get_image_tag()}"

    # User feedback
    for mod in modlist:
        print(f"Loading file: {mod}")

    print(f"Writing cabs to: {output_dir}")
    for module_path in modlist:
        with open(module_path, "r") as f:
            tree = cst.parse_module(f.read())

        for node in tree.body:
            if isinstance(node, cst.FunctionDef):
                decorators = {}
                for dec in node.decorators:
                    deco_name, deco_args = parse_decorator_libcst(dec)
                    decorators[deco_name] = deco_args

                if "stimela_cab" not in decorators:
                    continue  # skip non-decorated functions

                cab_def = {node.name.value: {}}
                cab_def[node.name.value]["flavour"] = "python"
                parts = Path(module_path).parts

                # Extract the module path relative to src/
                try:
                    src_index = parts.index("src")
                except ValueError:
                    raise RuntimeError(
                        f"Expected 'src' directory in module path, got: {module_path}\n"
                        f"Module path should follow pattern: .../src/package/cli/module.py"
                    )

                relative_path = Path(*parts[src_index + 1 :])
                parts = list(relative_path.parts)

                # Replace 'cli' with 'core' to get the command module path
                try:
                    cli_index = parts.index("cli")
                    parts[cli_index] = "core"
                except ValueError:
                    raise RuntimeError(
                        f"Expected 'cli' directory in module path after 'src', got: {relative_path}\n"
                        f"Module path should follow pattern: .../src/package/cli/module.py"
                    )

                parts[-1] = parts[-1].replace(".py", "")
                parts.append(node.name.value)
                cab_def[node.name.value]["command"] = ".".join(parts)
                cab_def[node.name.value]["outputs"] = {}
                for decorator_name, decorator_content in decorators.items():
                    if decorator_name == "stimela_cab":
                        kwargs = decorator_content["kwargs"].copy()
                        cab_def[node.name.value].update(kwargs)
                    else:  # must be outputs
                        # there are no args in outputs decorator, they are all kwargs
                        kwargs = decorator_content["kwargs"].copy()
                        # Remove empty info fields to avoid trailing whitespace in YAML
                        # Also remove info fields that only contain whitespace or comments
                        if "info" in kwargs:
                            info_value = kwargs["info"]
                            if isinstance(info_value, str):
                                info_stripped = info_value.strip()
                                # Remove if empty or only contains a comment
                                if not info_stripped or info_stripped.startswith("#"):
                                    del kwargs["info"]
                        cab_def[node.name.value]["outputs"][decorator_name] = kwargs
                # Override image after decorator processing so CLI arg takes precedence
                if image is not None:
                    cab_def[node.name.value]["image"] = image
                cab_def[node.name.value]["inputs"] = {}
                # LibCST: use node.params.params instead of node.args.args
                for param in node.params.params:
                    # Check if this parameter is an output (convert underscores to hyphens for comparison)
                    if param.name.value.replace("_", "-") in cab_def[node.name.value]["outputs"]:
                        continue  # skip outputs
                    # Use extract_input_libcst which handles LibCST Param nodes
                    param_name, input_def = extract_input_libcst(param)
                    if input_def.get("skip"):
                        continue  # skip infrastructure params (e.g. backend)
                    # Convert underscores to hyphens for cab input names
                    cab_def[node.name.value]["inputs"][param_name.replace("_", "-")] = input_def

                # reorder to place outputs last
                outputs = cab_def[node.name.value].pop("outputs")
                cab_def[node.name.value]["outputs"] = outputs

                # Wrap in top-level "cabs" key
                cab_def = {"cabs": cab_def}

                # Generate YAML
                # Use safe_dump with nice formatting
                # Set width to large value to prevent line wrapping (which breaks trailing comments)
                yaml_content = yaml.safe_dump(
                    cab_def,
                    default_flow_style=False,
                    sort_keys=False,
                    indent=2,
                    width=YAML_MAX_WIDTH,
                )

                # format info fields so they are defined as multi-line strings
                yaml_content_formatted = format_info_fields(yaml_content)

                # Write the YAML file
                if output_dir:
                    output_dir = Path(output_dir)
                    # Create output directory if it doesn't exist
                    output_dir.mkdir(parents=True, exist_ok=True)
                    output_file = output_dir / f"{node.name.value}.yml"
                    with open(output_file, "w") as f:
                        f.write(yaml_content_formatted)
                else:  # else write to terminal
                    print(yaml_content_formatted)
