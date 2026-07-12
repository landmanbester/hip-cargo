# Per-Task Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-task resource diagnostics (getrusage deltas + queue lag + requested-vs-used join) emitted through the existing progress protocol and served at `GET /api/progress/{job_id}/diagnostics`, per `docs/superpowers/specs/2026-07-12-per-task-diagnostics-design.md`.

**Architecture:** A stdlib-only `utils/diagnostics.py` captures `ResourceSnapshot`s at entry/exit of `track_progress(...)` and emits one new `DIAGNOSTIC` event per tracked block, payload in `extra["diagnostics"]`. A module-level annotation stash lets task wrappers (stokify `tasks.py`) merge `import_s` / `requested` / `memory_mode` into the next DIAGNOSTIC event. A pure function `build_diagnostics_report(events)` joins DIAGNOSTIC payloads with the step timeline and derives utilisation; the `ProgressAggregator` actor and a new FastAPI endpoint expose it.

**Tech Stack:** Python 3.10+ stdlib (`resource`, `time`, `socket`, `os`, `threading`), optional `psutil` tier, FastAPI, Ray (existing monitoring extra).

## Global Constraints

- Work happens on the `apis` branch of `/home/bester/software/hip-cargo`; stokify changes in `/home/bester/software/stokify` are **left uncommitted** (that repo has in-flight user work; do not commit or stage anything there).
- `hip_cargo/utils/*` must stay stdlib-only (no psutil import at module level; guarded lazy import only).
- Lint after every task: `uv run ruff format . && uv run ruff check . --fix` (mandatory, per CLAUDE.md).
- Test command shape: `uv run --extra monitoring python -m pytest tests/<file> -v` (fast tests); Ray-backed tests carry `@pytest.mark.slow`.
- Commits use Conventional Commits, first line < 72 chars, trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- The `generate-cabs` pre-commit hook may rewrite `src/hip_cargo/cabs/*.yml`; on this branch the image tag must stay `:apis`. If the hook flips tags to `:latest`, restore with `git checkout -- src/hip_cargo/cabs/` and commit with `SKIP=generate-cabs`.
- DIAGNOSTIC payload key names are a public contract; the exact stdlib-tier key set is: `wall_s`, `cpu_user_s`, `cpu_system_s`, `rss_entry_mb`, `peak_rss_mb`, `read_blocks`, `write_blocks`, `hostname`, `pid` (annotations may add `import_s`, `requested`, `memory_mode`; the psutil tier adds `read_mb`, `write_mb`, `sampled`).
- **Conscious cut vs spec:** the `pynvml` GPU tier is deferred (no GPU-requesting step exists to exercise it); everything else in the spec is in scope.

---

### Task 1: `utils/diagnostics.py` — snapshots, deltas, annotations

**Files:**
- Create: `src/hip_cargo/utils/diagnostics.py`
- Test: `tests/test_diagnostics.py`

**Interfaces:**
- Produces: `ResourceSnapshot` (frozen dataclass), `capture_snapshot() -> ResourceSnapshot`, `diagnostics_delta(entry: ResourceSnapshot, exit_: ResourceSnapshot) -> dict[str, Any]`, `annotate_diagnostics(**fields: Any) -> None`, `consume_diagnostic_annotations() -> dict[str, Any]`, `clear_diagnostic_annotations() -> None`.

- [x] **Step 1: Write the failing tests**

```python
# tests/test_diagnostics.py
"""Tests for the per-task diagnostics capture layer."""

import time

import pytest

from hip_cargo.utils.diagnostics import (
    ResourceSnapshot,
    annotate_diagnostics,
    capture_snapshot,
    clear_diagnostic_annotations,
    consume_diagnostic_annotations,
    diagnostics_delta,
)

STDLIB_KEYS = {
    "wall_s",
    "cpu_user_s",
    "cpu_system_s",
    "rss_entry_mb",
    "peak_rss_mb",
    "read_blocks",
    "write_blocks",
    "hostname",
    "pid",
}


@pytest.fixture(autouse=True)
def _clean_annotations():
    clear_diagnostic_annotations()
    yield
    clear_diagnostic_annotations()


def test_capture_snapshot_fields():
    snap = capture_snapshot()
    assert isinstance(snap, ResourceSnapshot)
    assert snap.perf_s > 0
    assert snap.cpu_user_s >= 0
    assert snap.cpu_system_s >= 0
    assert snap.maxrss_mb > 0


def test_delta_key_set_is_stable_contract():
    entry = capture_snapshot()
    delta = diagnostics_delta(entry, capture_snapshot())
    assert set(delta) == STDLIB_KEYS


def test_delta_arithmetic():
    entry = capture_snapshot()
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 0.05:
        sum(range(1000))  # burn a little CPU and wall time
    delta = diagnostics_delta(entry, capture_snapshot())
    assert delta["wall_s"] >= 0.05
    assert delta["cpu_user_s"] >= 0
    # maxrss is monotone: peak can never be below the entry RSS
    assert delta["peak_rss_mb"] >= delta["rss_entry_mb"]
    assert delta["pid"] > 0
    assert isinstance(delta["hostname"], str) and delta["hostname"]


def test_annotations_merge_and_clear_on_consume():
    annotate_diagnostics(import_s=1.5, memory_mode="greedy")
    annotate_diagnostics(requested={"num_cpus": 2})
    got = consume_diagnostic_annotations()
    assert got == {"import_s": 1.5, "memory_mode": "greedy", "requested": {"num_cpus": 2}}
    assert consume_diagnostic_annotations() == {}
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run --extra monitoring python -m pytest tests/test_diagnostics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hip_cargo.utils.diagnostics'`

