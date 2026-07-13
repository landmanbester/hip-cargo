---
type: reference
title: Per-task diagnostics
description: Resource capture, the DIAGNOSTIC payload schema (stable agent contract), the report join, and the /diagnostics endpoint.
tags: [monitoring, diagnostics, optimisation, agent-contract]
timestamp: 2026-07-13
last_verified_commit: a1b714a
---

# Per-task diagnostics

What each task **actually consumed** versus what it **requested**. Stimela
profiles too coarsely for this; Ray's Dashboard cannot attribute in-process
consumption to hip-cargo's job/step vocabulary. Rationale:
`docs/design/transpile-rfc.md` §5.10.

Source: `src/hip_cargo/utils/diagnostics.py` (capture, stdlib-only),
`src/hip_cargo/monitoring/diagnostics_report.py` (join),
`monitoring/ray_backend.py::get_diagnostics`, `monitoring/server.py`.

## Capture

`track_progress(..., diagnostics=True)` (default on) takes a
`ResourceSnapshot` (`time.perf_counter()` + `resource.getrusage(RUSAGE_SELF)`)
at entry and exit and emits **one `DIAGNOSTIC` event** after the terminal
`COMPLETED`/`FAILED` event. Payload lives at `event.extra["diagnostics"]`.
Cost: two syscalls per task; dropped like any event under `NullBackend`.

## Payload schema — stable agent contract, do not rename

Stdlib tier (always present):

| Field | Type | Unit | Source |
|-------|------|------|--------|
| `wall_s` | float | s | `perf_counter` delta |
| `cpu_user_s` | float | s | `ru_utime` delta |
| `cpu_system_s` | float | s | `ru_stime` delta |
| `rss_entry_mb` | float | MiB | `ru_maxrss` at entry |
| `peak_rss_mb` | float | MiB | `ru_maxrss` at exit (see caveat 1) |
| `read_blocks` | int | blocks | `ru_inblock` delta |
| `write_blocks` | int | blocks | `ru_oublock` delta |
| `hostname` | str | — | `socket.gethostname()` |
| `pid` | int | — | `os.getpid()` |

psutil tier (merged over the above when `psutil` is importable — never a
dependency): `peak_rss_mb` becomes a true in-task sampled peak (0.5 s
interval), plus `read_mb`, `write_mb` (io_counters byte deltas, platform
permitting) and `sampled: true`.

Annotation tier (merged last, by convention from task wrappers):
`import_s` (float, lazy-import time), `requested` (dict:
`num_cpus`/`num_gpus`/`memory_mb`), `memory_mode` (str). A pynvml GPU tier is
**deferred** — not implemented.

## Annotations

`annotate_diagnostics(**fields)` (exported from the `hip_cargo` package root)
stashes fields in a per-process dict; the next DIAGNOSTIC emission merges and
clears them. Safe because Ray workers run one task at a time. Canonical use —
a task wrapper timing its lazy import (see `stokify/runtime/tasks.py`):

```python
_t0 = time.perf_counter()
from pkg.core.step import step_inmem          # heavy import, inside the worker
annotate_diagnostics(import_s=time.perf_counter() - _t0,
                     requested={"num_cpus": 2}, memory_mode=memory_mode)
```

## Report join

`build_diagnostics_report(job_id, events)` (pure function, no Ray) joins each
DIAGNOSTIC payload with:

- `step` — the event's `worker_name`.
- `queue_lag_s` — first `STARTED` (worker) minus first `STEP_STARTED` (same
  worker name); `null` when either is absent.
- `cpu_utilisation` — `(cpu_user_s + cpu_system_s) / (wall_s × requested.num_cpus)`;
  `null` when no request or zero wall.
- Pipeline rollup: `wall_s` = **last** `completed`/`failed` timestamp minus
  first `pipeline_started` (last, so a worker-level `completed` is not
  mistaken for the terminal event); `cpu_core_seconds` = Σ task CPU.

`ProgressAggregator.get_diagnostics(job_id)` delegates to it over the job's
event buffer.

## Endpoint

`GET /api/progress/{job_id}/diagnostics` → the report; 404 when `tasks` is
empty; 503 when the aggregator is unreachable.

```json
{
  "job_id": "demo", "pipeline_run_id": "…",
  "tasks": [{
    "step": "process", "hostname": "node-3", "pid": 12345,
    "requested": {"num_cpus": 4}, "memory_mode": "greedy",
    "queue_lag_s": 0.8, "import_s": 2.1, "wall_s": 41.3,
    "cpu_user_s": 150.2, "cpu_system_s": 3.1, "cpu_utilisation": 0.93,
    "rss_entry_mb": 310, "peak_rss_mb": 6120,
    "read_blocks": 0, "write_blocks": 18432, "sampled": true
  }],
  "pipeline": {"wall_s": 97.4, "cpu_core_seconds": 512.7}
}
```

## Caveats (honesty notes)

1. **Worker-process reuse.** `ru_maxrss` is a *process* high-water mark and
   Ray reuses workers, so the stdlib-tier `peak_rss_mb` can predate the task.
   Detect: `peak_rss_mb == rss_entry_mb` ⇒ the peak is stale. The psutil tier
   measures the true in-task peak.
2. **Child processes.** `RUSAGE_SELF` excludes subprocess consumption; steps
   that shell out under-attribute CPU.
3. **Not a profiler.** This names the step worth profiling, not the line —
   py-spy / memray are the escalation path.

Tests: `tests/test_diagnostics.py`, `tests/test_diagnostics_report.py`,
`tests/test_ray_backend.py::test_get_diagnostics_round_trip` (slow),
`tests/test_server.py` (endpoint). End-to-end: `stokify/demo.py` gates
`RESULT: PASS` on this field set.
