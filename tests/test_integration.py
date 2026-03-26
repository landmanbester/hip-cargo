"""Integration tests: full monitoring loop with real Ray aggregator.

Verifies that progress events flow through the protocol → Ray actor →
FastAPI server correctly. Uses a real local Ray cluster but mocks the
JobSubmissionClient.
"""

from contextlib import asynccontextmanager
from pathlib import Path

import pytest

ray = pytest.importorskip("ray")

from fastapi.testclient import TestClient  # noqa: E402

from hip_cargo.monitoring.config import MonitorSettings  # noqa: E402
from hip_cargo.monitoring.ray_backend import ProgressAggregator, RayProgressBackend  # noqa: E402
from hip_cargo.monitoring.recipe_parser import parse_recipe  # noqa: E402
from hip_cargo.monitoring.server import create_app  # noqa: E402
from hip_cargo.utils.progress import EventType, NullBackend, ProgressEvent, emit, set_backend  # noqa: E402
from hip_cargo.utils.progress_context import track_progress  # noqa: E402
from tests.mocks import FakeJobClient  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def ray_context():
    """Start a local Ray cluster for integration tests."""
    ctx = ray.init(
        num_cpus=2,
        ignore_reinit_error=True,
        runtime_env={"working_dir": None},
    )
    yield ctx
    ray.shutdown()


def run_mock_pipeline(pipeline_run_id: str, n_major_cycles: int = 5):
    """Simulate a SARA pipeline run, emitting progress events.

    Steps: init -> grid -> sara (with major cycles) -> restore -> degrid
    """
    steps = ["init", "grid", "sara", "restore", "degrid"]

    # Emit PIPELINE_STARTED with DAG structure
    emit(
        ProgressEvent(
            job_id=pipeline_run_id,
            worker_name="pipeline",
            event_type=EventType.PIPELINE_STARTED,
            extra={
                "recipe": "sara",
                "steps": steps,
                "edges": [[steps[i], steps[i + 1]] for i in range(len(steps) - 1)],
            },
        )
    )

    for i, step_name in enumerate(steps):
        # Emit STEP_STARTED
        emit(
            ProgressEvent(
                job_id=pipeline_run_id,
                worker_name=step_name,
                event_type=EventType.STEP_STARTED,
                extra={"step_index": i, "total_steps": len(steps)},
            )
        )

        if step_name == "sara":
            # Sara has major cycles with metrics
            with track_progress(
                step_name,
                total_steps=n_major_cycles,
                job_id=pipeline_run_id,
                pipeline_run_id=pipeline_run_id,
            ) as tracker:
                for cycle in range(n_major_cycles):
                    tracker.step(message=f"Major cycle {cycle + 1}/{n_major_cycles}")
                    peak_residual = 1.0 / (cycle + 1)  # decreasing
                    tracker.metric("peak_residual", peak_residual)
                    tracker.metric("objective", 100.0 / (cycle + 1))
        else:
            # Other steps just start and complete
            with track_progress(
                step_name,
                total_steps=1,
                job_id=pipeline_run_id,
                pipeline_run_id=pipeline_run_id,
            ) as tracker:
                tracker.step(message=f"{step_name} complete")

        # Emit STEP_COMPLETED
        emit(
            ProgressEvent(
                job_id=pipeline_run_id,
                worker_name=step_name,
                event_type=EventType.STEP_COMPLETED,
                extra={"step_index": i},
            )
        )

    # Emit pipeline completed
    emit(
        ProgressEvent(
            job_id=pipeline_run_id,
            worker_name="pipeline",
            event_type=EventType.COMPLETED,
        )
    )


def _setup_backend(ray_context):
    """Create an anonymous aggregator, wire up the backend, return the actor handle."""
    agg = ProgressAggregator.remote(1000)
    backend = RayProgressBackend(agg)
    set_backend(backend)
    return agg


def _create_integration_app(aggregator):
    """Create a test app with a real Ray aggregator but fake job client."""
    settings = MonitorSettings(_env_file=None, recipes_dir=str(FIXTURES))
    app = create_app(settings)

    @asynccontextmanager
    async def _test_lifespan(app):
        from hip_cargo.monitoring.dispatcher import EventDispatcher

        app.state.aggregator = aggregator
        app.state.job_client = FakeJobClient()
        app.state.settings = settings
        app.state.dispatcher = EventDispatcher(aggregator=aggregator, poll_interval=0.1)
        app.state.dispatcher.start()
        yield
        await app.state.dispatcher.stop()

    app.router.lifespan_context = _test_lifespan
    return app


