# Per-task diagnostics for agent-driven pipeline optimisation — Design

**Date:** 2026-07-12
**Status:** Draft — pending review (docs-first; implementation to follow as a separate plan)
**Branch context:** `apis` (monitoring substrate), demonstrated via `stokify`

## Problem

Agents (and humans) optimising a hip-cargo/Ray pipeline need per-task resource
attribution: what each step *actually consumed* relative to what it *requested*.
The existing sources each miss the mark:

- **Stimela** profiles at coarse granularity — per-run/per-step wall clock —
  with no per-task CPU, memory, or I/O attribution.
- **Ray core + Dashboard + state API** give task timelines, scheduling states,
  and node-level resource metrics, but do not attribute in-process resource
  consumption to individual hip-cargo steps, and the data lives in Ray's
  vocabulary (task IDs, actor IDs), not hip-cargo's (`job_id`, step name,
  `pipeline_run_id`).
- **The `apis` monitoring stack** streams rich *progress* (events, metrics,
  DAG) but nothing about resource consumption.

An optimising agent therefore has to scrape two systems and correlate them
itself, and still cannot answer the first question it needs: *which step is
over- or under-provisioned, and by how much?*

## Goals

1. Per-task resource deltas: wall time, user/system CPU time, peak RSS,
   block I/O, and (for transpiled tasks) lazy-import time.
2. Queue lag per step: time between the runner submitting a step and the
   worker body starting.
3. A requested-vs-used join: each record carries the step's declared resource
   request (`num_cpus` / `num_gpus` / `memory`) next to what was measured,
   plus derived utilisation ratios.
4. One machine-readable JSON endpoint serving all of the above per job —
   the agent contract.
5. Stdlib-only capture (matching the `utils/progress.py` ethos); zero
   overhead when monitoring is not attached (`NullBackend`).

## Non-goals

- **Line-level profiling.** py-spy / memray remain the escalation path once
  diagnostics have named the step worth profiling.
- **Prometheus / `ray.util.metrics` export.** That is the separate §3.3 item
  in the monitoring design doc; complementary, not replaced.
- **Optimisation advice.** The endpoint serves facts; agents derive
  conclusions. No "recommendations" field.
- **Mandatory GPU metrics.** GPU sampling is an optional enrichment tier
  (NVML), never a dependency.

## Design

### Capture: `hip_cargo/utils/diagnostics.py` (new, stdlib-only)

A `ResourceSnapshot` frozen dataclass captured at entry and exit of a tracked
block, from `time.perf_counter()` and `resource.getrusage(RUSAGE_SELF)`:

| field | source |
|---|---|
| `perf_s` | `perf_counter()` |
| `cpu_user_s`, `cpu_system_s` | `ru_utime`, `ru_stime` |
| `maxrss_mb` | `ru_maxrss` (KiB on Linux → MiB) |
| `inblocks`, `oublocks` | `ru_inblock`, `ru_oublock` |

`diagnostics_delta(entry, exit) -> dict[str, float | int | str]` computes the
per-task record with stable, unit-suffixed field names (`wall_s`,
`cpu_user_s`, `cpu_system_s`, `peak_rss_mb`, `rss_entry_mb`, `read_blocks`,
`write_blocks`, plus `hostname` and `pid`).

Integration point: `track_progress(...)` grows a `diagnostics: bool = True`
parameter. On exit (success *or* failure) it emits one `DIAGNOSTIC` event
whose payload rides in `extra["diagnostics"]`. Two `getrusage` calls per task
is negligible overhead; with `NullBackend` active the event is dropped like
every other event.

For transpiled packages, the `tasks.py` wrapper (the code the transpiler
emits, per RFC §5.2/§5.3) opens the diagnostics scope *around* the lazy
import, recording `import_s` separately — cold-start cost inside the
container is itself a tunable an agent needs to see.

### Optional enrichment tier (never required)

- If `psutil` imports: a sampling thread (0.5 s interval) records true
  in-task peak RSS and `io_counters()` byte totals, replacing the
  block-count proxies.
- If `pynvml` imports *and* the step requested GPUs: sampled GPU memory and
  utilisation.

