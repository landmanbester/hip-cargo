# Testing & CI/CD Guidelines

Read this when editing `tests/**` or `.github/workflows/**` files.

## 1. Round-Trip Tests

The round-trip test in `tests/test_roundtrip.py` is **not optional** — it is how
this project guarantees that `cli/*.py` and `cabs/*.yml` agree. It runs:

```
cli/<cmd>.py  ──(generate-cabs)──►  cabs/<cmd>.yml  ──(generate-function)──►  <cmd>.py
```

…then asserts the regenerated `<cmd>.py` is byte-identical (after `ruff format`)
to the original `cli/<cmd>.py`. If you write a CLI wrapper in a shape that
hip-cargo cannot round-trip, the test fails and the cab is unreliable. **Fix the
source, not the test.**

Add a new round-trip case to `tests/test_roundtrip.py` whenever you add a new
command under `cli/`.

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

## 4. CI

- **CI matrix is bracketed:** tests run on the oldest and newest supported
  Python on x86 (`Tests (3.10)`, `Tests (3.14)`) plus one arm64 job at the
  newest (`Tests (3.14, arm64)`). The oldest must equal the `requires-python`
  floor: the lightweight install has to keep working there, while commands run
  in the container on a newer Python. Changing the matrix renames required
  checks, so the branch ruleset must be updated with it.
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
