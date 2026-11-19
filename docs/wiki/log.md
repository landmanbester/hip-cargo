---
type: log
title: Wiki changelog
description: Chronological record of wiki updates.
timestamp: 2026-11-19
last_verified_commit: 1f7327c
---

# Wiki changelog

## 2026-11-19 — `container-execution.md`: release tests, fallback reason (verified at `1f7327c`)

- `publish.yml` runs the test suite before PyPI, since CI never sees the
  tbump release commit.
- The generated wrapper prints the caught `ImportError` before falling back.

## 2026-11-19 — `container-execution.md`: fallback scope, CI triggers, hooks (verified at `70b29f0`)

- The generated wrapper re-raises an `ImportError` named in the command's own
  package instead of falling back; lazy `[full]` imports are #132.
- `ci.yml` runs on pull requests only, so the `update-cabs` bot commit is
  never tested and `[skip checks]` only stops that workflow re-triggering.
- Hooks and tbump run `uv run --no-sync hip-cargo`; any `git+` line in the
  lock export needs `git` in the image; noted the PyPI/image release race.

## 2026-11-19 — `container-execution.md`: Dependabot-visible uv stage (verified at `6aa584a`)

- uv enters the image from a named `FROM ... AS uv` stage (bumped to 0.13.9)
  so the new `docker` Dependabot entry can update it; `python` minor/major
  updates are ignored. `uv_build` cap raised to `<0.14.0`.
- Repaired the multi-arch paragraph, which the previous entry had split.

## 2026-11-18 — `container-execution.md`: image labels on multi-arch builds (verified at `04c5e48`)

