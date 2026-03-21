"""Tests for the Ray progress aggregator and backend.

These tests require Ray and are marked slow since Ray startup takes a moment.
"""

import time

import pytest

ray = pytest.importorskip("ray")

from hip_cargo.monitoring.ray_backend import (  # noqa: E402
    ProgressAggregator,
    RayProgressBackend,
    get_or_create_aggregator,
)
from hip_cargo.utils.progress import EventType, ProgressEvent  # noqa: E402


@pytest.fixture(scope="module")
def ray_context():
    """Start and stop a local Ray instance for testing."""
    ray.init(num_cpus=2, ignore_reinit_error=True)
    yield
    ray.shutdown()


def _make_event_dict(
    job_id: str = "job1",
    worker_name: str = "worker",
    event_type: str = "progress",
    current_step: int = 1,
    **kwargs,
) -> dict:
    """Helper to build event dicts for testing."""
    d = {
        "job_id": job_id,
        "worker_name": worker_name,
        "event_type": event_type,
        "timestamp": time.time(),
        "current_step": current_step,
        "total_steps": None,
        "message": "",
        "metric_name": None,
        "metric_value": None,
        "artifact_path": None,
        "artifact_type": None,
        "extra": {},
    }
    d.update(kwargs)
    return d


@pytest.mark.slow
def test_aggregator_basic_flow(ray_context):
    """Push events and verify get_all_jobs, get_latest, get_events."""
    agg = ProgressAggregator.remote(1000)

    ray.get(agg.push_event.remote(_make_event_dict(event_type="started", current_step=0)))
    ray.get(agg.push_event.remote(_make_event_dict(event_type="progress", current_step=1)))
    ray.get(agg.push_event.remote(_make_event_dict(event_type="completed", current_step=2)))

    jobs = ray.get(agg.get_all_jobs.remote())
    assert len(jobs) == 1
    assert jobs[0]["job_id"] == "job1"
    assert jobs[0]["status"] == "completed"

    latest = ray.get(agg.get_latest.remote("job1"))
    assert latest["event_type"] == "completed"

    events = ray.get(agg.get_events.remote("job1"))
    assert len(events) == 3


@pytest.mark.slow
def test_event_ring_buffer(ray_context):
    """Events are trimmed when exceeding max_events."""
    max_events = 10
    agg = ProgressAggregator.remote(max_events)

    for i in range(25):
        ray.get(agg.push_event.remote(_make_event_dict(current_step=i)))

    events = ray.get(agg.get_events.remote("job1"))
    assert len(events) <= max_events
    # Should have kept the most recent half
    assert len(events) == max_events // 2


@pytest.mark.slow
def test_get_metrics_history(ray_context):
    """get_metrics_history returns only matching metric events."""
    agg = ProgressAggregator.remote(1000)

    ray.get(agg.push_event.remote(_make_event_dict(event_type="progress", current_step=1)))
    ray.get(
        agg.push_event.remote(
            _make_event_dict(event_type="metric", current_step=1, metric_name="residual", metric_value=0.1)
        )
    )
    ray.get(
        agg.push_event.remote(
            _make_event_dict(event_type="metric", current_step=2, metric_name="residual", metric_value=0.05)
        )
    )
    ray.get(
        agg.push_event.remote(
            _make_event_dict(event_type="metric", current_step=2, metric_name="loss", metric_value=1.0)
        )
    )

    history = ray.get(agg.get_metrics_history.remote("job1", "residual"))
    assert len(history) == 2
    assert history[0]["value"] == 0.1
    assert history[1]["value"] == 0.05

    loss_history = ray.get(agg.get_metrics_history.remote("job1", "loss"))
    assert len(loss_history) == 1


@pytest.mark.slow
def test_get_pipeline_dag(ray_context):
    """pipeline_started event's extra dict is returned by get_pipeline_dag."""
    agg = ProgressAggregator.remote(1000)

    dag_structure = {"steps": ["init", "grid", "sara"], "edges": [["init", "grid"], ["grid", "sara"]]}
    ray.get(agg.push_event.remote(_make_event_dict(event_type="pipeline_started", current_step=0, extra=dag_structure)))

    dag = ray.get(agg.get_pipeline_dag.remote("job1"))
    assert dag == dag_structure

    # No pipeline_started for unknown job
    assert ray.get(agg.get_pipeline_dag.remote("unknown")) is None


@pytest.mark.slow
def test_ray_progress_backend(ray_context):
    """RayProgressBackend.emit() pushes events to the aggregator."""
    agg = ProgressAggregator.remote(1000)
    backend = RayProgressBackend(agg)

    event = ProgressEvent(
        job_id="backend-test",
        worker_name="w1",
        event_type=EventType.PROGRESS,
        current_step=1,
    )
    backend.emit(event)

    # Fire-and-forget is async, so we need to ensure it's processed
    # by making a synchronous call after
    latest = ray.get(agg.get_latest.remote("backend-test"))
    assert latest is not None
    assert latest["job_id"] == "backend-test"
    assert latest["event_type"] == "progress"


@pytest.mark.slow
def test_get_or_create_aggregator(ray_context):
    """get_or_create_aggregator creates on first call, reuses on second."""
    name = f"test_aggregator_{int(time.time() * 1000)}"
    agg1 = get_or_create_aggregator(name=name, max_events=100)
    agg2 = get_or_create_aggregator(name=name, max_events=100)

    # Push via agg1, read via agg2 — same actor
    ray.get(agg1.push_event.remote(_make_event_dict(job_id="shared")))
    events = ray.get(agg2.get_events.remote("shared"))
    assert len(events) == 1


@pytest.mark.slow
def test_incremental_get_events(ray_context):
    """get_events with since_index returns only events from that index."""
    agg = ProgressAggregator.remote(1000)

    for i in range(10):
        ray.get(agg.push_event.remote(_make_event_dict(job_id="incr", current_step=i)))

    subset = ray.get(agg.get_events.remote("incr", since_index=5))
    assert len(subset) == 5
    assert subset[0]["current_step"] == 5
    assert subset[-1]["current_step"] == 9
