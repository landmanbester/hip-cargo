# Wheel-reinvention review: hip-cargo monitoring/diagnostics/transpile vs Ray-native

Reviewed at `apis` (PR #84 head), companion stokify `transpile`. **Ray actually installed: 2.55.1**
(hip-cargo `.venv`), not 2.56.0 as briefed — nothing below depends on the delta.
All Ray claims verified by introspecting the installed package
(`.venv/lib/python3.11/site-packages/ray/...`) and a <5 s live `ray.init(num_cpus=1)` probe;
file paths cited inline. Stability markers stated per claim.

## Headline finding

The wiki's load-bearing sentence — *"Ray's Dashboard cannot attribute in-process consumption
to hip-cargo's job/step vocabulary"* (docs/wiki/diagnostics.md) — is **true for exactly four
fields and false for everything else the stack collects**. A live probe of a task submitted
with `.options(name="stokify::process")` returned, from `ray.util.state.list_tasks(detail=True)`:

```
name: stokify::process | state: FINISHED
required_resources: {'CPU': 1.0}
events: PENDING_ARGS_AVAIL → PENDING_NODE_ASSIGNMENT → SUBMITTED_TO_WORKER → RUNNING → FINISHED (ms timestamps each)
queue_lag_s: 0.002   wall_s: 0.432   worker_pid: 510541
task_log_info: {stdout_file, stderr_file, byte offsets}
```

So `wall_s`, `queue_lag_s`, `requested` (num_cpus/num_gpus/memory), step lifecycle
(STARTED/COMPLETED/FAILED with `error_type`/`error_message`), worker pid/node, and per-task
log location are all Ray-native **the moment the transpiler names its tasks** — which it
currently does not (`stokify/src/stokify/transpiled/tasks.py` uses bare `@ray.remote`).
What is genuinely not Ray-native: per-task **CPU-seconds** (`cpu_user_s`/`cpu_system_s`),
per-task **true peak RSS**, per-task **IO deltas**, and **`import_s`**. Ray's resource
telemetry is per-*worker*, sampled, and Prometheus-only
(`dashboard/modules/reporter/reporter_agent.py:331-357`: `component_cpu_percentage`,
`component_rss_mb`, `component_uss_mb` gauges; history requires an external Prometheus —
the dashboard only offers `/api/prometheus/sd`, `/api/grafana_health` integration hooks).

## 1. Verdict table

| Component | Verdict | Verified Ray-native equivalent | Delete | Lost |
|---|---|---|---|---|
| `utils/progress.py` — EventType vocabulary (12 members) | **THIN** to ~5 (METRIC, ARTIFACT, DIAGNOSTIC, PROGRESS?, LOG?) | Lifecycle six-pack (STARTED/COMPLETED/FAILED, STEP_STARTED/STEP_COMPLETED/STEP_FAILED) ≡ `TaskState.state` + per-state `events` timeline (`ray/util/state/common.py`, verified live). PIPELINE_STARTED/terminal ≡ Ray Job status + `metadata` dict (`JobSubmissionClient`, dashboard `/api/jobs/`) | ~40 of 108 LOC + every emission site | Sub-second event latency for lifecycle (state API is poll-only); events survive in GCS only (same volatility as the detached actor, so nothing lost there) |
| `utils/progress_context.py` — `track_progress` | **THIN** | STARTED/COMPLETED/FAILED emission duplicated by task states; `FAILED` message ≡ `TaskState.error_message` (introspected field) | ~30 of 124 LOC | Nothing — keep it as the METRIC/ARTIFACT/DIAGNOSTIC emitter |
| `monitoring/ray_backend.py` — ProgressAggregator `_jobs` registry, `_latest`, lifecycle read surface | **THIN** | `ray.util.state.list_tasks/get_task/list_jobs/summarize_tasks` (all present, `@DeveloperAPI` — public but semi-stable) + dashboard `/api/v0/tasks`, `/api/v0/tasks/timeline`. GCS task-event store default ≫ the actor's 1000-event ring (state API serves up to `RAY_MAX_LIMIT_FROM_API_SERVER`=10 000/query, `util/state/common.py:53`) | ~60 of 171 LOC (`_jobs`/`_latest` bookkeeping, `get_all_jobs`, `get_latest`) | Best-effort caveat: Ray task events can be dropped at extreme task volume; irrelevant at pipeline-step granularity (≤ dozens of tasks) |
| `monitoring/server.py` — `/api/jobs`, `/api/jobs/{id}`, `/api/jobs/{id}/logs`, `POST /api/jobs/{id}/stop` | **REPLACE** | Verbatim duplicates of the Ray dashboard's own REST routes `/api/jobs/`, `/api/jobs/{id}`, `/api/jobs/{id}/logs`, `/api/jobs/{id}/stop` (route table grepped from `dashboard/modules/job/`; also `/logs/tail` streaming, which hip-cargo doesn't even expose — `JobSubmissionClient.tail_job_logs`, sdk.py:477) | ~120 LOC + `_job_details_to_dict` + `FakeJobClient` test mocks | Bearer-token auth in front of the jobs API (Ray dashboard is **unauthenticated by design**) and the progress-enrichment merge (client can join two responses) |
| `monitoring/server.py` — `POST /api/pipelines/submit` | **REPLACE** (already flagged "known-fragile placeholder" in monitoring-api.md; RFC §9.6 agrees) | `JobSubmissionClient.submit_job(entrypoint=..., runtime_env=..., metadata=...)` called directly by the client; the shell-string building (`f"'{v}'"` quoting) is a quoting bug farm | ~50 LOC | Nothing worth keeping |
| `monitoring/dispatcher.py` + `WS /ws/progress/{id}` | **THIN or DELETE** | No Ray equivalent for WS push (Serve is model-serving, not fan-out) — but the REST cursor endpoint `/api/progress/{id}/events?since=` **already implements the same 0.5 s-latency polling contract** the dispatcher itself uses internally. WS adds zero latency benefit over client-side polling at the same interval | 140 LOC dispatcher + ~40 LOC WS route + heartbeat/close protocol | A push socket for browsers; trivially re-addable later if a real frontend demands it |
| `utils/diagnostics.py` — getrusage capture, psutil sampler, `annotate_diagnostics` | **KEEP** (core is the novel part) | None. Verified: `TaskState` has no CPU/RSS fields; reporter agent collects per-*worker* `cpu_percent`/`memory_info` (reporter_agent.py:406-411) exported only as Prometheus gauges | — | — |
| `diagnostics.py` `requested=` annotation + transpiler's hardcoded `requested={"num_cpus": 1}` | **REPLACE** | `TaskState.required_resources` (verified live: `{'CPU': 1.0}`) — authoritative, free, and correct when `.options(num_cpus=...)` changes | annotation plumbing in every generated task (~4 LOC × N steps) | Nothing — Ray's number is the truth; the hardcode can silently diverge from actual `@ray.remote` options |
| `monitoring/diagnostics_report.py` — `queue_lag_s` join, pipeline `wall_s` | **THIN** | `queue_lag_s` ≡ `PENDING_NODE_ASSIGNMENT→RUNNING` delta from `TaskState.events` (verified live, ms precision; ours is a fragile first-STARTED-minus-first-STEP_STARTED heuristic that breaks on name collisions/retries). Pipeline wall ≡ Job `start_time`/`end_time` (introspected `JobDetails` fields, used in server.py:43-44) | ~25 of 80 LOC | Nothing; precision improves |
| Transpiled `runner.py` — STEP_* emission + `ray.wait` after **every** submit | **THIN** | Task states (above). Bonus defect: per-step `ray.wait([ref])` exists only to bracket STEP events and forces the driver to serialise the DAG — it forecloses the parallelism a DAG transpiler exists to exploit | ~20 LOC per generated runner + codegen | Nothing |
| Transpiled `tasks.py` — `import_s` timing, `_activate_backend` | **KEEP** | None: lazy-import time inside the task body is invisible to Ray (`WorkerState.worker_launch_time_ms` covers process spawn only, not module import) | — | — |
| METRIC events + `/api/progress/{id}/metrics/{name}` | **KEEP** (with a documented alternative) | `ray.util.metrics.Gauge/Counter/Histogram` exists (introspected) but is Prometheus-export-only — no query path without deploying Prometheus+Grafana. For a zero-infra in-band metric series, custom is honest | — | Prometheus-grade history/alerting (available later by *also* emitting `ray.util.metrics`) |
| ARTIFACT events, `/api/recipes*`, `/api/commands`, `/api/progress/{id}/dag` | **KEEP** | None — domain vocabulary (stimela recipes, cabs, science artifacts). Ray has no concept of any of it | — | — |
| LOG events / `tracker.log()` | **THIN/DELETE** | Per-task stdout/stderr captured automatically with byte offsets (`task_log_info`, verified live) + `get_job_logs`/`tail_job_logs`; `ray.util.state.get_log/list_logs` for programmatic access. `print()` already does this | ~10 LOC + vocab member | Structured log records in the same event stream (keep only if the frontend needs them inline) |
| PROGRESS events / `tracker.step()` | **KEEP-small** | `ray.experimental.tqdm_ray` exists (introspected) but is terminal-oriented and `experimental` — not a REST-consumable per-job series | — | — |
| py-spy/memray escalation (optimising-pipelines.md names them as manual next steps) | **DOC-FIX** | Dashboard already serves `/task/cpu_profile`, `/worker/cpu_profile`, `/memory_profile`, `/worker/traceback`, `/worker/gpu_profile` (route table, `dashboard/modules/reporter/`) — one-click py-spy/memray on a live task | — | wiki should point at these instead of implying manual tooling |

