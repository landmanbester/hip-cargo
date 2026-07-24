---
type: reference
title: Progress protocol
description: Event vocabulary, backend protocol, and the track_progress context manager.
tags: [monitoring, progress, events]
timestamp: 2026-07-13
last_verified_commit: a1b714a
---

# Progress protocol

Source: `src/hip_cargo/utils/progress.py`, `src/hip_cargo/utils/progress_context.py`.
Stdlib-only by design — safe to import in a lightweight driver; Ray never leaks
into this layer.

## Event vocabulary

`EventType` (a `StrEnum`), 12 members in three groups:

| Group | Members | Emitted by |
|-------|---------|------------|
| Worker lifecycle | `STARTED`, `COMPLETED`, `FAILED` | `track_progress` entry/exit |
| In-body | `PROGRESS`, `LOG`, `ARTIFACT`, `METRIC`, `DIAGNOSTIC` | `ProgressTracker` methods; DIAGNOSTIC by `track_progress` exit |
| Pipeline-level | `PIPELINE_STARTED`, `STEP_STARTED`, `STEP_COMPLETED`, `STEP_FAILED` | the pipeline runner, around step submissions |

`ProgressEvent` is a dataclass: `job_id`, `worker_name`, `event_type`,
`timestamp` (unix, auto), `current_step`, `total_steps`, `message`,
`metric_name`, `metric_value`, `artifact_path`, `artifact_type`, and `extra`
(free-form dict — carries `pipeline_run_id`, the DAG on `PIPELINE_STARTED`,
and the DIAGNOSTIC payload). `to_dict()` serialises with `event_type` as its
string value.

## Backend protocol

`ProgressBackend` is a runtime-checkable `Protocol` with `emit(event)` and
`close()`. The module-level backend defaults to `NullBackend` (no-op, zero
overhead). API: `set_backend(backend)`, `get_backend()`, `emit(event)`.

The backend global is **per-process**. Every Ray worker process starts at
`NullBackend`, so a `@ray.remote` task that wants monitoring must call
`set_backend(RayProgressBackend(get_or_create_aggregator()))` *inside the task
body* — setting it on the driver does nothing for workers. (See
`stokify/runtime/tasks.py::_activate_backend` for the canonical pattern.)

## track_progress

```python
with track_progress(worker_name, total_steps=None, job_id=None,
                    pipeline_run_id=None, diagnostics=True) as tracker:
    tracker.step("message")            # PROGRESS, increments current_step
    tracker.metric("residual", 0.01)   # METRIC
    tracker.artifact(path, artifact_type="fits")  # ARTIFACT
    tracker.log("message")             # LOG
```

- Emits `STARTED` on entry; `COMPLETED` on clean exit; `FAILED` (message =
  exception string) on error, then re-raises.
- With `diagnostics=True` (the default), one `DIAGNOSTIC` event follows the
  terminal event on **both** paths — see [diagnostics.md](diagnostics.md).
- `job_id` auto-generates (8-hex) when omitted; `pipeline_run_id` rides in
  `extra` on every event for grouping.

## Ray aggregation

Source: `src/hip_cargo/monitoring/ray_backend.py` (needs `hip-cargo[monitoring]`).

- `ProgressAggregator` — named, `lifetime="detached"` Ray actor; ring buffer
  per job (`max_events`, default 1000; trims oldest half when full). Read
  surface: `get_latest`, `get_events(job_id, since_index)`, `get_all_jobs`,
  `get_metrics_history`, `get_pipeline_dag`, `get_diagnostics`.
- `RayProgressBackend` — pushes `event.to_dict()` fire-and-forget.
- `get_or_create_aggregator(name="progress_aggregator")` — idempotent handle.
  Ray scopes named actors by **namespace**: server and workers must share one
  (`ray.init(namespace=...)`) or they will silently talk to different actors.

Tests: `tests/test_progress.py`, `tests/test_ray_backend.py` (slow, real Ray).