- `publish-container.yml` gained a `meta` job; per-arch builds set the OCI
  labels again (lost in the #121 split) and the merge job adds index
  annotations.
- The `Dockerfile` (own and template) installs from `uv.lock` with
  `uv export --locked`, so both architectures get the same versions.

## 2026-11-17 — `remote-uris.md`: remote support stops at the wrapper (verified at `aeaaa4a`)

- Added the #96 caveat: hip-cargo makes the CLI accept remote URIs; whether a
  command works on one depends on its `core/`, which may be local-only in both
  execution modes.

## 2026-11-17 — `cli-dialect.md`: two-way round-trip template (verified at `359c0ac`)

- The scaffolded `tests/test_roundtrip.py` now checks both directions against
  the committed `cli/` and `cabs/`, discovers commands, and needs no install
  (#115).

## 2026-11-17 — `cab-yaml-emission.md`: value-checked info rewrite (verified at `dbbf133`)

- Replaced "What the guard does not catch" with how #116 closes it:
  `format_info_fields` decodes each scalar with YAML and keeps only a rendering
  that reloads to the same value; `allow_unicode=True` on the dump; non-literal
  numeric defaults raise.
- Recorded the gotcha that a parameter's inline comment is only read when
  `help=` is the last `typer.Option` argument with no trailing comma.

## 2026-11-17 — `remote-uris.md`: shared path NewTypes (verified at `6e40c1d`)

- `File`/`Directory`/`MS`/`URI` now live in `utils/types.py` and are exported
  from `hip_cargo`; generated modules import them instead of declaring
  `NewType(..., Path)` locally (#114).

## 2026-11-17 — `container-execution.md`, `remote-uris.md`: fallback scope and one `params` dict (verified at `24e1fa7`)

- Generated wrappers now guard only the core import and the remote pre-flight
  with `except ImportError`; the core call runs in `else:` so run-time
  `ImportError`s propagate (#120). One `params` dict feeds the pre-flight, the
  core call (`**params`) and `run_in_container` (#118), which also fixes the
  resolved container `image` shadowing a parameter named `image`.
- `preflight_remote_must_exist` now imports the fsspec backend for every remote
  protocol in use, so a missing `[s3]`/`[gcs]`/`[azure]` extra still falls back
  before any work starts.

## 2026-11-17 — `container-execution.md`: the load-bearing generated import (verified at `fbfc9c7`)

- Recorded why `generate_function` emits a `get_container_image` import that
  ruff then removes: it decides the wrapping of the `from hip_cargo import`
  line. #121 removed it as dead code, which broke the round-trip of six
  downstream CLIs (pfb-imaging x5, meerkat-beams `bds_to_xradio`); restored.

## 2026-11-17 — `container-execution.md`: maintainer-owned image tag (verified at `a470098`)

- `publish-container.yml` (and its `hip-cargo init` template) no longer builds
  on PR pushes: images come from pushes to main, `v*` tags, and manual
  `workflow_dispatch` runs on feature branches (`feat/x` → `:feat-x`).
- The tag lifecycle now states that agents never change the tag; feature-branch
  tags are an optional, maintainer-only step. Matches pfb-model-spec,
  pfb-imaging and meerkat-beams.
- Test list: `test_container_resolution.py` (a copy of `test_config.py`'s
  `TestGetContainerImage`) was deleted; point at `test_config.py`.
- `publish-container.yml` gained a per-ref `concurrency` group so the
  `update-cabs` bot push cancels the superseded merge build.
- Images are now multi-arch (native amd64 + arm64 builds, merged by digest),
  matching pfb-imaging; CI tests the oldest and newest Python plus one arm64
  job.

## 2026-09-23 — `cab-yaml-emission.md` records what the guard misses (verified at `960f3e1`)

- Added the failure table for the cases that survive the `yaml.safe_load`
  guard: a trailing colon, `" #"`, a leading `"- "` and non-ASCII. Two of them
  are silent, because the guard checks that the output parses rather than that
  it round-trips by value.
- Noted that `get_cst_value`'s fallback still emits source text as a value for
  anything it cannot evaluate; #109 fixed one instance, not the class.
- Tracked in #116.

## 2026-09-19 — `cli-dialect.md` added (verified at `4532253`)

- New page recording the closed set of typer constructs a CLI module may use,
  and why: the cab and the module are two renderings of one definition, so the
  writable language is whatever a cab can express.
- Prompted by #112 and #113 — `typer.Option` param_decls were mis-parsed into
  `default`, and `typer.Argument` failed either as a round-trip line diff or as
  an internal `RuntimeError`. Both are now rejected at parse time with a message
  naming the rule.
- `index.md` re-stamped; it was last touched by `5d56942` without one.

## 2026-09-18 — cab YAML emission documented (verified at `5d56942`)

- **Added** `cab-yaml-emission.md`: how CLI source becomes cab YAML, why
  `get_cst_value`'s source-text fallback is a silent-corruption risk (signed
  literals), the three invariants `format_info_fields` must preserve, and the
  new `yaml.safe_load` guard in `generate_cabs`. Written alongside the fixes
  for #109 and #110.

## 2026-09-18 — monitoring and transpile removed (verified at `7e1a122`)

- Deleted `progress-protocol.md`, `diagnostics.md`, `monitoring-api.md`,
  `optimising-pipelines.md`, and `transpile.md`: the monitoring stack
  (progress protocol, Ray aggregator, FastAPI server, per-task diagnostics)
  and `hip-cargo transpile` were removed from hip-cargo. Run state, logs and
  dashboards are left to Ray/Prefect; any web UI belongs downstream.
  Everything is preserved on the `wilful` branch.

## 2026-09-18 — writable inputs mounted rw (verified at `7dae314`)

- `container-execution.md`: mount resolution honours `writable: true` on
  inputs (#98), so a cab that updates an MS in place gets an rw bind mount.

## 2026-07-24 — post-ultra-review release-blocker fixes (verified at `50f3eea`)

- `transpile.md`: four new refusals in the grammar table (`unsafe-name`,
  `name-collision`, `reserved-name`, `unsupported-default`) from codegen
  injection hardening; new "Failure semantics" section (the `_check` probe,
  `STEP_FAILED`/`FAILED`, non-zero exit).
- `monitoring-api.md`: monitoring extra is now Python 3.11+; `/api/pipelines/submit`
  returns 501 (shell-injection placeholder removed); "Known limitations"
  section for the three monitoring majors deferred to the Ray-native thinning.
- `README.md`: monitoring extra is a Python 3.11+ feature; lightweight 3.10
  installs route heavy work through the containerised backend.
- Salvaged the adversarial wheel-review (`docs/review-artifacts/wheel-review.md`)
  — the Ray-native deletion map the thinning epic works from.

## 2026-07-13 — transpile v1 (verified at `ebbd1fb`)

- New page `transpile.md`: `hip-cargo transpile` v1 — restricted-grammar
  validation with named refusals, data-edge inference, static `_inmem`
  detection (LibCST, no imports), tasks/runner/cli codegen.
- Index updated. Deferred items (per-step resources, `image_uri`,
  loops/nesting, packaging) tracked on the page.
- Live proof landed on stokify branch `transpile` (commit `a761616`):
  committed `src/stokify/transpiled/`, `stokify transpiled run`,
  `demo.py --transpiled` (RESULT: PASS), structural + e2e tests.
- Ephemeral transpile spec/plan folded here and deleted (per CLAUDE.md rule).

## 2026-07-13 — bundle created (verified at `a1b714a`)

- Initial pages: `progress-protocol.md`, `diagnostics.md`,
  `monitoring-api.md`, `optimising-pipelines.md`, `container-execution.md`,
  `remote-uris.md`.
- Folded the durable content of, and retired, `docs/superpowers/specs/*`,
  `docs/superpowers/plans/*`, and `docs/rfc-revision-and-stokify-task.md`
  (point-in-time process artifacts; recoverable from git history — last
  present at commit `a1b714a`).
- Context: per-task diagnostics (DIAGNOSTIC event, report join,
  `/api/progress/{id}/diagnostics`) landed on `apis` between `1eeaa4f` and
  `a1b714a`; the pynvml GPU tier from the original design is deferred.
