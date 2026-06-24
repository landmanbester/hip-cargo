# Testing & CI/CD Guidelines

Read this when editing `tests/**/*.py` or `.github/workflows/*.yml` files.

## 1. Test Infrastructure & Execution
* Tests must isolate temporary files using pytest's `tmp_path` / `tmp_path_factory` fixtures (preferred) or `tempfile.TemporaryDirectory()`.
* No test artifacts should ever be written to the repository directory.
* Tests must automatically clean up after themselves.
* Comment preservation is a core feature and must be tested through multiple roundtrip scenarios.
* **Autonomy Rule:** You are encouraged to update, modify, or remove existing tests as necessary when refactoring code to ensure the test suite accurately reflects the current state of the application and passes cleanly.
* **Remote URI testing.** Prefer fsspec's built-in `memory://` protocol for unit tests that exercise remote-URI behaviour — it requires no external credentials and is fast. Use it for `preflight_remote_must_exist`, mount skipping, scheme detection, etc.
* **Live-cloud tests are opt-in.** Any test that hits a real S3/GCS/Azure endpoint must be gated on an `HIP_CARGO_LIVE_S3`, `HIP_CARGO_LIVE_GCS`, or `HIP_CARGO_LIVE_AZURE` environment variable and must be excluded from the required CI checks.

## 2. Commit Messages
* Use [Conventional Commits](https://www.conventionalcommits.org/) format: `<type>: <description>`
* Types: `feat`, `fix`, `refactor`, `perf`, `docs`, `test`, `ci`, `deps`, `chore`
* Keep the first line under 72 characters
* Use imperative mood: "add support for X" not "added support for X"
* Optional scope in parentheses: `feat(init): add BSD-3-Clause license option`
* The changelog is auto-generated from these prefixes via git-cliff

## 3. Mandatory Linting
Always run linting after adding or modifying any code:
`uv run ruff format . && uv run ruff check . --fix`

This is mandatory. Do not consider a feature complete until linting passes cleanly. If `ruff check` reports errors that `--fix` cannot auto-correct, fix them manually before proceeding.

## 4. CI Workflow and `[skip checks]`
The CI pipeline relies on a custom `[skip checks]` tag, which operates differently from GitHub's native `[skip ci]`.
* The `update-cabs` workflow commits with `[skip checks]` in the message after the GitHub App regenerates cab definitions on merge to main.
* This custom tag allows the workflow to run but skips the heavy steps. This ensures required status checks always report a success status, satisfying branch protection rules.
* The CI workflow (`ci.yml`) evaluates the tag once at the workflow level:
  ```yaml
  env:
    SKIP_CHECKS: ${{ github.event_name == 'push' && contains(github.event.head_commit.message, '[skip checks]') }}
