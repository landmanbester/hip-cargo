"""Core logic for generating Stimela cab definitions from Python modules."""

from pathlib import Path

import yaml

from hip_cargo.utils.config import get_container_image
from hip_cargo.utils.introspector import format_info_fields, param_spec_to_cab_input, parse_module
from hip_cargo.utils.spec import CommandSpec

# Large width prevents YAML line wrapping, which would break trailing comments.
# YAML dumper would split long lines and lose the comment.
YAML_MAX_WIDTH = 10000


def generate_cabs(module: list[Path], image: str | None = None, output_dir: Path | None = None) -> None:
    """Generate Stimela cab definitions from Python modules.

    Args:
        module: List of Python module paths (e.g., "package/cli/command.py").
            Supports glob wildcards in filenames.
        image: Full container image name (with tag) to set in cab definitions.
            If None, resolved from the package's _container_image module.
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

    # Resolve image from installed package metadata when not explicitly provided.
    # Derive distribution name from module path: src/<package>/cli/module.py
    # The first component after src/ is the Python import name.
    if image is None:
        first_mod = modlist[0]
        parts = first_mod.parts
        try:
            src_idx = parts.index("src")
            import_name = parts[src_idx + 1]
            dist_name = import_name.replace("_", "-")
            image = get_container_image(dist_name)
        except (ValueError, IndexError):
            pass

    # User feedback
    for mod in modlist:
        print(f"Loading file: {mod}")

    print(f"Writing cabs to: {output_dir}")
    for module_path in modlist:
        module_spec = parse_module(module_path)

        for command in module_spec.commands:
            cab_def = _command_spec_to_cab_def(command, image)

            yaml_content = yaml.safe_dump(
                cab_def,
                default_flow_style=False,
                sort_keys=False,
                indent=2,
                width=YAML_MAX_WIDTH,
            )
            yaml_content_formatted = format_info_fields(yaml_content)

            if output_dir:
                output_dir = Path(output_dir)
                output_dir.mkdir(parents=True, exist_ok=True)
                output_file = output_dir / f"{command.name}.yml"
                with open(output_file, "w") as f:
                    f.write(yaml_content_formatted)
            else:
                print(yaml_content_formatted)


def _command_spec_to_cab_def(command: CommandSpec, image: str | None) -> dict:
    """Render a :class:`CommandSpec` into the dict shape expected by ``yaml.safe_dump``.

    Encapsulates all cab-YAML-specific shaping: command-path derivation, output
    handling, the image override, input-vs-output disambiguation, and the
    final ``inputs``/``outputs`` ordering.
    """
    cab_body: dict = {"flavour": "python"}

    parts = command.module_path.parts
    try:
        src_index = parts.index("src")
    except ValueError:
        raise RuntimeError(
            f"Expected 'src' directory in module path, got: {command.module_path}\n"
            f"Module path should follow pattern: .../src/package/cli/module.py"
        )

    relative_path = Path(*parts[src_index + 1 :])
    rel_parts = list(relative_path.parts)
    try:
        cli_index = rel_parts.index("cli")
        rel_parts[cli_index] = "core"
    except ValueError:
        raise RuntimeError(
            f"Expected 'cli' directory in module path after 'src', got: {relative_path}\n"
            f"Module path should follow pattern: .../src/package/cli/module.py"
        )
    rel_parts[-1] = rel_parts[-1].replace(".py", "")
    rel_parts.append(command.name)
    cab_body["command"] = ".".join(rel_parts)

    outputs: dict = {}
    for decorator_name, decorator_content in command.decorators.items():
        if decorator_name == "stimela_cab":
            cab_body.update(decorator_content["kwargs"].copy())
        else:
            kwargs = decorator_content["kwargs"].copy()
            # Remove empty / comment-only info fields to avoid trailing whitespace in YAML.
            if "info" in kwargs:
                info_value = kwargs["info"]
                if isinstance(info_value, str):
                    info_stripped = info_value.strip()
                    if not info_stripped or info_stripped.startswith("#"):
                        del kwargs["info"]
            outputs[decorator_name] = kwargs
    cab_body["outputs"] = outputs

    if image is not None:
        cab_body["image"] = image

    cab_body["inputs"] = {}
    for param_spec in command.params:
        if param_spec.name.replace("_", "-") in outputs:
            continue
        param_name, input_def = param_spec_to_cab_input(param_spec)
        if input_def.get("skip"):
            continue
        cab_body["inputs"][param_name.replace("_", "-")] = input_def

    # Move outputs to the end of the dict (insertion-order matters for YAML).
    cab_body["outputs"] = cab_body.pop("outputs")

    return {"cabs": {command.name: cab_body}}
