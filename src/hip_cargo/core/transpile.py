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


def sanitize(name: str) -> str:
    """Hyphenated YAML name -> Python identifier."""
    return name.replace("-", "_")


@dataclass(frozen=True)
class Binding:
    """A step parameter binding classified for codegen.

    Args:
        name: Cab parameter name (hyphenated, as in YAML).
        kind: "literal", "ref" (=recipe.x), or "interp" ({recipe.x} in a string).
        value: Raw YAML value (for ref kinds, the referenced input name).
        refs: Recipe input names referenced (empty for literals).
    """

    name: str
    kind: str
    value: object
    refs: tuple[str, ...] = ()

    def as_python(self) -> str:
        """Render the binding's value as a Python expression over sanitised input names."""
        if self.kind == "ref":
            return sanitize(str(self.value))
        if self.kind == "interp":
            return lower_interpolation(str(self.value))
        return repr(self.value)


@dataclass(frozen=True)
class StepSpec:
    """One transpiled step: everything codegen needs, nothing it doesn't.

    Args:
        name: Step name from the recipe.
        cab: Cab name.
        module: Import path of the command's module (e.g. "stokify.core.init").
        func: Command function name (e.g. "init").
        inmem_func: The detected `<func>_inmem` sibling, or None (disk fallback).
        upstream: Producer step name whose dataset this step consumes, or None.
        work_dir_input: Recipe input name that roots this step's paths (inmem mode).
        memory_mode: Binding for the memory-mode slot, or None (literal "greedy").
        kwargs: Non-path, non-slot bindings passed as keyword arguments.
        all_bindings: Every binding (used by the disk-fallback call).
        dropped: Path-dtype parameter names dropped in inmem mode.
    """

    name: str
    cab: str
    module: str
    func: str
    inmem_func: str | None
    upstream: str | None
    work_dir_input: str | None
    memory_mode: Binding | None
    kwargs: tuple[Binding, ...]
    all_bindings: tuple[Binding, ...]
    dropped: tuple[str, ...]


@dataclass(frozen=True)
class RecipeSpec:
    """Neutral facts of a validated recipe, shaped for the code generators.

    Args:
        name: Recipe name.
        package: Root package of the wrapped functions (Ray namespace).
        inputs: Recipe inputs as plain dicts (name, dtype, default, info, required, mkdir).
        steps: Ordered step specs.
        edges: Data edges as (producer, consumer) pairs.
        source: Recipe path, recorded in generated headers.
    """

    name: str
    package: str
    inputs: tuple[dict, ...]
    steps: tuple[StepSpec, ...]
    edges: tuple[tuple[str, str], ...]
    source: str


class TranspileRefusedError(Exception):
    """Raised when a recipe cannot be transpiled; carries all TranspileErrors."""

    def __init__(self, errors: list[TranspileError]) -> None:
        self.errors = errors
        super().__init__("\n".join(str(e) for e in errors))


def lower_interpolation(value: str) -> str:
    """Lower a '{recipe.x}/tail' interpolation to a Python f-string literal.

    Args:
        value: The raw YAML string containing {recipe.<input>} references.

    Returns:
        Python source for an f-string over sanitised input names, or a plain
        repr when the string holds no references.
    """
    if not _INTERP_REF_RE.search(value):
        return repr(value)
    lowered = value.replace("{", "{{").replace("}", "}}")
    for ref in set(_INTERP_REF_RE.findall(value)):
        lowered = lowered.replace(f"{{{{recipe.{ref}}}}}", f"{{{sanitize(ref)}}}")
    return 'f"' + lowered.replace('"', '\\"') + '"'


def _classify_binding(param) -> Binding:
    """Turn a parsed StepParam into a codegen Binding."""
    if param.is_binding:
        match = _PURE_REF_RE.match(param.binding_expr or "")
        return Binding(name=param.name, kind="ref", value=match.group(1), refs=(match.group(1),))
    refs = tuple(_interp_refs(param.value))
    if refs:
        return Binding(name=param.name, kind="interp", value=param.value, refs=refs)
    return Binding(name=param.name, kind="literal", value=param.value)


def find_inmem(command: str) -> tuple[str, list[str]] | None:
    """Statically detect a `<func>_inmem` sibling of a cab command.

    Locates the command's module via `importlib.util.find_spec` (parent
    package __init__ files execute, but hip-cargo-style packages keep those
    light) and scans the module *source* with LibCST — the module itself is
    never imported, so the science stack is never loaded.

    Args:
        command: The cab's `module.func` import path.

    Returns:
        (inmem_function_name, parameter_names) when found, else None.
    """
    import importlib.util
    from pathlib import Path

    import libcst

    module_path, func = command.rsplit(".", 1)
    try:
        spec = importlib.util.find_spec(module_path)
    except (ImportError, ModuleNotFoundError):
        return None
    if spec is None or spec.origin is None:
        return None

    target = f"{func}_inmem"
    module = libcst.parse_module(Path(spec.origin).read_text())
    for node in module.body:
        if isinstance(node, libcst.FunctionDef) and node.name.value == target:
            params = [p.name.value for p in node.params.params]
            return target, params
    return None