- [x] **Step 3: Write the implementation**

```python
# src/hip_cargo/utils/diagnostics.py
"""Per-task resource diagnostics capture.

Stdlib-only, matching the ethos of ``utils/progress.py``: two ``getrusage``
syscalls per tracked block, zero overhead when no monitoring backend is
attached. The delta produced here rides in a ``DIAGNOSTIC`` event's
``extra["diagnostics"]`` payload; its key names are a public contract that
optimising agents depend on — do not rename them.

Honesty caveats (also documented in the design spec):
- ``ru_maxrss`` is a *process* high-water mark and Ray reuses worker
  processes, so ``peak_rss_mb`` can predate the task. Both ``rss_entry_mb``
  and ``peak_rss_mb`` are reported so consumers can detect a stale peak.
- ``RUSAGE_SELF`` excludes unreaped child processes.
"""

import os
import resource
import socket
import sys
import time
from dataclasses import dataclass
from typing import Any

# ru_maxrss is KiB on Linux, bytes on macOS.
_MAXRSS_TO_MB = 1.0 / (1024.0 * 1024.0) if sys.platform == "darwin" else 1.0 / 1024.0


@dataclass(frozen=True)
class ResourceSnapshot:
    """Point-in-time resource usage of the current process."""

    perf_s: float
    cpu_user_s: float
    cpu_system_s: float
    maxrss_mb: float
    inblocks: int
    oublocks: int


def capture_snapshot() -> ResourceSnapshot:
    """Capture a resource snapshot for the current process (RUSAGE_SELF)."""
    ru = resource.getrusage(resource.RUSAGE_SELF)
    return ResourceSnapshot(
        perf_s=time.perf_counter(),
        cpu_user_s=ru.ru_utime,
        cpu_system_s=ru.ru_stime,
        maxrss_mb=ru.ru_maxrss * _MAXRSS_TO_MB,
        inblocks=ru.ru_inblock,
        oublocks=ru.ru_oublock,
    )


def diagnostics_delta(entry: ResourceSnapshot, exit_: ResourceSnapshot) -> dict[str, Any]:
    """Compute the per-task diagnostics record between two snapshots.

    Args:
        entry: Snapshot taken at block entry.
        exit_: Snapshot taken at block exit.

    Returns:
        Dict with the stable, unit-suffixed field names agents consume.
    """
    return {
        "wall_s": exit_.perf_s - entry.perf_s,
        "cpu_user_s": exit_.cpu_user_s - entry.cpu_user_s,
        "cpu_system_s": exit_.cpu_system_s - entry.cpu_system_s,
        "rss_entry_mb": entry.maxrss_mb,
        "peak_rss_mb": exit_.maxrss_mb,
        "read_blocks": exit_.inblocks - entry.inblocks,
        "write_blocks": exit_.oublocks - entry.oublocks,
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
    }


# Per-process annotation stash. A task wrapper (e.g. a transpiled tasks.py)
# records fields the core function cannot know — import_s, the declared
# resource request, the memory mode — and the next DIAGNOSTIC emission merges
# and clears them. Safe per-process: Ray workers execute one task at a time.
_annotations: dict[str, Any] = {}


def annotate_diagnostics(**fields: Any) -> None:
    """Stash fields to merge into the next DIAGNOSTIC event's payload."""
    _annotations.update(fields)


def consume_diagnostic_annotations() -> dict[str, Any]:
    """Return and clear the stashed annotations."""
    global _annotations
    got = _annotations
    _annotations = {}
    return got


def clear_diagnostic_annotations() -> None:
    """Drop any stashed annotations (e.g. between tests or tasks)."""
    _annotations.clear()
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run --extra monitoring python -m pytest tests/test_diagnostics.py -v`
Expected: 4 passed

- [x] **Step 5: Lint and commit**

```bash
uv run ruff format . && uv run ruff check . --fix
git add src/hip_cargo/utils/diagnostics.py tests/test_diagnostics.py
git commit -m "feat: add stdlib per-task diagnostics capture layer"
```

(If the `generate-cabs` hook modifies `src/hip_cargo/cabs/*.yml`, restore them per Global Constraints and retry with `SKIP=generate-cabs`.)

---

### Task 2: `DIAGNOSTIC` event + `track_progress(diagnostics=True)`

