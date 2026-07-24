---
type: log
title: Wiki changelog
description: Chronological record of wiki updates.
timestamp: 2026-07-13
---

# Wiki changelog

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