_CONTRACT_SLOTS = ["memory_mode", "job_id", "pipeline_run_id", "work_dir"]


def infer_data_edges(dag: RecipeDAG) -> list[tuple[str, str, str]]:
    """Infer data edges from matching output/input path bindings.

    A producer's *output* binding string equal to a later step's *input*
    binding string is a data edge — the recipe expressed the handoff as a
    shared path; the transpiler recovers the true dependency from it.

    Args:
        dag: Parsed recipe with cab schemas resolved.

    Returns:
        (producer_step, consumer_step, consumer_param) triples.
    """
    edges = []
    for i, producer in enumerate(dag.steps):
        out_names = set((producer.cab_schema or {}).get("outputs", {}))
        out_values = {p.value for p in producer.params if p.name in out_names and isinstance(p.value, str)}
        if not out_values:
            continue
        for consumer in dag.steps[i + 1 :]:
            in_names = set((consumer.cab_schema or {}).get("inputs", {}))
            for param in consumer.params:
                if param.name in in_names and param.value in out_values:
                    edges.append((producer.name, consumer.name, param.name))
    return edges


def build_recipe_spec(dag: RecipeDAG, source: str = "") -> RecipeSpec:
    """Build the codegen IR from a validated recipe.

    Args:
        dag: Parsed recipe; must already have passed `validate_recipe`.
        source: Recipe path recorded in generated file headers.

    Returns:
        The RecipeSpec both generators consume.

    Raises:
        TranspileRefusedError: On structural problems only visible at build time
            (multiple upstreams, ambiguous work_dir, contract violations).
    """
    errors: list[TranspileError] = []
    data_edges = infer_data_edges(dag)

    package = ""
    steps: list[StepSpec] = []
    for step in dag.steps:
        schema = step.cab_schema or {}
        command = schema.get("command", "")
        module, func = command.rsplit(".", 1)
        package = package or module.split(".")[0]

        upstreams = sorted({p for p, c, _ in data_edges if c == step.name})
        if len(upstreams) > 1:
            errors.append(
                TranspileError(
                    feature="multiple-upstreams",
                    location=f"step '{step.name}'",
                    message=f"consumes outputs of {upstreams}; v1 transpiles linear chains only",
                )
            )
        upstream = upstreams[0] if upstreams else None

        path_params = {
            name
            for section in ("inputs", "outputs")
            for name, p in schema.get(section, {}).items()
            if (p.get("dtype") or "") in _PATH_DTYPES
        }
        bindings = [_classify_binding(p) for p in step.params]
        path_bindings = [b for b in bindings if b.name in path_params]

        work_dir_refs = sorted({r for b in path_bindings for r in b.refs})
        work_dir_input = work_dir_refs[0] if len(work_dir_refs) == 1 else None

        memory_mode = next((b for b in bindings if b.name == "memory-mode"), None)
        kwargs = tuple(b for b in bindings if b.name not in path_params and b.name != "memory-mode")

        inmem = find_inmem(command)
        inmem_func = None
        if inmem is not None:
            inmem_func, inmem_params = inmem
            expected = (["<dataset>"] if upstream else []) + _CONTRACT_SLOTS
            got = inmem_params[: len(expected)]
            slots_ok = got[1:] == _CONTRACT_SLOTS if upstream else got == _CONTRACT_SLOTS
            if len(got) < len(expected) or not slots_ok:
                errors.append(
                    TranspileError(
                        feature="inmem-contract",
                        location=f"step '{step.name}'",
                        message=(
                            f"{module}.{inmem_func} does not follow the v1 in-memory contract "
                            f"([dataset,] memory_mode, job_id, pipeline_run_id, work_dir, ...); "
                            f"found parameters {inmem_params}"
                        ),
                    )
                )
                inmem_func = None
            elif work_dir_input is None:
                errors.append(
                    TranspileError(
                        feature="ambiguous-work-dir",
                        location=f"step '{step.name}'",
                        message=(
                            f"cannot derive work_dir: path bindings reference {work_dir_refs or 'no'} "
                            "recipe inputs; exactly one Directory-rooting input is required for "
                            "in-memory transpilation"
                        ),
                    )
                )

        steps.append(
            StepSpec(
                name=step.name,
                cab=step.cab,
                module=module,
                func=func,
                inmem_func=inmem_func,
                upstream=upstream,
                work_dir_input=work_dir_input,
                memory_mode=memory_mode,
                kwargs=kwargs,
                all_bindings=tuple(bindings),
                dropped=tuple(sorted(b.name for b in path_bindings)),
            )
        )

    if errors:
        raise TranspileRefusedError(errors)

    return RecipeSpec(
        name=dag.name,
        package=package,
        inputs=tuple(
            {
                "name": i.name,
                "dtype": i.dtype,
                "required": i.required,
                "default": i.default,
                "info": i.info,
                "mkdir": i.mkdir,
            }
            for i in dag.inputs
        ),
        steps=tuple(steps),
        edges=tuple((p, c) for p, c, _ in data_edges),
        source=source,
    )