Approximate total deletable: **~450–500 LOC** of the ~1 130 LOC core stack, plus
`FakeJobClient` mock code and every generated runner's STEP/wait boilerplate; and the
codegen + tests that produce them. Dependencies dropped: none (fastapi/uvicorn stay for the
domain endpoints), but the **detached-actor namespace footgun** (documented in
progress-protocol.md as a silent-failure mode) stops guarding lifecycle data — only
domain events still transit the actor.

## 2. Migration shapes (REPLACE/THIN verdicts)

**Name the tasks; stop narrating the scheduler.** The transpiler emits
`tasks.init_task.options(name=f"{job_id}::init").remote(...)` and drops the
`STEP_STARTED`/`STEP_COMPLETED` emissions and every intermediate `ray.wait`. The runner
becomes a pure ObjectRef chain ending in one `ray.get`. Step lifecycle, queue lag, wall
time, requested resources, errors, and log locations are then served by
`list_tasks(filters=[("name", "=", f"{job_id}::{step}")], detail=True)` — the monitoring
server's step-status read path calls that instead of the aggregator.

**Delete the jobs proxy.** Remove the four `/api/jobs*` routes and `JobSubmissionClient`
from the server; clients hit `:8265/api/jobs/` directly (documented, stable REST). If the
deployment needs auth in front of Ray's unauthenticated dashboard, keep the bearer
middleware as a ~30-line *generic* reverse-proxy route rather than re-modelling
`JobDetails` field-by-field. `POST /api/pipelines/submit` dies with it — the transpiled
package's own `cli.py run --monitor` plus `submit_job` from the client side is the
sanctioned path (RFC §9.6 already concedes this).