**Files:**
- Modify: `src/hip_cargo/utils/progress.py` (EventType)
- Modify: `src/hip_cargo/utils/progress_context.py` (track_progress)
- Modify: `src/hip_cargo/__init__.py` (export `annotate_diagnostics` if progress API is exported there — check first; only add if `track_progress` is already exported)
- Test: `tests/test_diagnostics.py` (extend)

**Interfaces:**
- Consumes: Task 1's `capture_snapshot`, `diagnostics_delta`, `consume_diagnostic_annotations`.
- Produces: `EventType.DIAGNOSTIC = "diagnostic"`; `track_progress(worker_name, total_steps=None, job_id=None, pipeline_run_id=None, diagnostics=True)` emits one DIAGNOSTIC event after COMPLETED/FAILED with payload at `event.extra["diagnostics"]`.

- [x] **Step 1: Write the failing tests** (append to `tests/test_diagnostics.py`)

```python
from hip_cargo.utils.progress import EventType, NullBackend, ProgressEvent, set_backend
from hip_cargo.utils.progress_context import track_progress


class ListBackend:
    def __init__(self) -> None:
        self.events: list[ProgressEvent] = []

    def emit(self, event: ProgressEvent) -> None:
        self.events.append(event)

    def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _reset_backend():
    set_backend(NullBackend())
    yield
    set_backend(NullBackend())


def test_diagnostic_event_type_exists():
    assert EventType.DIAGNOSTIC == "diagnostic"


def test_track_progress_emits_diagnostic_on_success():
    backend = ListBackend()
    set_backend(backend)
    with track_progress("w", job_id="j") as tracker:
        tracker.step()
    types = [e.event_type for e in backend.events]
    assert types == [EventType.STARTED, EventType.PROGRESS, EventType.COMPLETED, EventType.DIAGNOSTIC]
    payload = backend.events[-1].extra["diagnostics"]
    assert STDLIB_KEYS <= set(payload)


def test_track_progress_emits_diagnostic_on_failure():
    backend = ListBackend()
    set_backend(backend)
    with pytest.raises(ValueError):
        with track_progress("w", job_id="j"):
            raise ValueError("boom")
    types = [e.event_type for e in backend.events]
    assert types == [EventType.STARTED, EventType.FAILED, EventType.DIAGNOSTIC]


def test_track_progress_diagnostics_opt_out():
    backend = ListBackend()
    set_backend(backend)
    with track_progress("w", job_id="j", diagnostics=False):
        pass
    assert [e.event_type for e in backend.events] == [EventType.STARTED, EventType.COMPLETED]


def test_annotations_merge_into_diagnostic_payload():
    backend = ListBackend()
    set_backend(backend)
    annotate_diagnostics(import_s=2.0, requested={"num_cpus": 4}, memory_mode="greedy")
    with track_progress("w", job_id="j"):
        pass
    payload = backend.events[-1].extra["diagnostics"]
    assert payload["import_s"] == 2.0
    assert payload["requested"] == {"num_cpus": 4}
    assert payload["memory_mode"] == "greedy"
    # consumed: a second block has no annotations
    with track_progress("w2", job_id="j"):
        pass
    assert "import_s" not in backend.events[-1].extra["diagnostics"]
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run --extra monitoring python -m pytest tests/test_diagnostics.py -v`
Expected: new tests FAIL (`AttributeError: DIAGNOSTIC` / unexpected event lists); Task 1 tests still PASS.

- [x] **Step 3: Implement**

In `src/hip_cargo/utils/progress.py`, add to `EventType`:

```python
    DIAGNOSTIC = "diagnostic"
```

In `src/hip_cargo/utils/progress_context.py`, replace `track_progress` with:

```python
@contextmanager
def track_progress(
    worker_name: str,
    total_steps: int | None = None,
    job_id: str | None = None,
    pipeline_run_id: str | None = None,
    diagnostics: bool = True,
) -> Iterator[ProgressTracker]:
    """Context manager that emits STARTED/COMPLETED/FAILED events around a block.

    Args:
        worker_name: Name of the worker or step.
        total_steps: Total iterations expected, if known.
        job_id: Unique job identifier. Auto-generated if not provided.
        pipeline_run_id: Pipeline run ID for grouping steps in a pipeline run.
        diagnostics: Emit one DIAGNOSTIC event (resource deltas) on exit.

    Yields:
        A ProgressTracker for emitting progress, metric, artifact, and log events.
    """
    if job_id is None:
        job_id = uuid.uuid4().hex[:8]

    tracker = ProgressTracker(job_id, worker_name, total_steps, pipeline_run_id)

    entry = capture_snapshot() if diagnostics else None
    emit(tracker._make_event(EventType.STARTED))
    try:
        yield tracker
    except Exception as exc:
        emit(tracker._make_event(EventType.FAILED, message=str(exc)))
        if entry is not None:
            _emit_diagnostics(tracker, entry)
        raise
    else:
        emit(tracker._make_event(EventType.COMPLETED))
        if entry is not None:
            _emit_diagnostics(tracker, entry)


def _emit_diagnostics(tracker: ProgressTracker, entry: ResourceSnapshot) -> None:
    """Emit a DIAGNOSTIC event with the delta since entry plus any annotations."""
    payload = diagnostics_delta(entry, capture_snapshot())
    payload.update(consume_diagnostic_annotations())
    event = tracker._make_event(EventType.DIAGNOSTIC)
    event.extra["diagnostics"] = payload
    emit(event)
```

