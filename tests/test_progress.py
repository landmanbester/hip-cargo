"""Tests for the progress event protocol and context manager."""

import pytest

from hip_cargo.utils.progress import (
    EventType,
    NullBackend,
    ProgressBackend,
    ProgressEvent,
    get_backend,
    set_backend,
)
from hip_cargo.utils.progress_context import track_progress


class ListBackend:
    """Collects emitted events into a list for test assertions."""

    def __init__(self) -> None:
        self.events: list[ProgressEvent] = []

    def emit(self, event: ProgressEvent) -> None:
        self.events.append(event)

    def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _reset_backend():
    """Reset the module-level backend before and after each test."""
    set_backend(NullBackend())
    yield
    set_backend(NullBackend())


def test_null_backend_no_side_effects():
    """Emitting events with NullBackend doesn't raise and has no side effects."""
    backend = NullBackend()
    event = ProgressEvent(job_id="test", worker_name="w", event_type=EventType.STARTED)
    backend.emit(event)
    backend.close()


def test_set_get_backend():
    """Module-level backend can be swapped and retrieved."""
    backend = ListBackend()
    set_backend(backend)
    assert get_backend() is backend


def test_null_backend_is_progress_backend():
    """NullBackend satisfies the ProgressBackend protocol."""
    assert isinstance(NullBackend(), ProgressBackend)


def test_list_backend_is_progress_backend():
    """ListBackend satisfies the ProgressBackend protocol."""
    assert isinstance(ListBackend(), ProgressBackend)


def test_progress_event_to_dict():
    """Serialisation produces correct dict with event_type as string."""
    event = ProgressEvent(
        job_id="abc",
        worker_name="grid",
        event_type=EventType.METRIC,
        metric_name="residual",
        metric_value=0.01,
    )
    d = event.to_dict()
    assert d["event_type"] == "metric"
    assert d["job_id"] == "abc"
    assert d["worker_name"] == "grid"
    assert d["metric_name"] == "residual"
    assert d["metric_value"] == 0.01
    assert isinstance(d["timestamp"], float)
    assert d["extra"] == {}


def test_track_progress_happy_path():
    """STARTED, PROGRESS (with incrementing steps), METRIC, and COMPLETED are emitted."""
    backend = ListBackend()
    set_backend(backend)

    with track_progress("clean", total_steps=3, job_id="job1") as tracker:
        tracker.step("cycle 1")
        tracker.step("cycle 2")
        tracker.metric("residual", 0.05)

    types = [e.event_type for e in backend.events]
    assert types == [
        EventType.STARTED,
        EventType.PROGRESS,
        EventType.PROGRESS,
        EventType.METRIC,
        EventType.COMPLETED,
    ]
    # Step counter increments
    assert backend.events[1].current_step == 1
    assert backend.events[2].current_step == 2
    assert backend.events[2].message == "cycle 2"
    # Metric values
    assert backend.events[3].metric_name == "residual"
    assert backend.events[3].metric_value == 0.05


def test_track_progress_failure_path():
    """Exception emits FAILED with the message, then re-raises."""
    backend = ListBackend()
    set_backend(backend)

    with pytest.raises(ValueError, match="boom"):
        with track_progress("grid", job_id="job2") as tracker:
            tracker.step()
            raise ValueError("boom")

    types = [e.event_type for e in backend.events]
    assert types == [EventType.STARTED, EventType.PROGRESS, EventType.FAILED]
    assert backend.events[2].message == "boom"


def test_track_progress_with_pipeline_run_id():
    """pipeline_run_id appears in the extra dict of all emitted events."""
    backend = ListBackend()
    set_backend(backend)

    with track_progress("sara", job_id="job3", pipeline_run_id="pipe-abc") as tracker:
        tracker.step()
        tracker.log("hello")

    for event in backend.events:
        assert event.extra["pipeline_run_id"] == "pipe-abc"


def test_tracker_artifact():
    """ARTIFACT events contain the path and type."""
    backend = ListBackend()
    set_backend(backend)

    with track_progress("imager", job_id="job4") as tracker:
        tracker.artifact("/tmp/dirty.fits", artifact_type="fits")

    artifact_event = backend.events[1]
    assert artifact_event.event_type == EventType.ARTIFACT
    assert artifact_event.artifact_path == "/tmp/dirty.fits"
    assert artifact_event.artifact_type == "fits"


def test_auto_generated_job_id():
    """When no job_id is provided, one is generated and used consistently."""
    backend = ListBackend()
    set_backend(backend)

    with track_progress("worker") as tracker:
        tracker.step()
        tracker.metric("loss", 1.0)

    job_ids = {e.job_id for e in backend.events}
    assert len(job_ids) == 1  # all events share the same job_id
    job_id = job_ids.pop()
    assert len(job_id) == 8  # uuid4 hex truncated to 8 chars
