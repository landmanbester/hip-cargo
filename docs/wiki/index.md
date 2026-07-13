---
type: index
title: hip-cargo LLM wiki
description: Progressive-disclosure listing of the in-repo knowledge bundle.
timestamp: 2026-07-13
last_verified_commit: a1b714a
---

# hip-cargo LLM wiki

In-repo knowledge bundle in the [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
style: plain markdown + YAML frontmatter, readable by humans without tools and
by agents without SDKs. The primary reader is an LLM agent; humans are a close
second.

**This is the canonical reference for what is implemented.** Design *rationale*
lives in `docs/design/transpile-rfc.md` (forward-looking, discussion-status).
Specs and plans are ephemeral process artifacts and are not retained in the
repo — do not cite them.

**Verification contract:** every page's frontmatter carries
`last_verified_commit` — the commit its claims were last checked against.
To assess staleness: `git diff <stamp>..HEAD -- <files the page covers>`.
Maintenance rule (also in `CLAUDE.md`): if your change invalidates or extends
a page, update the page and refresh its stamp **in the same session**.

## Pages

| Page | Covers | Read when |
|------|--------|-----------|
| [progress-protocol.md](progress-protocol.md) | Event vocabulary, `ProgressEvent`, backends, `track_progress`, Ray aggregation | Instrumenting code or consuming the event stream |
| [diagnostics.md](diagnostics.md) | Per-task resource capture, DIAGNOSTIC payload schema, report join, `/diagnostics` endpoint | Consuming or emitting per-task resource data |
| [monitoring-api.md](monitoring-api.md) | REST + WebSocket endpoint reference, `MonitorSettings` config | Calling the monitoring server |
| [optimising-pipelines.md](optimising-pipelines.md) | How an agent turns requested-vs-used numbers into optimisation actions | Asked to tune/optimise a pipeline |
| [container-execution.md](container-execution.md) | Image tag lifecycle, container fallback, GPU passthrough, per-backend run-args | Touching runner/execution or `_container_image.py` |
| [remote-uris.md](remote-uris.md) | UPath path types, remote URI handling, credential forwarding, fsspec extras | Touching path types or object-store support |
| [log.md](log.md) | Chronological wiki changelog | Checking what changed and when |

## Not covered here

- **How to edit this codebase** (linting, commit format, test isolation, Typer
  patterns): `.claude/rules/*.md` — harness instructions, kept separately.
- **Why the transpiler design looks the way it does**: `docs/design/transpile-rfc.md`.
- **Release mechanics** (tbump, git-cliff changelog, `update-cabs` workflow):
  summarised in [container-execution.md](container-execution.md) §Image tag lifecycle.
- **The runnable demonstrator**: `../../../stokify/DEMONSTRATOR.md` (sibling repo).
