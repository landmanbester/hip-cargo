---
type: log
title: Wiki changelog
description: Chronological record of wiki updates.
timestamp: 2026-07-13
---

# Wiki changelog

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
