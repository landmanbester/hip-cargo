---
type: reference
title: Monitoring API
description: REST + WebSocket endpoint reference and MonitorSettings configuration.
tags: [monitoring, api, fastapi, config]
timestamp: 2026-07-13
last_verified_commit: a1b714a
---

# Monitoring API

Source: `src/hip_cargo/monitoring/server.py` (`create_app`), `config.py`
(`MonitorSettings`), `dispatcher.py` (`EventDispatcher`). Requires
`hip-cargo[monitoring]`. Launch: `hip-cargo monitor --port 8321`, or
`create_app(MonitorSettings(...))` programmatically. Swagger UI at `/docs`.

## Endpoints

| Method | Path | Returns / notes |
|--------|------|-----------------|
| GET | `/api/jobs` | All Ray jobs (Ray Jobs SDK) enriched with progress |
| GET | `/api/jobs/{id}` | Job details + latest progress; 404 unknown |
| GET | `/api/jobs/{id}/logs` | Job logs |
| POST | `/api/jobs/{id}/stop` | Stop a running job |
| GET | `/api/progress/{id}` | Latest event; 404 when none |
| GET | `/api/progress/{id}/events?since=0` | Incremental event fetch (cursor index) |
| GET | `/api/progress/{id}/metrics/{name}` | `[{step, value, timestamp}]` series |
| GET | `/api/progress/{id}/dag` | `extra` dict of `PIPELINE_STARTED`; 404 when none |
| GET | `/api/progress/{id}/diagnostics` | Per-task report ([diagnostics.md](diagnostics.md)); 404 when no tasks |
| GET | `/api/recipes` | Discovered recipe files |
| GET | `/api/recipes/{name}` | Parsed recipe DAG (`recipe_parser.py`) |
| GET | `/api/commands` | Project cab schemas (`cab_resolver.py`) |
| POST | `/api/pipelines/submit` | **501 — disabled.** Built a `stimela run` shell entrypoint from params (injection surface); removed. Submit via the transpiled package's own CLI (RFC §9.6) |
| WS | `/ws/progress/{id}` | Live event stream + heartbeats |

Error semantics: all `/api/progress/*` routes return **503** when the
aggregator actor is unreachable. When `HIPCARGO_AUTH_TOKEN` is set, `/api/*`
requires `Authorization: Bearer <token>` (WebSocket: `?token=` query param).

The WebSocket replays only from the subscriber's join-time cursor — late
joiners do not see history; use the REST `events` endpoint for that. A single
`EventDispatcher` poll loop fans one aggregator stream out to N clients.

## Configuration (`MonitorSettings`)

Env prefix `HIPCARGO_`, or a `.env` file; all optional:

| Field | Default | Meaning |
|-------|---------|---------|
| `auth_token` | `None` | Bearer token; unset = no auth |
| `host` / `port` | `0.0.0.0` / `8321` | Bind address |
| `ray_address` | `None` → `"auto"` | Cluster address for `ray.init` |
| `ray_dashboard_url` | `http://localhost:8265` | Ray Jobs SDK target |
| `aggregator_name` | `progress_aggregator` | Named detached actor |
| `max_events_per_job` | `1000` | Ring-buffer size |
| `websocket_poll_interval` | `0.5` | Dispatcher poll (s) |
| `recipes_dir` | `None` | Override recipe auto-discovery |
| `cli_module` | `None` | Dotted CLI module for cab discovery |

Tests: `tests/test_server.py` (FakeAggregator/FakeJobClient, no Ray),
`tests/test_integration.py` (slow, real local Ray cluster end-to-end).