# --- Test 1: Full pipeline lifecycle via aggregator ---


@pytest.mark.slow
def test_full_pipeline_lifecycle(ray_context):
    """Events flow through protocol -> RayProgressBackend -> ProgressAggregator."""
    agg = _setup_backend(ray_context)
    try:
        run_mock_pipeline("integration-test-1")

        # Verify job is registered
        jobs = ray.get(agg.get_all_jobs.remote())
        job_ids = [j["job_id"] for j in jobs]
        assert "integration-test-1" in job_ids

        # Latest event should be COMPLETED
        latest = ray.get(agg.get_latest.remote("integration-test-1"))
        assert latest["event_type"] == "completed"
        assert latest["worker_name"] == "pipeline"

        # Events should contain the full lifecycle
        events = ray.get(agg.get_events.remote("integration-test-1"))
        event_types = [e["event_type"] for e in events]
        assert event_types[0] == "pipeline_started"
        assert event_types[-1] == "completed"
        assert "step_started" in event_types
        assert "step_completed" in event_types
        assert "progress" in event_types
        assert "metric" in event_types

        # Metrics history
        residuals = ray.get(agg.get_metrics_history.remote("integration-test-1", "peak_residual"))
        assert len(residuals) == 5  # one per major cycle
        values = [r["value"] for r in residuals]
        assert values == sorted(values, reverse=True)  # decreasing

        # DAG structure
        dag = ray.get(agg.get_pipeline_dag.remote("integration-test-1"))
        assert dag is not None
        assert len(dag["steps"]) == 5
        assert len(dag["edges"]) == 4
    finally:
        set_backend(NullBackend())


# --- Test 2: REST API serves pipeline data ---


@pytest.mark.slow
def test_rest_api_serves_pipeline_data(ray_context):
    """FastAPI endpoints return correct data from real aggregator."""
    agg = _setup_backend(ray_context)
    try:
        run_mock_pipeline("integration-test-2")

        app = _create_integration_app(agg)
        with TestClient(app, raise_server_exceptions=False) as client:
            # Latest progress
            resp = client.get("/api/progress/integration-test-2")
            assert resp.status_code == 200
            data = resp.json()
            assert data["event_type"] == "completed"

            # All events
            resp = client.get("/api/progress/integration-test-2/events")
            assert resp.status_code == 200
            events = resp.json()
            assert len(events) > 0
            assert events[0]["event_type"] == "pipeline_started"

            # Metrics
            resp = client.get("/api/progress/integration-test-2/metrics/peak_residual")
            assert resp.status_code == 200
            metrics = resp.json()
            assert len(metrics) == 5
            values = [m["value"] for m in metrics]
            assert values[0] > values[-1]  # decreasing

            # DAG
            resp = client.get("/api/progress/integration-test-2/dag")
            assert resp.status_code == 200
            dag = resp.json()
            assert len(dag["steps"]) == 5
            assert len(dag["edges"]) == 4
    finally:
        set_backend(NullBackend())


# --- Test 3: Recipe DAG endpoint with real fixture ---


@pytest.mark.slow
def test_recipe_dag_endpoint(ray_context):
    """Recipe endpoints return correct DAG from sara.yml fixture."""
    agg = _setup_backend(ray_context)
    try:
        app = _create_integration_app(agg)
        with TestClient(app, raise_server_exceptions=False) as client:
            # List recipes
            resp = client.get("/api/recipes")
            assert resp.status_code == 200
            names = [r["name"] for r in resp.json()]
            assert "sara" in names

            # Get sara recipe
            resp = client.get("/api/recipes/sara")
            assert resp.status_code == 200
            dag = resp.json()
            assert dag["name"] == "pfb-sara"
            assert len(dag["steps"]) == 5
            assert dag["steps"][0]["name"] == "initialize"
            assert dag["steps"][2]["name"] == "saradeconv"
            assert [s["cab"] for s in dag["steps"]] == ["init", "grid", "sara", "restore", "degrid"]
            assert len(dag["edges"]) == 4

            # Verify inputs
            inputs_by_name = {i["name"]: i for i in dag["inputs"]}
            assert inputs_by_name["ms"]["dtype"] == "List[URI]"
            assert inputs_by_name["ms"]["required"] is True
            assert inputs_by_name["niter"]["dtype"] == "int"
            assert inputs_by_name["niter"]["default"] == 15
            assert inputs_by_name["robustness"]["dtype"] == "float"
            assert inputs_by_name["robustness"]["default"] == -0.3
    finally:
        set_backend(NullBackend())


# --- Test 4: Pipeline event ordering ---