with imports at the top of the file:

```python
from hip_cargo.utils.diagnostics import (
    ResourceSnapshot,
    capture_snapshot,
    consume_diagnostic_annotations,
    diagnostics_delta,
)
```

Check `src/hip_cargo/__init__.py`: if `track_progress` is re-exported there, add `annotate_diagnostics` to the same export block (lazy or direct, matching the existing pattern); otherwise skip.

- [x] **Step 4: Run the full fast test suite**

Run: `uv run --extra monitoring python -m pytest tests/test_diagnostics.py tests/test_progress.py -v`
Expected: all pass (existing `test_progress.py` event-sequence assertions may need the trailing DIAGNOSTIC added — if any fail on the new event, update those assertions; the Autonomy Rule in `.claude/rules/testing-and-ci.md` covers this).

- [x] **Step 5: Lint and commit**

```bash
uv run ruff format . && uv run ruff check . --fix
git add -u src tests
git commit -m "feat: emit DIAGNOSTIC event from track_progress"
```

---

### Task 3: Optional psutil enrichment tier

**Files:**
- Modify: `src/hip_cargo/utils/diagnostics.py`
- Modify: `src/hip_cargo/utils/progress_context.py`
- Test: `tests/test_diagnostics.py` (extend)

**Interfaces:**
- Produces: `start_sampler(interval: float = 0.5) -> _Sampler | None` (None when psutil is missing) and `_Sampler.stop() -> dict[str, Any]` returning `{"peak_rss_mb": float, "read_mb": float, "write_mb": float, "sampled": True}` (io fields omitted when the platform lacks `io_counters`). `track_progress` merges the sampler dict over the stdlib delta (sampled peak wins).

- [x] **Step 1: Write the failing tests** (append to `tests/test_diagnostics.py`)

```python
from hip_cargo.utils.diagnostics import start_sampler

psutil = pytest.importorskip("psutil")


def test_sampler_reports_sampled_peak():
    sampler = start_sampler(interval=0.01)
    assert sampler is not None
    time.sleep(0.05)
    result = sampler.stop()
    assert result["sampled"] is True
    assert result["peak_rss_mb"] > 0


def test_track_progress_payload_marks_sampled_tier():
    backend = ListBackend()
    set_backend(backend)
    with track_progress("w", job_id="j"):
        time.sleep(0.02)
    payload = backend.events[-1].extra["diagnostics"]
    assert payload.get("sampled") is True
```

(`importorskip` keeps the suite green when psutil is absent — the stdlib tier is the fallback under test elsewhere.)

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run --extra monitoring python -m pytest tests/test_diagnostics.py -v -k sampler`
Expected: FAIL — `ImportError: cannot import name 'start_sampler'`

- [x] **Step 3: Implement** (append to `src/hip_cargo/utils/diagnostics.py`)

```python
import threading


class _Sampler:
    """Background RSS sampler backed by psutil (optional enrichment tier)."""

    def __init__(self, interval: float) -> None:
        import psutil

        self._proc = psutil.Process()
        self._interval = interval
        self._stop_event = threading.Event()
        self._peak_rss = self._proc.memory_info().rss
        try:
            self._io_entry = self._proc.io_counters()
        except (AttributeError, NotImplementedError, psutil.AccessDenied):
            self._io_entry = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval):
            try:
                self._peak_rss = max(self._peak_rss, self._proc.memory_info().rss)
            except Exception:
                return

    def stop(self) -> dict[str, Any]:
        """Stop sampling and return the enrichment fields."""
        self._stop_event.set()
        self._thread.join(timeout=self._interval * 4)
        result: dict[str, Any] = {
            "peak_rss_mb": self._peak_rss / (1024.0 * 1024.0),
            "sampled": True,
        }
        if self._io_entry is not None:
            try:
                io_exit = self._proc.io_counters()
                result["read_mb"] = (io_exit.read_bytes - self._io_entry.read_bytes) / (1024.0 * 1024.0)
                result["write_mb"] = (io_exit.write_bytes - self._io_entry.write_bytes) / (1024.0 * 1024.0)
            except Exception:
                pass
        return result


def start_sampler(interval: float = 0.5) -> "_Sampler | None":
    """Start the psutil enrichment sampler, or return None when unavailable."""
    try:
        import psutil  # noqa: F401
    except ImportError:
        return None
    return _Sampler(interval)
```

In `progress_context.py`, wire the sampler into the existing flow:

```python
    entry = capture_snapshot() if diagnostics else None
    sampler = start_sampler() if diagnostics else None
