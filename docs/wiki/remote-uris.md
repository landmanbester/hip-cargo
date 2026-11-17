---
type: reference
title: Path types and remote URIs
description: UPath-backed File/Directory/MS/URI types, remote object-store handling, credential forwarding, and fsspec extras.
tags: [paths, upath, s3, gcs, azure, fsspec]
timestamp: 2026-11-17
last_verified_commit: aeaaa4a
---

# Path types and remote URIs

Source: `src/hip_cargo/utils/types.py` (types + `parse_upath`),
`utils/runner.py` (mounts, preflight, credential forwarding).

## The path types

`File`, `Directory`, `MS`, `URI` are all `NewType(..., UPath)`
(universal_pathlib), defined once in `utils/types.py` and exported from
`hip_cargo`. User functions receive a `UPath` and call
`.open()` / `.read_bytes()` / `.exists()` directly — **hip-cargo does no IO**.
Local paths behave exactly like `pathlib.Path`; remote URIs (`s3://`, `gs://`,
`az://`, `http(s)://`) route to the matching fsspec backend on first access.

**Remote support stops at the wrapper (#96).** hip-cargo makes the *CLI*
accept a remote URI: `parse_upath`, the pre-flight, credential forwarding and
mount skipping. Whether the *command* works on one depends entirely on what the
package's `core/` does with the `UPath`. A `core/` built on `os.*`, `open()`,
`shutil` or a C library (casacore, CFITSIO, HDF5) is local-only, both natively
and in the container fallback, which runs the same code. Seen in
talonmyburgh/jackknify#7, where generated wrappers led to a README claiming URI
support that `core/` did not have. The scaffolded
`.claude/rules/architecture.md` now says to check `core/` before claiming it.

Codegen contract: for these four types the generator emits
`parser=parse_upath` (never `parser=Path`) in `typer.Option(...)` and adds
the path types it uses and `parse_upath` to the generated
`from hip_cargo import ...` block. Before #114 it declared the types locally
as `NewType(..., Path)`, an annotation that is false for remote URIs (a remote
`UPath` is not a `pathlib.Path`). The forward parser only reads the annotation
name, so those older modules still parse until they are regenerated. List types
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
URI without the extra raises `ImportError` from `preflight_remote_must_exist`,
which resolves `fsspec.get_filesystem_class` for every remote protocol in use
(constructing an `S3Path`/`GCSPath`/`AzurePath` does not import the backend,
so without this a remote output path would only fail mid-run). The pre-flight
sits inside the generated wrapper's `try/except ImportError`, which is
otherwise limited to the core import (#120): users with a container runtime
fall through to containerised execution before any work starts; users without
get an error suggesting the matching `pip install hip-cargo[...]`.

Testing convention: unit tests use fsspec's `memory://` protocol (no
credentials, fast). Live-cloud tests are opt-in behind `HIP_CARGO_LIVE_S3` /
`_GCS` / `_AZURE` env vars and excluded from required CI.

Tests: `tests/test_upath_parser.py`, `tests/test_remote_uri_runner.py`.
