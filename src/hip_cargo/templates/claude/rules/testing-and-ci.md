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
starts with `_` are skipped. The suite needs no install: it reads
`CONTAINER_IMAGE` from `_container_image.py` with `ast` rather than importing
the package.

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
- **Container images are multi-arch:** `publish-container.yml` builds amd64 and
  arm64 on native runners, pushes each by digest, and a `merge` job publishes
  one manifest under the real tags. Drop the arm64 build entry (and the arm64
  test job) for an amd64-only project.

## 5. Commits

- Use [Conventional Commits](https://www.conventionalcommits.org/):
  `<type>: <description>` (`feat`, `fix`, `refactor`, `perf`, `docs`, `test`,
  `ci`, `deps`, `chore`). Imperative mood, first line under 72 chars.
- The `update-cabs` bot uses `[skip checks]` to bypass required status checks;
  **do not** add that tag to human commits.