Absence of either library degrades silently to the stdlib tier.

### Event vocabulary

One new member: `EventType.DIAGNOSTIC = "diagnostic"`. No change to the
`ProgressEvent` dataclass — the payload uses the documented `extra`
extensibility dict.

### Serving

- `ProgressAggregator.get_diagnostics(job_id)` filters `DIAGNOSTIC` events
  and joins them with the step timeline already in the buffer:
  `queue_lag_s = STARTED.timestamp − STEP_STARTED.timestamp` per step.
- New endpoint `GET /api/progress/{job_id}/diagnostics`:

```json
{
  "job_id": "demo",
  "pipeline_run_id": "…",
  "tasks": [
    {
      "step": "process",
      "hostname": "node-3", "pid": 12345,
      "requested": {"num_cpus": 4, "num_gpus": 0, "memory_mb": 8192},
      "queue_lag_s": 0.8,
      "import_s": 2.1,
      "wall_s": 41.3,
      "cpu_user_s": 150.2, "cpu_system_s": 3.1,
      "cpu_utilisation": 0.93,
      "peak_rss_mb": 6120, "rss_entry_mb": 310,
      "read_blocks": 0, "write_blocks": 18432,
      "memory_mode": "greedy"
    }
  ],
  "pipeline": {"wall_s": 97.4, "cpu_core_seconds": 512.7}
}
```

`cpu_utilisation = (cpu_user_s + cpu_system_s) / (wall_s × num_cpus)` when
the request is known; `null` otherwise. The `requested` block is sourced from
the step's declared resources (the `@ray.remote` decorator values carried in
`StepSpec` / the cab's resource hints, RFC §5.3/§9.3); when unavailable
(hand-instrumented, non-transpiled code) it is `null` and the ratios with it.

The endpoint is additive: existing endpoints and the WebSocket stream are
unchanged (a `DIAGNOSTIC` event flows through them like any other event, so
live dashboards may also consume it).

## Honesty caveats (carried into user-facing docs verbatim)

1. **Worker-process reuse.** `ru_maxrss` is a *process* high-water mark and
   Ray reuses worker processes, so a task's `peak_rss_mb` can reflect an
   earlier task in the same worker. Both `rss_entry_mb` and `peak_rss_mb`
   are reported so a consumer can detect a pre-existing high-water mark
   (`peak == entry` ⇒ the peak predates this task). The psutil tier measures
   the true in-task peak.
2. **Child processes.** `RUSAGE_SELF` excludes subprocess consumption; steps
   that shell out under-attribute CPU. (RUSAGE_CHILDREN only counts reaped
   children and is not used in v1.)
3. **Not a profiler.** Diagnostics name the step worth profiling; they do
   not name the line. py-spy / memray are the next step and out of scope.

## Testing

- **Unit** (`tests/test_diagnostics.py`): snapshot delta arithmetic;
  `DIAGNOSTIC` emitted on both clean exit and exception; `NullBackend`
  drops it; payload key set is exactly the documented schema (agents depend
  on stable names); psutil tier is skipped cleanly when not installed.
- **Integration**: extend the existing aggregator/server integration test
  (real local Ray cluster) to assert `GET .../diagnostics` returns a joined
  record with `queue_lag_s` computed for each step of the fake pipeline.
- **Demonstrator**: `stokify`'s `demo.py` gains a per-task diagnostics table
  in its printed summary, asserting the requested-vs-used fields are present
  (`RESULT: PASS` gate extended).

## Alternatives considered

- **Ray-only (no wrapper):** the state API + Dashboard cover timelines and
  node metrics but cannot attribute in-process RSS/CPU per hip-cargo step,
  and force agents to correlate two vocabularies. Rejected as insufficient,
  retained as a complement.
- **Per-task profilers (py-spy/memray) always-on:** heavy dependencies,
  material overhead, large artifacts to serve. Rejected for v1; documented
  as the escalation path.
- **Extend `tracker.metric()` conventions instead of a new event type:**
  would overload the metric time-series channel with one-shot structured
  records and complicate chart consumers. Rejected; `extra`-carried
  `DIAGNOSTIC` keeps both channels clean.
