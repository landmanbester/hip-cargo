"""Parser for stimela recipe YAML files.

Extracts DAG structure (steps, edges, parameter bindings) from recipe files
to power frontend flow diagrams and pipeline launch forms. Does NOT evaluate
stimela expressions — only parses and classifies them.
"""

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

_RECIPE_REF_RE = re.compile(r"recipe\.[\w-]+")
_SKIP_KEYS = {"_include", "opts"}


@dataclass
class RecipeInput:
    """A recipe-level input parameter.

    Args:
        name: Parameter name (as in YAML, with hyphens preserved).
        dtype: Stimela type string (e.g. "str", "List[URI]", "Directory").
        required: Whether the input is required.
        default: Default value, if any.
        info: Help text.
        aliases: Glob patterns that broadcast this value to matching step params.
        mkdir: Whether to create the directory if it doesn't exist.
    """

    name: str
    dtype: str | None = None
    required: bool = False
    default: Any = None
    info: str = ""
    aliases: list[str] = field(default_factory=list)
    mkdir: bool = False


@dataclass
class StepParam:
    """A single parameter binding within a recipe step.

    Args:
        name: Parameter name.
        value: Raw value from YAML.
        is_binding: True if the value is a stimela expression (starts with '=').
        binding_expr: The expression after '=' if is_binding.
        recipe_refs: Recipe input references extracted from the binding expression.
    """

    name: str
    value: Any
    is_binding: bool = False
    binding_expr: str | None = None
    recipe_refs: list[str] = field(default_factory=list)


@dataclass
class RecipeStep:
    """A step in the recipe DAG.

    Args:
        name: Step name (key in the steps dict).
        cab: Cab name to execute.
        info: Description.
        params: Parsed parameter bindings.
        order: Position in the step sequence.
    """

    name: str
    cab: str
    info: str = ""
    params: list[StepParam] = field(default_factory=list)
    order: int = 0


@dataclass
class RecipeDAG:
    """Top-level parsed recipe structure.

    Args:
        name: Human-readable recipe name.
        recipe_key: The YAML key for this recipe block.
        info: Description.
        inputs: Recipe-level input parameters.
        steps: Ordered recipe steps.
        edges: Execution order edges as (source_step, target_step) pairs.
        includes: Cab include paths from _include.
    """

    name: str
    recipe_key: str
    info: str = ""
    inputs: list[RecipeInput] = field(default_factory=list)
    steps: list[RecipeStep] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)
    includes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict suitable for JSON API responses."""
        d = asdict(self)
        # asdict converts tuples to lists, which is fine for JSON
        return d

    def step_names(self) -> list[str]:
        """Return ordered list of step names."""
        return [s.name for s in self.steps]

    def get_step(self, name: str) -> RecipeStep | None:
        """Look up a step by name."""
        for s in self.steps:
            if s.name == name:
                return s
        return None


def parse_param_binding(name: str, value: Any) -> StepParam:
    """Parse a single step parameter value into a StepParam.

    Args:
        name: Parameter name.
        value: Raw value from YAML (may be a literal or a '='-prefixed binding).

    Returns:
        A StepParam with binding info populated if applicable.
    """
    if isinstance(value, str) and value.startswith("="):
        expr = value[1:]
        refs = _RECIPE_REF_RE.findall(expr)
        return StepParam(name=name, value=value, is_binding=True, binding_expr=expr, recipe_refs=refs)
    return StepParam(name=name, value=value)


def find_recipe_block(parsed_yaml: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Find the recipe block in parsed YAML, skipping _include and opts.

    Args:
        parsed_yaml: The full parsed YAML dict.

    Returns:
        A (key, block) tuple for the first recipe block found.

    Raises:
        ValueError: If no recipe block is found.
    """
    for key, block in parsed_yaml.items():
        if key not in _SKIP_KEYS and isinstance(block, dict):
            return key, block
    raise ValueError("No recipe block found in YAML (expected a key other than _include and opts)")


def parse_recipe(recipe_path: str | Path) -> RecipeDAG:
    """Parse a stimela recipe YAML and extract the DAG structure.

    Args:
        recipe_path: Path to the recipe YAML file.

    Returns:
        A RecipeDAG with parsed inputs, steps, edges, and includes.
    """
    recipe_path = Path(recipe_path)
    with open(recipe_path) as f:
        parsed = yaml.safe_load(f)

    includes = parsed.get("_include", []) or []

    recipe_key, recipe_block = find_recipe_block(parsed)

    name = recipe_block.get("name", recipe_key)
    info = recipe_block.get("info", "")

    # Parse inputs
    inputs = []
    raw_inputs = recipe_block.get("inputs") or {}
    for input_name, input_def in raw_inputs.items():
        if input_def is None:
            input_def = {}
        inputs.append(
            RecipeInput(
                name=input_name,
                dtype=input_def.get("dtype"),
                required=input_def.get("required", False),
                default=input_def.get("default"),
                info=input_def.get("info", ""),
                aliases=input_def.get("aliases", []) or [],
                mkdir=input_def.get("mkdir", False),
            )
        )

    # Parse steps
    steps = []
    raw_steps = recipe_block.get("steps") or {}
    for order, (step_name, step_def) in enumerate(raw_steps.items()):
        if step_def is None:
            step_def = {}
        params = []
        for param_name, param_value in (step_def.get("params") or {}).items():
            params.append(parse_param_binding(param_name, param_value))
        steps.append(
            RecipeStep(
                name=step_name,
                cab=step_def.get("cab", ""),
                info=step_def.get("info", ""),
                params=params,
                order=order,
            )
        )

    # Build linear edges
    edges = []
    for i in range(len(steps) - 1):
        edges.append((steps[i].name, steps[i + 1].name))

    return RecipeDAG(
        name=name,
        recipe_key=recipe_key,
        info=info,
        inputs=inputs,
        steps=steps,
        edges=edges,
        includes=includes,
    )
