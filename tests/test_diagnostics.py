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
from hip_cargo.utils.progress import EventType, NullBackend, ProgressEvent, set_backend
from hip_cargo.utils.progress_context import track_progress

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


def test_sampler_reports_sampled_peak():
    psutil = pytest.importorskip("psutil")  # noqa: F841
    from hip_cargo.utils.diagnostics import start_sampler

    sampler = start_sampler(interval=0.01)
    assert sampler is not None
    time.sleep(0.05)
    result = sampler.stop()
    assert result["sampled"] is True
    assert result["peak_rss_mb"] > 0


def test_track_progress_payload_marks_sampled_tier():
    pytest.importorskip("psutil")
    backend = ListBackend()
    set_backend(backend)
    with track_progress("w", job_id="j"):
        time.sleep(0.02)
    payload = backend.events[-1].extra["diagnostics"]
    assert payload.get("sampled") is True