```

and in `_emit_diagnostics` (signature grows a `sampler` parameter; both call sites pass it):

```python
def _emit_diagnostics(tracker: ProgressTracker, entry: ResourceSnapshot, sampler: "_Sampler | None") -> None:
    payload = diagnostics_delta(entry, capture_snapshot())
    if sampler is not None:
        payload.update(sampler.stop())
    payload.update(consume_diagnostic_annotations())
    event = tracker._make_event(EventType.DIAGNOSTIC)
    event.extra["diagnostics"] = payload
    emit(event)
```

(import `start_sampler` and `_Sampler` from `hip_cargo.utils.diagnostics`).

- [x] **Step 4: Run tests**

Run: `uv run --extra monitoring python -m pytest tests/test_diagnostics.py -v`
Expected: all pass (sampler tests skip if psutil absent)

- [x] **Step 5: Lint and commit**

```bash
uv run ruff format . && uv run ruff check . --fix
git add -u src tests
git commit -m "feat: optional psutil sampling tier for diagnostics"
```

---

### Task 4: `build_diagnostics_report` + aggregator method

**Files:**
- Create: `src/hip_cargo/monitoring/diagnostics_report.py`
- Modify: `src/hip_cargo/monitoring/ray_backend.py` (add `get_diagnostics` to `ProgressAggregator`)
- Test: `tests/test_diagnostics_report.py`

**Interfaces:**
- Consumes: serialised event dicts as stored by `ProgressAggregator.push_event` (i.e. `ProgressEvent.to_dict()` output).
- Produces: `build_diagnostics_report(job_id: str, events: list[dict]) -> dict` returning `{"job_id", "pipeline_run_id", "tasks": [...], "pipeline": {"wall_s", "cpu_core_seconds"}}`; `ProgressAggregator.get_diagnostics(job_id) -> dict` delegating to it. Each task record = DIAGNOSTIC payload + `{"step": worker_name, "queue_lag_s": float | None, "cpu_utilisation": float | None}`.

- [x] **Step 1: Write the failing tests**

```python
# tests/test_diagnostics_report.py
"""Tests for the diagnostics report join (pure function, no Ray)."""

from hip_cargo.monitoring.diagnostics_report import build_diagnostics_report


def _ev(event_type, worker, ts, extra=None):
    return {
        "job_id": "j",
        "worker_name": worker,
        "event_type": event_type,
        "timestamp": ts,
        "extra": extra or {},
    }


def _diag(worker, ts, payload):
    e = _ev("diagnostic", worker, ts)
    e["extra"]["diagnostics"] = payload
    return e


PAYLOAD = {
    "wall_s": 10.0,
    "cpu_user_s": 36.0,
    "cpu_system_s": 4.0,
    "rss_entry_mb": 100.0,
    "peak_rss_mb": 900.0,
    "read_blocks": 0,
    "write_blocks": 8,
    "hostname": "n1",
    "pid": 42,
    "requested": {"num_cpus": 4},
}


def test_report_joins_queue_lag_and_utilisation():
    events = [
        _ev("pipeline_started", "pipe", 100.0, {"pipeline_run_id": "run1"}),
        _ev("step_started", "init", 100.5),
        _ev("started", "init", 101.5),
        _diag("init", 111.5, dict(PAYLOAD)),
        _ev("step_completed", "init", 112.0),
        _ev("completed", "pipe", 112.5),
    ]
    report = build_diagnostics_report("j", events)
    assert report["job_id"] == "j"
    assert len(report["tasks"]) == 1
    task = report["tasks"][0]
    assert task["step"] == "init"
    assert task["queue_lag_s"] == 1.0  # started 101.5 - step_started 100.5
    assert task["cpu_utilisation"] == (36.0 + 4.0) / (10.0 * 4)
    assert task["peak_rss_mb"] == 900.0
    assert report["pipeline"]["wall_s"] == 12.5  # completed - pipeline_started
    assert report["pipeline"]["cpu_core_seconds"] == 40.0


def test_report_nulls_when_no_request_or_timeline():
    events = [_diag("solo", 5.0, {k: v for k, v in PAYLOAD.items() if k != "requested"})]
    report = build_diagnostics_report("j", events)
    task = report["tasks"][0]
    assert task["queue_lag_s"] is None
    assert task["cpu_utilisation"] is None
    assert report["pipeline"]["wall_s"] is None
    assert report["pipeline"]["cpu_core_seconds"] == 40.0


def test_report_empty_when_no_diagnostics():
    events = [_ev("started", "w", 1.0)]
    report = build_diagnostics_report("j", events)
    assert report["tasks"] == []
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run --extra monitoring python -m pytest tests/test_diagnostics_report.py -v`
Expected: FAIL — module not found

- [x] **Step 3: Implement**

```python
# src/hip_cargo/monitoring/diagnostics_report.py
"""Join DIAGNOSTIC events with the step timeline into the agent-facing report.

Pure functions over serialised event dicts so the logic is testable without
a Ray cluster; the ProgressAggregator actor delegates here.
"""

