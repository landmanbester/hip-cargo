# `hip-cargo transpile` v1 — Implementation Plan

> EPHEMERAL (same-session inline execution; full design in the sibling spec). Fold outcomes into `docs/wiki/transpile.md` and delete before finishing. TDD per task; lint + conventional commit after each.

**Global:** hip-cargo on `apis`; stokify on `transpile`. Test cmds: `uv run --extra monitoring python -m pytest tests/test_transpile*.py -v`. Commit trailer as per repo rule. `SKIP=generate-cabs` only for non-code commits; code commits let the hook regenerate cabs (tag stays `:apis` because the installed hip-cargo is the local editable checkout — verify on first commit).

### Task 1 — Front-end + fixtures + validation
- Verify `hip_cargo.monitoring` package imports light (no fastapi/ray at module import); fix `__init__.py` laziness if needed.
- `tests/fixtures/transpile/`: `fakepkg/` (installable-on-syspath mini package: `core/{alpha,beta}.py` with `alpha`/`alpha_inmem`, `beta` (no inmem), cabs YAML), recipes: `linear_ok.yml`, `formula.yml` (=IF), `alias.yml`, `loop.yml` (for_loop), `unknown_ref.yml`, `unbound_required.yml`.
- `core/transpile.py`: `TranspileError` dataclass; `validate_recipe(dag) -> list[TranspileError]`.
- Tests: each fixture produces exactly the expected error(s) naming the feature; `linear_ok` produces none.
- Commit: `feat(transpile): recipe validation with named refusals`

### Task 2 — IR + inference
- `Binding`, `StepSpec`, `RecipeSpec` frozen dataclasses; `build_recipe_spec(dag, package) -> RecipeSpec`.
- Data-edge inference (output↔input string match); inmem detection via `find_spec` + libcst scan incl. contract-signature check; slot mapping (`memory-mode`→slot, path drops, unique `work_dir` source, kwargs sanitisation); `lower_interpolation(value, inputs) -> str` (f-string).
- Tests: edges for linear_ok; alpha→inmem / beta→fallback; work_dir ambiguity error; lowering cases.
- Commit: `feat(transpile): recipe IR, data-edge inference, inmem detection`

### Task 3 — Codegen
- `render_tasks/render_runner/render_cli/render_init(spec) -> str`; `write_package(spec, output_dir)` (ruff subprocess, byte-compare idempotence).
- Tests: golden snapshot for linear_ok; generated modules pass `ruff check`; idempotent second write (mtime unchanged); bandit importorskip.
- Commit: `feat(transpile): emit tasks/runner/cli package`

### Task 4 — CLI + wiki page
- `cli/transpile.py` (File/Directory params, lazy core), register in `cli/__init__.py`; cab via hook.
- `docs/wiki/transpile.md` (status v1, grammar table, contract, usage, deferred: resources/§9.3, runtime_env application, nested/for_loop, packaging §9.5) + `log.md` entry.
- Commit: `feat(transpile): hip-cargo transpile command` (+ docs commit)

### Task 5 — stokify integration (branch `transpile`)
- Run real transpile → `src/stokify/transpiled/`; commit generated output.
- Register `stokify transpiled run`; structural test vs exemplars; slow e2e (tiny sizes, monitor, assert events + diagnostics); `demo.py --transpiled`.
- README "Transpilation" section.
- Commits on `transpile` branch.

### Task 6 — Close out
- Update wiki transpile.md to final state; fold spec+plan; `git rm` both; log.md.
- Full suites both repos (fast + slow); demo classic + `--transpiled` PASS.
- Push hip-cargo `apis`; stokify `transpile` stays local (no remote).
