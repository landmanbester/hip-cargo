# Testing & CI/CD Guidelines

Read this when editing `tests/**` or `.github/workflows/**` files.

## 1. Round-Trip Tests

The round-trip tests in `tests/test_roundtrip.py` are **not optional** — they
are how this project guarantees that the committed `cli/*.py` and the committed
`cabs/*.yml` agree. They check both directions, against the committed files:

```
cli/<cmd>.py  ──(generate-cabs)──►      == cabs/<cmd>.yml   (as a parsed document)
cabs/<cmd>.yml ──(generate-function)──► == cli/<cmd>.py     (byte for byte)
```

- A **forward** failure means the committed cab is stale: regenerate it (the
  pre-commit hook does this on commit).
- A **reverse** failure means `cli/<cmd>.py` is not in the shape hip-cargo emits.
  Do not hand-fix it: edit the cab and regenerate the module, or report a
  hip-cargo bug if the regeneration itself is wrong. **Fix the source, not the
  test.**

Commands are discovered, not listed: a new module under `cli/` is covered with
no change to the test file, and a `@stimela_cab` command without a committed cab
fails `test_every_decorated_command_has_a_committed_cab`. Modules whose name
starts with `_` are skipped. It reads `CONTAINER_IMAGE` from
`_container_image.py` with `ast` rather than importing the package, so it needs
no `[full]` install.

The same file checks two contracts the round trip cannot see:

- `test_the_core_function_accepts_what_the_wrapper_passes`: the wrapper calls
  `<cmd>_core(**params)`, so every CLI parameter name must be a parameter of the
  core function, and every core parameter without a default must come from the
  CLI. It parses `core/` with `ast`, so heavy imports are not needed. A
  generated import whose module or function no longer exists fails the test;
  it skips only a hand-written wrapper, a core function from another package,
  or one that `core/<cmd>.py` re-exports, aliases or defines conditionally
  (e.g. in a `try`/`except ImportError`) rather than with a single `def`.
- `test_every_cab_command_is_registered_on_the_cli`: a cab command missing from
  `cli/__init__.py` round-trips fine but is invisible on the CLI. This one
  imports the CLI app, which the lightweight install provides.

Both scaffolded test files set `pytestmark = pytest.mark.unit`, so `pytest -m
unit` keeps them. Mark new test files too: `--strict-markers` rejects unknown
markers, but an unmarked file is silently deselected by `-m`.

After upgrading hip-cargo, a reverse failure across every command usually means
the emitter changed in that release: regenerate `cli/*.py` from the cabs.

## 2. Test Infrastructure

- Use `tempfile.TemporaryDirectory()` for isolated temp files. No test artifacts
  should ever be written to the repo directory; tests must clean up after
  themselves.
- For remote-URI behaviour, prefer fsspec's built-in `memory://` protocol — it
  needs no credentials and is fast.
- Any test hitting a real S3/GCS/Azure endpoint must be opt-in (gated on an env
  var) and excluded from required CI checks.

## 3. Mandatory Dev Workflow

After every code change run:

```bash
uv run ruff format . && uv run ruff check . --fix
```

This is non-negotiable — the pre-commit hook and CI both enforce it, and
generated code is formatted with the same configuration, so divergence breaks
the round-trip.

**Keep the pre-commit ruff equal to the locked ruff.** The hook runs its own
ruff, pinned by `rev:` under `astral-sh/ruff-pre-commit` in
`.pre-commit-config.yaml`; CI and `generate-function` use the ruff in `uv.lock`.
When ruff moves in `uv.lock` (an upgrade or a Dependabot PR), set the hook's
`rev` to `v<that version>` in the same change and run
`pre-commit run --all-files`. `tests/test_precommit.py` fails until you do.
`hip-cargo init` pins them equal at creation.

**Keep the image's uv current.** The `Dockerfile` takes uv from a named stage
(`FROM ghcr.io/astral-sh/uv:<x.y.z> AS uv`) so Dependabot's monthly `docker`
updates can bump it; never turn it back into `COPY --from=<image>`, which
Dependabot cannot see. The image's uv must not lag the uv that writes
`uv.lock`. When a bump moves uv past the `uv_build` cap in `[build-system]`,
raise the cap to the next minor in the same change.

## 4. CI

- **CI matrix is bracketed:** the full test suite runs on the oldest and newest
  Python the full install supports, on x86 (`Tests (3.11)`, `Tests (3.14)`),
  plus one arm64 job at the newest (`Tests (3.14, arm64)`).
- **Python 3.10 is lightweight-only:** `Lightweight install (3.10)` installs the
  package without extras and runs `<CLI_COMMAND> --help`, which imports every
  `cli/` module. Its Python must equal the `requires-python` floor. Commands
  still run on 3.10 by dispatching into the container, which ships a newer
  Python. Do not add a 3.10 leg to the full test matrix.
- Changing job names renames required checks, so update the branch ruleset in
  the same change.
- **CI runs on pull requests only** (into the default branch or a long-lived
  `dev-*` integration branch), plus `workflow_dispatch`. A merge is not
  re-tested, since its PR already passed; a PR into any other branch (e.g. a
  stacked PR) runs only when the maintainer opts in with
  `gh workflow run ci.yml --ref <branch>`. Do not add a `push` trigger back. A PR is tested against its base as of the run, so the
  ruleset should require branches to be up to date (strict required checks);
  otherwise two PRs that pass separately can break the default branch
  together. A merge queue instead needs a `merge_group:` trigger in `ci.yml`.
  The tbump release commit never goes through a PR, so `publish.yml` runs the
  test suite before uploading to PyPI. Its `test` job's Python (`UV_PYTHON`
  and `setup-python`) must equal the newest Python in the `ci.yml` matrix;
  change them together if you cap `requires-python` lower.
- **Container images are multi-arch:** `publish-container.yml` builds amd64 and
  arm64 on native runners, pushes each by digest, and a `merge` job publishes
  one manifest under the real tags. A `meta` job computes tags, labels and
  annotations once: labels live in each image's config, so the per-arch builds
  set them; the merge job applies tags and index annotations. Drop the arm64
  build entry (and the arm64 test job) for an amd64-only project.

## 5. Commits

- Use [Conventional Commits](https://www.conventionalcommits.org/):
  `<type>: <description>` (`feat`, `fix`, `refactor`, `perf`, `docs`, `test`,
  `ci`, `deps`, `chore`). Imperative mood, first line under 72 chars.
- The `update-cabs` bot tags its commit `[skip checks]` so its own push does
  not re-trigger it; **do not** add that tag to human commits.