from typing import Any


def _first_timestamp(events: list[dict], event_type: str, worker: str | None = None) -> float | None:
    for e in events:
        if e.get("event_type") != event_type:
            continue
        if worker is not None and e.get("worker_name") != worker:
            continue
        return e.get("timestamp")
    return None


def build_diagnostics_report(job_id: str, events: list[dict]) -> dict[str, Any]:
    """Build the per-task diagnostics report for a job.

    Args:
        job_id: The job the events belong to.
        events: Serialised ProgressEvent dicts in arrival order.

    Returns:
        {"job_id", "pipeline_run_id", "tasks": [...], "pipeline": {...}} where
        each task record is the DIAGNOSTIC payload plus step, queue_lag_s,
        and cpu_utilisation (null when underivable).
    """
    pipeline_run_id = None
    for e in events:
        run_id = e.get("extra", {}).get("pipeline_run_id")
        if run_id:
            pipeline_run_id = run_id
            break

    tasks: list[dict[str, Any]] = []
    for e in events:
        if e.get("event_type") != "diagnostic":
            continue
        payload = e.get("extra", {}).get("diagnostics")
        if not payload:
            continue
        step = e.get("worker_name", "")
        record: dict[str, Any] = {"step": step, **payload}

        step_started = _first_timestamp(events, "step_started", step)
        started = _first_timestamp(events, "started", step)
        record["queue_lag_s"] = (
            started - step_started if step_started is not None and started is not None else None
        )

        num_cpus = (payload.get("requested") or {}).get("num_cpus")
        wall = payload.get("wall_s")
        if num_cpus and wall:
            record["cpu_utilisation"] = (payload.get("cpu_user_s", 0.0) + payload.get("cpu_system_s", 0.0)) / (
                wall * num_cpus
            )
        else:
            record["cpu_utilisation"] = None
        tasks.append(record)

    pipeline_started = _first_timestamp(events, "pipeline_started")
    finished = _first_timestamp(events, "completed") or _first_timestamp(events, "failed")
    pipeline_wall = (
        finished - pipeline_started if pipeline_started is not None and finished is not None else None
    )
    cpu_core_seconds = sum(t.get("cpu_user_s", 0.0) + t.get("cpu_system_s", 0.0) for t in tasks)

    return {
        "job_id": job_id,
        "pipeline_run_id": pipeline_run_id,
        "tasks": tasks,
        "pipeline": {"wall_s": pipeline_wall, "cpu_core_seconds": cpu_core_seconds},
    }
```

Note: `_first_timestamp(events, "completed")` must not match a *worker's* completed event before the pipeline's. The runner emits the terminal `COMPLETED` with the pipeline worker name, but workers also emit `completed`. Search in **reverse** for the terminal event instead — use this variant for the pipeline wall:

```python
def _last_timestamp(events: list[dict], event_type: str) -> float | None:
    for e in reversed(events):
        if e.get("event_type") == event_type:
            return e.get("timestamp")
    return None
```

and compute `finished = _last_timestamp(events, "completed") or _last_timestamp(events, "failed")`. (The test's single `completed` event is unaffected; add a second worker-level `completed` before it in `test_report_joins_queue_lag_and_utilisation` to pin the behaviour: append `_ev("completed", "init", 111.9)` before the pipeline `completed` and keep the assertion at 12.5.)

In `src/hip_cargo/monitoring/ray_backend.py`, add to `ProgressAggregator` (after `get_pipeline_dag`):

```python
    def get_diagnostics(self, job_id: str) -> dict:
        """Get the per-task diagnostics report for a job.

        Args:
            job_id: The job/pipeline run to query.

        Returns:
            The joined diagnostics report (see build_diagnostics_report).
        """
        from hip_cargo.monitoring.diagnostics_report import build_diagnostics_report

        return build_diagnostics_report(job_id, self._events.get(job_id, []))
```

- [x] **Step 4: Run tests**

Run: `uv run --extra monitoring python -m pytest tests/test_diagnostics_report.py tests/test_ray_backend.py -v -m "not slow"`
Expected: report tests pass; ray_backend fast tests unaffected

- [x] **Step 5: Add a real-Ray round-trip test** (append to `tests/test_ray_backend.py`, following the file's existing `@pytest.mark.slow` fixture pattern for a ray-backed aggregator — reuse its ray fixture/actor setup)

```python
@pytest.mark.slow
def test_get_diagnostics_round_trip(ray_cluster):  # match the file's existing fixture name
    from hip_cargo.monitoring.ray_backend import RayProgressBackend, get_or_create_aggregator
    from hip_cargo.utils.diagnostics import annotate_diagnostics
    from hip_cargo.utils.progress import set_backend
    from hip_cargo.utils.progress_context import track_progress

    agg = get_or_create_aggregator(name="diag_test_agg")
    set_backend(RayProgressBackend(agg))
    annotate_diagnostics(requested={"num_cpus": 1}, memory_mode="greedy")
    with track_progress("stepA", job_id="diagjob"):
        pass
    import time

    deadline = time.time() + 10
    report = {}
    while time.time() < deadline:
        report = ray.get(agg.get_diagnostics.remote("diagjob"))
        if report["tasks"]:
            break
        time.sleep(0.2)
    assert len(report["tasks"]) == 1
    task = report["tasks"][0]
    assert task["step"] == "stepA"
    assert task["requested"] == {"num_cpus": 1}
    assert task["cpu_utilisation"] is not None
