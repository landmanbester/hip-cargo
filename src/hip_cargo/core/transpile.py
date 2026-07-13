"""Transpile a restricted-subset stimela recipe into a Ray runner package.

Implements the `hip-cargo transpile` pipeline: parse -> validate -> infer ->
emit (see docs/wiki/transpile.md). The parser front-end is shared with the
monitoring stack (`monitoring/recipe_parser.py`, `monitoring/cab_resolver.py`);
this module never imports the wrapped science package — in-memory siblings are
detected statically via `importlib.util.find_spec` + a LibCST source scan.
"""

import re
from dataclasses import dataclass, replace

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
    dtype: str | None = None  # stimela dtype from the cab schema, for typed codegen

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
        dtypes = {
            name: p.get("dtype") for section in ("inputs", "outputs") for name, p in schema.get(section, {}).items()
        }
        bindings = [replace(_classify_binding(p), dtype=dtypes.get(p.name)) for p in step.params]
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


# --- Codegen ---------------------------------------------------------------

_HEADER = """# Generated by `hip-cargo transpile` — do not edit.
# Source recipe: {source}
"""

_PY_TYPES = {"int": "int", "float": "float", "bool": "bool", "str": "str"}


def _py_type(dtype: str | None) -> str:
    return _PY_TYPES.get(dtype or "str", "str")


def _task_name(step: StepSpec) -> str:
    return f"{sanitize(step.name)}_task"


def _kwarg_sig(binding: Binding) -> str:
    return f"{sanitize(binding.name)}: {_py_type(binding.dtype)}"


def render_tasks(spec: RecipeSpec) -> str:
    """Render the per-step @ray.remote task module."""
    blocks = [
        _HEADER.format(source=spec.source),
        f'"""Per-step @ray.remote task wrappers for the {spec.name!r} pipeline."""',
        "",
        "import os",
        "",
        'os.environ.setdefault("RAY_ENABLE_UV_RUN_RUNTIME_ENV", "0")',
        "",
        "import ray  # noqa: E402",
        "",
        "",
        "def _activate_backend() -> None:",
        '    """Register the shared aggregator backend inside this worker process."""',
        "    from hip_cargo.monitoring.ray_backend import RayProgressBackend, get_or_create_aggregator",
        "    from hip_cargo.utils.progress import set_backend",
        "",
        "    set_backend(RayProgressBackend(get_or_create_aggregator()))",
    ]

    for step in spec.steps:
        blocks.append("")
        blocks.append("")
        blocks.append("@ray.remote")
        if step.inmem_func is not None:
            sig = ['dataset: "object"'] if step.upstream else []
            sig += ["memory_mode: str", "job_id: str", "work_dir: str", "monitor: bool"]
            sig += [_kwarg_sig(b) for b in step.kwargs]
            blocks.append(f'def {_task_name(step)}({", ".join(sig)}) -> "object":')
            blocks.append(f'    """Run step {step.name!r} (cab {step.cab!r}) in-memory."""')
            blocks += _task_body_common(step)
            call = ["dataset"] if step.upstream else []
            call += ["memory_mode", "job_id", "job_id", "work_dir"]
            call += [f"{sanitize(b.name)}={sanitize(b.name)}" for b in step.kwargs]
            blocks.append(f"    return {step.inmem_func}({', '.join(call)})")
        else:
            sig = ['_upstream: "object"'] if step.upstream else []
            sig += ["job_id: str", "monitor: bool"]
            sig += [f"{sanitize(b.name)}: {_py_type(b.dtype)}" for b in step.all_bindings]
            blocks.append(f'def {_task_name(step)}({", ".join(sig)}) -> "object":')
            blocks.append(
                f'    """Run step {step.name!r} (cab {step.cab!r}) via its disk command (no _inmem sibling)."""'
            )
            blocks += _task_body_common(step, inmem=False)
            call = [f"{sanitize(b.name)}={sanitize(b.name)}" for b in step.all_bindings]
            blocks.append(f"    return {step.func}({', '.join(call)})")

    return "\n".join(blocks) + "\n"


