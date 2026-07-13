"""Transpile a restricted-subset stimela recipe into a Ray runner package.

Implements the `hip-cargo transpile` pipeline: parse -> validate -> infer ->
emit (see docs/wiki/transpile.md). The parser front-end is shared with the
monitoring stack (`monitoring/recipe_parser.py`, `monitoring/cab_resolver.py`);
this module never imports the wrapped science package — in-memory siblings are
detected statically via `importlib.util.find_spec` + a LibCST source scan.
"""

import re
from dataclasses import dataclass

from hip_cargo.monitoring.recipe_parser import RecipeDAG, RecipeStep

_INTERP_REF_RE = re.compile(r"\{recipe\.([\w-]+)\}")
_PURE_REF_RE = re.compile(r"^recipe\.([\w-]+)$")
_IMPORT_PATH_RE = re.compile(r"^[A-Za-z_][\w]*(\.[A-Za-z_][\w]*)+$")
_PATH_DTYPES = {"File", "Directory", "MS", "URI"}


@dataclass(frozen=True)
class TranspileError:
    """One named, actionable refusal from the restricted-subset validator.

    Args:
        feature: Short name of the unsupported feature (e.g. "formula-dsl").
        location: Where it was found (e.g. "step 'first', param 'n-items'").
        message: Human/agent-readable explanation with the RFC exclusion.
    """

    feature: str
    location: str
    message: str

    def __str__(self) -> str:
        return f"[{self.feature}] {self.location}: {self.message}"


def _interp_refs(value: object) -> list[str]:
    """Extract {recipe.x} interpolation references from a literal value."""
    if not isinstance(value, str):
        return []
    return _INTERP_REF_RE.findall(value)


def validate_recipe(dag: RecipeDAG) -> list[TranspileError]:
    """Check a parsed recipe against the restricted transpile subset.

    Collects every violation rather than failing fast, so a user migrating an
    existing stimela recipe sees the full distance to the subset at once
    (RFC transpile-rfc.md §11, migration story).

    Args:
        dag: Parsed recipe (with cab schemas resolved).

    Returns:
        All violations found; empty when the recipe is transpilable.
    """
    errors: list[TranspileError] = []
    input_names = {i.name for i in dag.inputs}

    for inp in dag.inputs:
        if inp.aliases:
            errors.append(
                TranspileError(
                    feature="aliases",
                    location=f"input '{inp.name}'",
                    message=(
                        f"alias patterns {inp.aliases} broadcast values to step params at run time; "
                        "aliases are excluded from the restricted subset (RFC §6) — bind each step "
                        "param explicitly with =recipe.x instead"
                    ),
                )
            )

    for step in dag.steps:
        loc_step = f"step '{step.name}'"
        for key in step.extra_keys:
            errors.append(
                TranspileError(
                    feature=key,
                    location=loc_step,
                    message=(
                        f"step key '{key}' (loops / nested recipes / merges) is excluded from the "
                        "restricted subset (RFC §6); flatten the recipe to plain linear steps"
                    ),
                )
            )

        schema = step.cab_schema
        if schema is None:
            errors.append(
                TranspileError(
                    feature="unresolved-cab",
                    location=loc_step,
                    message=(
                        f"cab '{step.cab}' could not be resolved from the recipe's _include entries; "
                        "the cab package must be importable (a lightweight install suffices)"
                    ),
                )
            )
        else:
            command = schema.get("command", "")
            if not _IMPORT_PATH_RE.match(command or ""):
                errors.append(
                    TranspileError(
                        feature="non-python-cab",
                        location=loc_step,
                        message=(
                            f"cab '{step.cab}' command {command!r} is not an importable "
                            "module.function path; only python-flavour cabs are transpilable (RFC §6)"
                        ),
                    )
                )
            errors.extend(_validate_required_bound(step))

        for param in step.params:
            loc = f"{loc_step}, param '{param.name}'"
            if param.is_binding:
                match = _PURE_REF_RE.match(param.binding_expr or "")
                if not match:
                    errors.append(
                        TranspileError(
                            feature="formula-dsl",
                            location=loc,
                            message=(
                                f"binding '={param.binding_expr}' is not a plain =recipe.<input> "
                                "reference; the formula DSL (=IF/=IFSET/arithmetic) is excluded "
                                "from the restricted subset (RFC §6, §2.2)"
                            ),
                        )
                    )
                elif match.group(1) not in input_names:
                    errors.append(
                        TranspileError(
                            feature="unknown-ref",
                            location=loc,
                            message=f"'recipe.{match.group(1)}' does not name a recipe input",
                        )
                    )
            else:
                for ref in _interp_refs(param.value):
                    if ref not in input_names:
                        errors.append(
                            TranspileError(
                                feature="unknown-ref",
                                location=loc,
                                message=f"interpolation '{{recipe.{ref}}}' does not name a recipe input",
                            )
                        )

    return errors


def _validate_required_bound(step: RecipeStep) -> list[TranspileError]:
    """Flag required cab inputs that are neither bound nor defaulted."""
    errors = []
    bound = {p.name for p in step.params}
    for name, param in (step.cab_schema or {}).get("inputs", {}).items():
        if param.get("required") and param.get("default") is None and name not in bound:
            errors.append(
                TranspileError(
                    feature="unbound-required",
                    location=f"step '{step.name}'",
                    message=f"required cab input '{name}' of cab '{step.cab}' is not bound in the recipe",
                )
            )
    return errors