```

Run: `uv run --extra monitoring python -m pytest tests/test_ray_backend.py -v -m slow -k diagnostics`
Expected: PASS

- [x] **Step 6: Lint and commit**

```bash
uv run ruff format . && uv run ruff check . --fix
git add src/hip_cargo/monitoring/diagnostics_report.py src/hip_cargo/monitoring/ray_backend.py tests/test_diagnostics_report.py tests/test_ray_backend.py
git commit -m "feat: diagnostics report join and aggregator method"
```

---

### Task 5: `GET /api/progress/{job_id}/diagnostics` endpoint

**Files:**
- Modify: `src/hip_cargo/monitoring/server.py` (new route after `get_dag`)
- Modify: `tests/test_server.py` (`FakeAggregator` + endpoint tests)

**Interfaces:**
- Consumes: `ProgressAggregator.get_diagnostics(job_id) -> dict` (Task 4).
- Produces: `GET /api/progress/{job_id}/diagnostics` → 200 with the report, 404 when `tasks` is empty, 503 when the aggregator is unreachable (via the existing `_agg_call`).

- [x] **Step 1: Write the failing tests** (append to `tests/test_server.py`; extend `FakeAggregator.__init__` with `self.get_diagnostics = _RemoteMethod(self._get_diagnostics)` and)

```python
    def _get_diagnostics(self, job_id):
        return self._data.get("diagnostics", {}).get(
            job_id, {"job_id": job_id, "pipeline_run_id": None, "tasks": [], "pipeline": {}}
        )
```

```python
def test_get_diagnostics_returns_report():
    report = {
        "job_id": "job-1",
        "pipeline_run_id": "run1",
        "tasks": [{"step": "init", "wall_s": 1.0, "queue_lag_s": 0.1, "cpu_utilisation": 0.9}],
        "pipeline": {"wall_s": 1.5, "cpu_core_seconds": 3.6},
    }
    app = _create_test_app(aggregator_data={"diagnostics": {"job-1": report}})
    with TestClient(app) as client:
        resp = client.get("/api/progress/job-1/diagnostics")
    assert resp.status_code == 200
    assert resp.json() == report


def test_get_diagnostics_404_when_empty():
    app = _create_test_app()
    with TestClient(app) as client:
        resp = client.get("/api/progress/nope/diagnostics")
    assert resp.status_code == 404
```

(match the file's existing `_create_test_app` usage — adjust argument names to the actual helper signature if they differ.)

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run --extra monitoring python -m pytest tests/test_server.py -v -k diagnostics`
Expected: FAIL — 404 for both (route missing) and/or AttributeError on FakeAggregator

- [x] **Step 3: Implement** (in `create_app`, after the `get_dag` route)

```python
    @app.get("/api/progress/{job_id}/diagnostics")
    async def get_diagnostics(job_id: str):
        report = await _agg_call("get_diagnostics", job_id)
        if not report or not report.get("tasks"):
            raise HTTPException(status_code=404, detail=f"No diagnostics data for job '{job_id}'")
        return report
```

- [x] **Step 4: Run the server test file**

Run: `uv run --extra monitoring python -m pytest tests/test_server.py -v`
Expected: all pass

- [x] **Step 5: Lint and commit**

```bash
uv run ruff format . && uv run ruff check . --fix
git add src/hip_cargo/monitoring/server.py tests/test_server.py
git commit -m "feat: serve per-task diagnostics report endpoint"
```

---

### Task 6: Full-suite verification + docs flip

**Files:**
- Modify: `docs/hip-cargo-monitoring-design-doc.md` (§3.7 status, §4 API table)
- Modify: `docs/superpowers/specs/2026-07-12-per-task-diagnostics-design.md` (status line)
- Modify: `CLAUDE.md` (utils/monitoring file inventory: add `diagnostics.py`, `diagnostics_report.py`)

**Interfaces:** none (docs + verification).

- [x] **Step 1: Run the full fast suite**

Run: `uv run --extra monitoring python -m pytest -m "not slow" -q`
Expected: all pass, no regressions

- [x] **Step 2: Run the slow (Ray) suite**

Run: `uv run --extra monitoring python -m pytest -m slow -q`
Expected: all pass (real local Ray cluster; DIAGNOSTIC events flow through aggregator unchanged — they are ordinary events)

- [x] **Step 3: Docs flip**