def _task_body_common(step: StepSpec, inmem: bool = True) -> list[str]:
    """Shared task-body preamble: backend activation, timed import, diagnostics."""
    func = step.inmem_func if inmem else step.func
    annotate = 'annotate_diagnostics(import_s=_time.perf_counter() - _t0, requested={"num_cpus": 1}'
    if inmem:
        annotate += ", memory_mode=memory_mode"
    annotate += ")"
    return [
        "    if monitor:",
        "        _activate_backend()",
        "    import time as _time",
        "",
        "    _t0 = _time.perf_counter()",
        f"    from {step.module} import {func}",
        "",
        "    if monitor:",
        "        from hip_cargo.utils.diagnostics import annotate_diagnostics",
        "",
        f"        {annotate}",
    ]


def render_runner(spec: RecipeSpec, out_package: str) -> str:
    """Render the ObjectRef-chaining pipeline runner module."""
    has_memory_mode = any(i["name"] == "memory-mode" for i in spec.inputs)
    steps_list = ", ".join(repr(s.name) for s in spec.steps)
    edges_list = ", ".join(f"[{p!r}, {c!r}]" for p, c in spec.edges)

    params, mkdirs = [], []
    for inp in spec.inputs:
        py = sanitize(inp["name"])
        py_t = "str" if (inp["dtype"] or "") in _PATH_DTYPES else _py_type(inp["dtype"])
        if inp["required"] and inp["default"] is None:
            params.append(f"{py}: {py_t}")
        else:
            params.append(f"{py}: {py_t} = {inp['default']!r}")
        if inp.get("mkdir"):
            mkdirs.append(py)
    params += ["monitor: bool = False", "job_id: str | None = None", "ray_address: str | None = None"]

    lines = [
        _HEADER.format(source=spec.source),
        f'"""ObjectRef-chaining pipeline runner for the {spec.name!r} recipe."""',
        "",
        "import os",
        "",
        'os.environ.setdefault("RAY_ENABLE_UV_RUN_RUNTIME_ENV", "0")',
        "",
        "import uuid  # noqa: E402",
        "",
        "from hip_cargo.utils.progress import EventType, ProgressEvent, emit  # noqa: E402",
        "",
        f"STEPS = [{steps_list}]",
        f"EDGES = [{edges_list}]",
        "",
        "",
        "def _emit(event_type: EventType, job_id: str, worker_name: str, message: str = '', extra: dict | None = None) -> None:",  # noqa: E501
        '    """Emit a pipeline-level event through the active backend."""',
        "    emit(ProgressEvent(job_id=job_id, worker_name=worker_name, event_type=event_type, message=message, extra=extra or {}))",  # noqa: E501
        "",
        "",
        f"def run_pipeline({', '.join(params)}) -> 'tuple[str, object]':",
        f'    """Run the {spec.name!r} pipeline on a Ray cluster; returns (job_id, final ObjectRef)."""',
        "    import ray",
        "",
        f"    from {out_package} import tasks",
        "",
        "    if job_id is None:",
        "        job_id = uuid.uuid4().hex[:8]",
        "    if not ray.is_initialized():",
        f"        ray.init(address=ray_address, namespace={spec.package!r}, ignore_reinit_error=True)",
        "    if monitor:",
        "        from hip_cargo.monitoring.ray_backend import RayProgressBackend, get_or_create_aggregator",
        "        from hip_cargo.utils.progress import set_backend",
        "",
        "        set_backend(RayProgressBackend(get_or_create_aggregator()))",
        "",
    ]
    for py in mkdirs:
        lines.append(f"    {py} = str({py})")
        lines.append(f"    os.makedirs({py}, exist_ok=True)")
    if mkdirs:
        lines.append("")

    if has_memory_mode:
        started_extra = '{"steps": STEPS, "edges": EDGES, "memory_mode": memory_mode}'
        started_msg = 'f"memory_mode={memory_mode}"'
    else:
        started_extra = '{"steps": STEPS, "edges": EDGES}'
        started_msg = "''"
    lines.append(
        f"    _emit(EventType.PIPELINE_STARTED, job_id, {spec.name!r}, message={started_msg}, extra={started_extra})"
    )

    prev_ref = None
    for index, step in enumerate(spec.steps):
        ref = f"ref_{sanitize(step.name)}"
        if step.inmem_func is not None:
            mm = step.memory_mode.as_python() if step.memory_mode else "'greedy'"
            args = [f"ref_{sanitize(step.upstream)}"] if step.upstream else []
            args += [mm, "job_id", sanitize(step.work_dir_input), "monitor"]
            args += [f"{sanitize(b.name)}={b.as_python()}" for b in step.kwargs]
        else:
            args = [f"ref_{sanitize(step.upstream)}"] if step.upstream else []
            args += ["job_id", "monitor"]
            args += [f"{sanitize(b.name)}={b.as_python()}" for b in step.all_bindings]
        lines += [
            "",
            f'    _emit(EventType.STEP_STARTED, job_id, {step.name!r}, extra={{"step_index": {index}}})',
            f"    {ref} = tasks.{_task_name(step)}.remote({', '.join(args)})",
            f"    ray.wait([{ref}])",
            f'    _emit(EventType.STEP_COMPLETED, job_id, {step.name!r}, extra={{"step_index": {index}}})',
        ]
        prev_ref = ref

    lines += [
        "",
        f"    _emit(EventType.COMPLETED, job_id, {spec.name!r}, message='pipeline complete')",
        f"    return job_id, {prev_ref}",
    ]
    return "\n".join(lines) + "\n"


