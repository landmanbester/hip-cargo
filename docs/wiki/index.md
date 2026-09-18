---
type: index
title: hip-cargo LLM wiki
description: Progressive-disclosure listing of the in-repo knowledge bundle.
timestamp: 2026-09-18
last_verified_commit: 7e1a122
---

# hip-cargo LLM wiki

In-repo knowledge bundle in the [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
style: plain markdown + YAML frontmatter, readable by humans without tools and
by agents without SDKs. The primary reader is an LLM agent; humans are a close
second.

**This is the canonical reference for what is implemented.**
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
| [cab-yaml-emission.md](cab-yaml-emission.md) | Value extraction from CST, info-field formatting, the YAML-validity guard | Touching `get_cst_value`, `format_info_fields` or cab emission |
| [container-execution.md](container-execution.md) | Image tag lifecycle, container fallback, GPU passthrough, per-backend run-args | Touching runner/execution or `_container_image.py` |
| [remote-uris.md](remote-uris.md) | UPath path types, remote URI handling, credential forwarding, fsspec extras | Touching path types or object-store support |
| [log.md](log.md) | Chronological wiki changelog | Checking what changed and when |

## Not covered here

- **How to edit this codebase** (linting, commit format, test isolation, Typer
  patterns): `.claude/rules/*.md` — harness instructions, kept separately.
- **Release mechanics** (tbump, git-cliff changelog, `update-cabs` workflow):
  summarised in [container-execution.md](container-execution.md) §Image tag lifecycle.