- In `docs/hip-cargo-monitoring-design-doc.md` §3.7: change "Designed but not implemented; full design in…" to "Implemented (see `utils/diagnostics.py`, `monitoring/diagnostics_report.py`); design in…" and adjust the API-reference row from "(planned, §3.7)" to "Per-task resource breakdown (§3.7)".
- In the spec: change `**Status:** Draft — pending review …` to `**Status:** Implemented on apis (2026-07-12)`.
- In `CLAUDE.md`: add `diagnostics.py` under `utils/` and `diagnostics_report.py` under `monitoring/` in the file inventory.

- [x] **Step 4: Lint and commit**

```bash
uv run ruff format . && uv run ruff check . --fix
git add -u docs CLAUDE.md
git commit -m "docs: mark per-task diagnostics implemented"
```

---

### Task 7: stokify wiring — annotations + demo diagnostics table (NO COMMITS in stokify)

**Files:**
- Modify: `/home/bester/software/stokify/src/stokify/runtime/tasks.py` (annotate import_s/requested/memory_mode in each task)
- Modify: `/home/bester/software/stokify/demo.py` (fetch + print diagnostics table, extend PASS gate)

**Interfaces:**
- Consumes: `hip_cargo.utils.diagnostics.annotate_diagnostics` (Task 1/2) and `GET /api/progress/{job_id}/diagnostics` (Task 5). stokify resolves the local editable hip-cargo, now on `apis` with these changes.

- [x] **Step 1: Annotate each task wrapper**

In `tasks.py`, inside each `@ray.remote` task body, after `_activate_backend()` and around the lazy import (shown for `init_task`; mirror for `process_task` with `{"num_cpus": 2}` and `image_task` with `{"num_cpus": 2}`, matching each decorator's `num_cpus`):

```python
    if monitor:
        _activate_backend()
    import time as _time

    _t0 = _time.perf_counter()
    from stokify.core.init import init_inmem

    if monitor:
        from hip_cargo.utils.diagnostics import annotate_diagnostics

        annotate_diagnostics(
            import_s=_time.perf_counter() - _t0,
            requested={"num_cpus": 1},
            memory_mode=memory_mode,
        )
```

(the annotations merge into the DIAGNOSTIC event the core function's `track_progress` emits.)

- [x] **Step 2: Extend demo.py**

After the residual-metric section (around line 186), add a diagnostics section that queries the new endpoint, prints a table, and appends to `failures` when the contract is not met:

```python
        REQUIRED_DIAG_FIELDS = {
            "step",
            "wall_s",
            "cpu_user_s",
            "cpu_system_s",
            "rss_entry_mb",
            "peak_rss_mb",
            "hostname",
            "pid",
            "import_s",
            "requested",
            "memory_mode",
            "queue_lag_s",
            "cpu_utilisation",
        }

        diag_resp = client.get(f"/api/progress/{job_id}/diagnostics")
        print("\n--- GET /api/progress/{job_id}/diagnostics ---")
        if diag_resp.status_code == 200:
            report = diag_resp.json()
            header = f"{'step':<10}{'wall_s':>8}{'cpu_s':>8}{'util':>6}{'peak_mb':>9}{'lag_s':>7}{'import_s':>9}"
            print(header)
            for task in report["tasks"]:
                cpu_s = task["cpu_user_s"] + task["cpu_system_s"]
                util = task["cpu_utilisation"]
                print(
                    f"{task['step']:<10}"
                    f"{task['wall_s']:>8.2f}"
                    f"{cpu_s:>8.2f}"
                    f"{util if util is None else round(util, 2)!s:>6}"
                    f"{task['peak_rss_mb']:>9.0f}"
                    f"{task['queue_lag_s']:>7.2f}"
                    f"{task['import_s']:>9.3f}"
                )
            steps_seen = {t["step"] for t in report["tasks"]}
            if steps_seen != {"init", "process", "image"}:
                failures.append(f"diagnostics missing steps: {steps_seen}")
            for task in report["tasks"]:
                missing = REQUIRED_DIAG_FIELDS - set(task)
                if missing:
                    failures.append(f"diagnostics fields missing for {task['step']}: {sorted(missing)}")
        else:
            failures.append(f"/diagnostics returned {diag_resp.status_code}")
```

Also update the final PASS line to mention diagnostics:
`" RESULT: PASS — events, metrics, DAG, and per-task diagnostics flow through the monitoring API."`

- [x] **Step 3: Run the self-verifying demo end-to-end**

```bash
cd /home/bester/software/stokify && uv sync --extra full && uv run --extra full python demo.py --memory-mode greedy
```
Expected: `RESULT: PASS` including the printed per-task diagnostics table with three rows (init/process/image), non-null `queue_lag_s` and `cpu_utilisation`.

- [x] **Step 4: Run stokify's fast tests (regression check only)**

```bash
cd /home/bester/software/stokify && uv run --extra full python -m pytest -m "not slow" -q
```
Expected: no new failures relative to the pre-change state (record the before state first: run this command once *before* Step 1).

- [x] **Step 5: DO NOT COMMIT** — leave stokify changes in the working tree (the repo carries the user's uncommitted work-in-progress). Report the changed files in the final summary instead.