def render_cli(spec: RecipeSpec, out_package: str) -> str:
    """Render the Typer driver CLI module from the recipe's inputs."""
    from hip_cargo.utils.cab_to_function import generate_parameter_signature

    has_path_input = any((i["dtype"] or "") in _PATH_DTYPES for i in spec.inputs)

    param_blocks = []
    for inp in spec.inputs:
        param_def = {k: v for k, v in inp.items() if k in ("dtype", "info", "default", "required") and v is not None}
        param_blocks.append(generate_parameter_signature(inp["name"], param_def))
    param_blocks += [
        '    monitor: Annotated[\n        bool,\n        typer.Option(\n            help="Stream progress events to the monitoring aggregator.",\n        ),\n    ] = False,',  # noqa: E501
        '    job_id: Annotated[\n        str | None,\n        typer.Option(\n            help="Fixed job id (useful for following a run live).",\n        ),\n    ] = None,',  # noqa: E501
        '    ray_address: Annotated[\n        str | None,\n        typer.Option(\n            help="Ray cluster address; omit to start/use a local cluster.",\n        ),\n    ] = None,',  # noqa: E501
    ]

    forward = [
        f"{sanitize(i['name'])}=str({sanitize(i['name'])})"
        if (i["dtype"] or "") in _PATH_DTYPES
        else f"{sanitize(i['name'])}={sanitize(i['name'])}"
        for i in spec.inputs
    ]
    forward += ["monitor=monitor", "job_id=job_id", "ray_address=ray_address"]

    lines = [
        _HEADER.format(source=spec.source),
        f'"""Typer driver CLI for the {spec.name!r} pipeline."""',
        "",
        "import uuid",
        "from typing import Annotated",
        "",
        "import typer",
    ]
    if has_path_input:
        path_dtypes = sorted({(i["dtype"] or "") for i in spec.inputs if (i["dtype"] or "") in _PATH_DTYPES})
        lines[lines.index("from typing import Annotated")] = "from typing import Annotated, NewType"
        lines.insert(lines.index("import uuid"), "from pathlib import Path")
        lines.insert(lines.index("import uuid"), "")
        lines.append("from hip_cargo import parse_upath")
        lines.append("")
        for dtype in path_dtypes:
            lines.append(f'{dtype} = NewType("{dtype}", Path)')
    lines += [
        "",
        f'app = typer.Typer(help="Transpiled driver for the {spec.name!r} recipe.")',
        "",
        "",
        "@app.command()",
        "def run(",
        *param_blocks,
        "):",
        f'    """Run the {spec.name!r} pipeline on a Ray cluster."""',
        f"    from {out_package}.runner import run_pipeline",
        "",
        "    if job_id is None:",
        "        job_id = uuid.uuid4().hex[:8]",
        '    typer.echo(f"job_id={job_id}")',
        f"    run_pipeline({', '.join(forward)})",
        '    typer.echo(f"pipeline complete: job_id={job_id}")',
    ]
    return "\n".join(lines) + "\n"