**Shrink the aggregator to a domain-event store.** `ProgressAggregator` keeps
`push_event`/`get_events`/`get_metrics_history`/`get_pipeline_dag`/`get_diagnostics` but
drops `_jobs`/`_latest` lifecycle bookkeeping; `get_all_jobs` is answered by
`ray.util.state.list_jobs` + task summaries. `track_progress` keeps emitting only
METRIC/ARTIFACT/DIAGNOSTIC (+PROGRESS).

**Let Ray fill half the diagnostics report.** `build_diagnostics_report` takes the
DIAGNOSTIC payloads (CPU-seconds, RSS, IO, import_s — the novel part) and joins them with
`TaskState` rows keyed on task name: `wall_s` = RUNNING→FINISHED, `queue_lag_s` =
PENDING_NODE_ASSIGNMENT→RUNNING, `requested` = `required_resources`. `cpu_utilisation`
stays as the one derived field. The stale-`ru_maxrss` caveat also shrinks: worker
attribution can be cross-checked against `worker_pid`.

**Drop the WebSocket layer (or defer it).** Clients poll
`/api/progress/{id}/events?since=N` at 0.5 s — the identical latency the dispatcher's own
poll loop already imposes. Dispatcher, heartbeats, close-protocol, and the WS auth query
param all go.

## 3. Genuinely novel (no Ray equivalent — verified)

1. **Per-task CPU-seconds, IO-block deltas, and true in-task peak RSS**
   (`utils/diagnostics.py`). Ray records none of these per task; per-worker sampled
   gauges exist only via Prometheus export.
2. **`import_s`** — lazy-import cost inside the task body; invisible to every Ray timer.
3. **The requested-vs-used join as one agent-consumable JSON** (`/diagnostics`) — Ray can
   supply half the columns but has no endpoint that correlates request against
   consumption per named step.
4. **ARTIFACT events** and the recipe/cab domain surface (`/api/recipes*`,
   `/api/commands`, recipe-DAG-as-declared vs Ray's task-graph-as-executed).
5. **In-band METRIC history without Prometheus** — deliberate zero-infra trade; Ray's
   answer requires an external TSDB.
6. **Auth in front of the API** — the Ray dashboard has no authentication story at all.

Everything else in the stack has a Ray-native twin.

## 4. Top 3 recommendations (burden saved ÷ migration effort)

1. **Delete the `/api/jobs*` proxy and `/api/pipelines/submit`** (~170 LOC + mocks +
   tests). Pure duplication of a documented, stable REST API; the submit endpoint is
   admitted-fragile shell-string assembly. Effort: hours; nothing to build, only a doc
   pointer to `:8265` (and optionally a 30-line generic authed proxy).
2. **Name transpiled tasks and delete lifecycle narration** (STEP_* events, per-step
   `ray.wait`, `_jobs` registry, `queue_lag_s` heuristic, `requested=` hardcode). This
   halves the event vocabulary, removes the aggregator's most stateful code, replaces
   heuristic joins with authoritative ms-precision GCS data, and un-serialises the driver
   — a correctness *and* deletion win. Effort: a day in codegen + report join, mostly
   test updates. Caveat to record in the wiki: `ray.util.state` is `@DeveloperAPI`
   (public, semi-stable) and task events are best-effort at extreme volume — both
   acceptable at pipeline-step granularity.
3. **Drop dispatcher + WebSocket until a real frontend exists** (~180 LOC + the
   subscription/heartbeat protocol surface). The REST cursor endpoint already delivers
   the same latency; this is speculative generality today ("Frontend not yet built" —
   server.py's own root page).

Also worth a line each: point optimising-pipelines.md at the dashboard's built-in
`/task/cpu_profile` and `/memory_profile` endpoints instead of framing py-spy/memray as
manual escalation; and consider dual-emitting metrics through `ray.util.metrics` so
Prometheus users get them for free without touching the custom store.
