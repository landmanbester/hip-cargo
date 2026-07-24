---
type: reference
title: Path types and remote URIs
description: UPath-backed File/Directory/MS/URI types, remote object-store handling, credential forwarding, and fsspec extras.
tags: [paths, upath, s3, gcs, azure, fsspec]
timestamp: 2026-07-13
last_verified_commit: a1b714a
---

# Path types and remote URIs

Source: `src/hip_cargo/utils/types.py` (types + `parse_upath`),
`utils/runner.py` (mounts, preflight, credential forwarding).

## The path types

`File`, `Directory`, `MS`, `URI` are all `NewType(..., UPath)`
(universal_pathlib). User functions receive a `UPath` and call
`.open()` / `.read_bytes()` / `.exists()` directly — **hip-cargo does no IO**.
Local paths behave exactly like `pathlib.Path`; remote URIs (`s3://`, `gs://`,
`az://`, `http(s)://`) route to the matching fsspec backend on first access.

Codegen contract: for these four types the generator emits
`parser=parse_upath` (never `parser=Path`) in `typer.Option(...)` and adds
`parse_upath` to the generated `from hip_cargo import ...` block. List types
keep their comma-separated parsers.

## Remote URI behaviour (protocol not in `{"", "file", "local"}`)

- **Mounts**: `_resolve_mounts` skips remote UPaths — they contribute no
  container bind mounts.
- **Preflight**: `preflight_remote_must_exist` calls `upath.exists()` before
  dispatch when `must_exist=True`; missing → `typer.Exit(1)`. `mkdir` /
  `write_parent` / `access_parent` policies are skipped (meaningless on
  object stores).
- **Credential forwarding** into the fallback container, per scheme:

| Scheme | Env vars forwarded | Config dir mounted (ro) |
|---|---|---|
| `s3` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_PROFILE`, `AWS_REGION`, `AWS_DEFAULT_REGION`, `AWS_ENDPOINT_URL` | `~/.aws` (skipped if `AWS_SESSION_TOKEN` set) |
| `gs`/`gcs` | `GOOGLE_APPLICATION_CREDENTIALS` | `~/.config/gcloud` + the keyfile |
| `az`/`abfs`/`adl` | `AZURE_STORAGE_ACCOUNT`, `AZURE_STORAGE_KEY`, `AZURE_STORAGE_CONNECTION_STRING`, `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET` | `~/.azure` |

## Extras and the missing-backend path

fsspec backends stay **lazy** — never imported from CLI modules. Extras:
`hip-cargo[s3]` (s3fs), `[gcs]` (gcsfs), `[azure]` (adlfs), `[all]`. A remote
URI without the extra raises `ImportError`, which the generated wrapper's
existing `try/except ImportError → run_in_container` catches: users with a
container runtime fall through to containerised execution; users without get
an error suggesting the matching `pip install hip-cargo[...]`.

Testing convention: unit tests use fsspec's `memory://` protocol (no
credentials, fast). Live-cloud tests are opt-in behind `HIP_CARGO_LIVE_S3` /
`_GCS` / `_AZURE` env vars and excluded from required CI.

Tests: `tests/test_upath_parser.py`, `tests/test_remote_uri_runner.py`.