def render_init(spec: RecipeSpec) -> str:
    """Render the generated package __init__."""
    return _HEADER.format(source=spec.source) + f'"""Transpiled Ray pipeline package for the {spec.name!r} recipe."""\n'


def write_package(spec: RecipeSpec, output_dir, out_package: str | None = None) -> list:
    """Render, format, and write the transpiled package (idempotently).

    Args:
        spec: The recipe IR.
        output_dir: Directory to write the package into (created if missing).
        out_package: Dotted import path of the emitted package; defaults to
            `<root package>.<output_dir name>` (e.g. "stokify.transpiled").

    Returns:
        List of Paths actually (re)written — unchanged files are skipped.
    """
    from pathlib import Path

    from hip_cargo.utils.config import find_pyproject_toml

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if out_package is None:
        out_package = f"{spec.package}.{output_dir.name}"

    config_file = find_pyproject_toml(output_dir)
    modules = {
        "__init__.py": render_init(spec),
        "tasks.py": render_tasks(spec),
        "runner.py": render_runner(spec, out_package),
        "cli.py": render_cli(spec, out_package),
    }

    written = []
    for filename, source in modules.items():
        formatted = _ruff_pipe(source, config_file)
        target = output_dir / filename
        if target.exists() and target.read_text() == formatted:
            continue
        target.write_text(formatted)
        written.append(target)
    return written


def _ruff_pipe(source: str, config_file) -> str:
    """Format-first ruff pipeline for generated modules.

    `ruff format` runs before `ruff check --fix` because long generated lines
    (E501) are only fixable by the formatter; the trailing format pass cleans
    up after any check fixes.
    """
    import subprocess
    import warnings
    from pathlib import Path

    fmt_cmd = ["ruff", "format", "--stdin-filename", "generated.py", "-"]
    check_cmd = ["ruff", "check", "--fix", "--exit-zero", "--stdin-filename", "generated.py", "-"]
    cwd = None
    if config_file is not None:
        fmt_cmd.extend(["--config", str(config_file)])
        check_cmd.extend(["--config", str(config_file)])
        cwd = str(Path(config_file).resolve().parent)
    try:
        run = lambda cmd, text: subprocess.run(cmd, input=text, capture_output=True, text=True, check=True, cwd=cwd)  # noqa: E731
        return run(fmt_cmd, run(check_cmd, run(fmt_cmd, source).stdout).stdout).stdout
    except (subprocess.CalledProcessError, OSError) as e:
        warnings.warn(f"Ruff unavailable/failed during transpile; emitting unformatted source: {e}")
        return source


def transpile_recipe(recipe_path, output_dir, out_package: str | None = None) -> list:
    """Full pipeline: parse -> validate -> build IR -> emit package.

    Args:
        recipe_path: Recipe YAML path.
        output_dir: Target directory for the generated package.
        out_package: Dotted import path override for the emitted package.

    Returns:
        List of written file Paths.

    Raises:
        TranspileRefusedError: When the recipe falls outside the restricted subset.
    """
    from pathlib import Path

    from hip_cargo.monitoring.recipe_parser import parse_recipe
    from hip_cargo.utils.config import find_pyproject_toml

    dag = parse_recipe(recipe_path, resolve_cabs=True)
    errors = validate_recipe(dag)
    if errors:
        raise TranspileRefusedError(errors)

    # Record the recipe path project-relative so the generated header (and
    # therefore idempotence) does not depend on how the path was spelled.
    resolved = Path(recipe_path).resolve()
    source = str(resolved)
    config_file = find_pyproject_toml(Path(output_dir).resolve())
    if config_file is not None:
        try:
            source = str(resolved.relative_to(config_file.parent))
        except ValueError:
            pass
    spec = build_recipe_spec(dag, source=source)
    return write_package(spec, output_dir, out_package)
