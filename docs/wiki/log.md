---
type: log
title: Wiki changelog
description: Chronological record of wiki updates.
timestamp: 2026-07-13
---

# Wiki changelog

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
