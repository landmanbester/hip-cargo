"""Core logic for generating Stimela cab definitions from Python modules."""

import ast
from pathlib import Path

import yaml

from hip_cargo.utils.introspector import extract_input, parse_decorator


def generate_cabs(module_paths: list[Path], output_dir: Path | None, image: str | None) -> None:
    """Generate a Stimela cab definition from a Python module.

    Args:
        module_paths: List of python module paths (e.g., "package/cli/command.py")
        output_path: Directory where the YAML cab should be written

    Raises:
        ImportError: If the module cannot be imported
        AttributeError: If the module doesn't contain a decorated function
    """
    for module_path in module_paths:
        with open(module_path, "r") as f:
            tree = ast.parse(f.read(), filename=module_path)

        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                decorators = {}
                for dec in node.decorator_list:
                    deco_name, deco_args = parse_decorator(dec)
                    decorators[deco_name] = deco_args

                if "stimela_cab" not in decorators:
                    continue  # skip non-decorated functions

                cab_def = {node.name: {}}
                cab_def[node.name]["flavour"] = "python"
                parts = Path(module_path).parts
                src_index = parts.index("src")
                relative_path = Path(*parts[src_index + 1 :])
                parts = list(relative_path.parts)
                cli_index = parts.index("cli")
                parts[cli_index] = "core"
                parts[-1] = parts[-1].replace(".py", "")
                parts.append(node.name)
                cab_def[node.name]["command"] = ".".join(parts)
                if image is not None:
                    cab_def[node.name]["image"] = image
                cab_def[node.name]["outputs"] = {}
                for decorator_name, decorator_content in decorators.items():
                    if decorator_name == "stimela_cab":
                        cab_def[node.name].update(decorator_content["kwargs"])
                    else:  # must be outputs
                        # there are no args in outputs decorator, they are all kwargs
                        cab_def[node.name]["outputs"][decorator_name] = decorator_content["kwargs"]
                cab_def[node.name]["inputs"] = {}
                num_args = len(node.args.args)
                num_default = len(node.args.defaults)
                for i, arg in enumerate(node.args.args):
                    if arg.arg in cab_def[node.name]["outputs"]:
                        continue  # skip outputs
                    default_idx = i - (num_args - num_default)
                    if default_idx >= 0:
                        default = node.args.defaults[default_idx]
                    else:
                        default = None
                    param_name, input_def = extract_input(arg, default)
                    cab_def[node.name]["inputs"][param_name] = input_def

                # rerder to place outputs last
                outputs = cab_def[node.name].pop("outputs")
                cab_def[node.name]["outputs"] = outputs

                # Generate YAML
                # Use safe_dump with nice formatting
                yaml_content = yaml.safe_dump(
                    cab_def,
                    default_flow_style=False,
                    sort_keys=False,
                    indent=2,
                )

                # Write the YAML file
                if output_dir:
                    output_dir = Path(output_dir)
                    # Create parent directory if it doesn't exist
                    output_dir.parent.mkdir(parents=True, exist_ok=True)
                    output_file = output_dir / f"{node.name}.yml"
                    with open(output_file, "w") as f:
                        f.write(yaml_content)
                else:  # else write to terminal
                    print(yaml_content)