@pytest.mark.slow
def test_pipeline_event_ordering(ray_context):
    """Events are emitted in the correct lifecycle order."""
    agg = _setup_backend(ray_context)
    try:
        run_mock_pipeline("integration-test-4", n_major_cycles=3)
        events = ray.get(agg.get_events.remote("integration-test-4"))
        event_types = [e["event_type"] for e in events]

        # First and last events
        assert event_types[0] == "pipeline_started"
        assert event_types[-1] == "completed"

        # For each step, STEP_STARTED must come before STEP_COMPLETED
        for step_name in ["init", "grid", "sara", "restore", "degrid"]:
            step_events = [(i, e) for i, e in enumerate(events) if e.get("worker_name") == step_name]
            step_types = [(i, e["event_type"]) for i, e in step_events]

            start_indices = [i for i, t in step_types if t == "step_started"]
            complete_indices = [i for i, t in step_types if t == "step_completed"]
            assert len(start_indices) == 1
            assert len(complete_indices) == 1
            assert start_indices[0] < complete_indices[0]

        # Sara step has progress and metric events between its step_started/step_completed
        sara_events = [(i, e) for i, e in enumerate(events) if e.get("worker_name") == "sara"]
        sara_start = next(i for i, e in sara_events if e["event_type"] == "step_started")
        sara_end = next(i for i, e in sara_events if e["event_type"] == "step_completed")
        sara_between = [e for i, e in sara_events if sara_start < i < sara_end]
        sara_between_types = {e["event_type"] for e in sara_between}
        assert "progress" in sara_between_types
        assert "metric" in sara_between_types
    finally:
        set_backend(NullBackend())


# --- Test 5: Multiple concurrent pipelines ---


@pytest.mark.slow
def test_multiple_pipelines(ray_context):
    """Two pipelines with different IDs are tracked independently."""
    agg = _setup_backend(ray_context)
    try:
        run_mock_pipeline("integration-test-5a", n_major_cycles=3)
        run_mock_pipeline("integration-test-5b", n_major_cycles=2)

        # Both pipelines registered
        jobs = ray.get(agg.get_all_jobs.remote())
        job_ids = {j["job_id"] for j in jobs}
        assert "integration-test-5a" in job_ids
        assert "integration-test-5b" in job_ids

        # Events are separate
        events_a = ray.get(agg.get_events.remote("integration-test-5a"))
        events_b = ray.get(agg.get_events.remote("integration-test-5b"))
        assert all(e["job_id"] == "integration-test-5a" for e in events_a)
        assert all(e["job_id"] == "integration-test-5b" for e in events_b)

        # Metric histories are independent
        residuals_a = ray.get(agg.get_metrics_history.remote("integration-test-5a", "peak_residual"))
        residuals_b = ray.get(agg.get_metrics_history.remote("integration-test-5b", "peak_residual"))
        assert len(residuals_a) == 3
        assert len(residuals_b) == 2
    finally:
        set_backend(NullBackend())


# --- Test 6: Sara fixture recipe structure ---


@pytest.mark.slow
def test_sara_recipe_structure(ray_context):
    """Parse sara.yml directly and verify full structure."""
    dag = parse_recipe(FIXTURES / "sara.yml", resolve_cabs=False)

    # 5 steps with correct cabs
    assert len(dag.steps) == 5
    assert [s.cab for s in dag.steps] == ["init", "grid", "sara", "restore", "degrid"]

    # Recipe inputs
    inputs_by_name = {i.name: i for i in dag.inputs}

    ms = inputs_by_name["ms"]
    assert ms.dtype == "List[URI]"
    assert ms.required is True

    niter = inputs_by_name["niter"]
    assert niter.dtype == "int"
    assert niter.default == 15

    robustness = inputs_by_name["robustness"]
    assert robustness.dtype == "float"
    assert robustness.default == -0.3

    # saradeconv step params
    sara_step = dag.get_step("saradeconv")
    sara_params = {p.name: p for p in sara_step.params}
    assert sara_params["niter"].is_binding is True
    assert "recipe.niter" in sara_params["niter"].recipe_refs
    assert sara_params["rmsfactor"].is_binding is True
    assert "recipe.rmsfactor" in sara_params["rmsfactor"].recipe_refs

    # initialize step params
    init_step = dag.get_step("initialize")
    init_params = {p.name: p for p in init_step.params}
    assert init_params["ms"].is_binding is True
    assert "recipe.ms" in init_params["ms"].recipe_refs
    assert init_params["data-column"].is_binding is True
    assert "recipe.data-column" in init_params["data-column"].recipe_refs
