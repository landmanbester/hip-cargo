"""Tests for the FastAPI monitoring server.

Uses a FakeAggregator and FakeJobClient so no real Ray cluster is needed.
"""

import concurrent.futures
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hip_cargo.monitoring.config import MonitorSettings
from hip_cargo.monitoring.server import create_app

FIXTURES = Path(__file__).parent / "fixtures"


# --- Fake aggregator that mimics Ray actor handle interface ---


class _FakeRef:
    """Mimics a Ray ObjectRef with a .future() method."""

    def __init__(self, value):
        self._value = value

    def future(self):
        f = concurrent.futures.Future()
        f.set_result(self._value)
        return f


class _RemoteMethod:
    """Mimics the .remote() callable on a Ray actor method."""

    def __init__(self, fn):
        self._fn = fn

    def remote(self, *args, **kwargs):
        return _FakeRef(self._fn(*args, **kwargs))


class FakeAggregator:
    """Mock aggregator that returns pre-configured data without Ray.

    Each public method is wrapped so that `agg.method_name.remote(args)`
    returns a _FakeRef compatible with asyncio.wrap_future.
    """

    def __init__(self, data=None):
        self._data = data or {}
        self.get_latest = _RemoteMethod(self._get_latest)
        self.get_events = _RemoteMethod(self._get_events)
        self.get_all_jobs = _RemoteMethod(self._get_all_jobs)
        self.get_metrics_history = _RemoteMethod(self._get_metrics_history)
        self.get_pipeline_dag = _RemoteMethod(self._get_pipeline_dag)

    def _get_latest(self, job_id):
        return self._data.get("latest", {}).get(job_id)

    def _get_events(self, job_id, since_index=0):
        return self._data.get("events", {}).get(job_id, [])[since_index:]

    def _get_all_jobs(self):
        return self._data.get("jobs", [])

    def _get_metrics_history(self, job_id, metric_name):
        return self._data.get("metrics", {}).get(f"{job_id}:{metric_name}", [])

    def _get_pipeline_dag(self, job_id):
        return self._data.get("dags", {}).get(job_id)


# --- Fake JobSubmissionClient ---


class _FakeJobDetails:
    """Mimics ray.job_submission.JobDetails attributes."""

    def __init__(self, **kwargs):
        self.job_id = kwargs.get("job_id", "")
        self.submission_id = kwargs.get("submission_id", "")
        self.status = kwargs.get("status", "RUNNING")
        self.entrypoint = kwargs.get("entrypoint", "")
        self.message = kwargs.get("message", "")
        self.error_type = kwargs.get("error_type", None)
        self.start_time = kwargs.get("start_time", None)
        self.end_time = kwargs.get("end_time", None)
        self.metadata = kwargs.get("metadata", {})
        self.runtime_env = kwargs.get("runtime_env", {})


class FakeJobClient:
    """Mock JobSubmissionClient that returns canned data without Ray."""

    def __init__(self, jobs=None):
        self._jobs = jobs or {}

    def list_jobs(self):
        return [_FakeJobDetails(**j) for j in self._jobs.values()]

    def get_job_info(self, job_id):
        if job_id not in self._jobs:
            raise RuntimeError(f"Job {job_id} not found")
        return _FakeJobDetails(**self._jobs[job_id])

    def get_job_logs(self, job_id):
        if job_id not in self._jobs:
            raise RuntimeError(f"Job {job_id} not found")
        return self._jobs[job_id].get("logs", "")

    def stop_job(self, job_id):
        if job_id not in self._jobs:
            raise RuntimeError(f"Job {job_id} not found")
        return True

    def submit_job(self, entrypoint, runtime_env=None, metadata=None):
        return "raysubmit_test_123"


class FailingJobClient:
    """Mock JobSubmissionClient that always raises ConnectionError."""

    def list_jobs(self):
        raise ConnectionError("Ray cluster unreachable")

    def get_job_info(self, job_id):
        raise ConnectionError("Ray cluster unreachable")

    def get_job_logs(self, job_id):
        raise ConnectionError("Ray cluster unreachable")

    def stop_job(self, job_id):
        raise ConnectionError("Ray cluster unreachable")

    def submit_job(self, entrypoint, runtime_env=None, metadata=None):
        raise ConnectionError("Ray cluster unreachable")


# --- Fixtures ---

_DEFAULT_JOB_DATA = {
    "ray-job-1": {
        "job_id": "ray-job-1",
        "submission_id": "raysubmit_1",
        "status": "RUNNING",
        "entrypoint": "stimela run ...",
        "logs": "some log output",
    },
}


def _create_test_app(
    aggregator_data=None,
    auth_token=None,
    job_data=None,
    job_client=None,
):
    """Create a test app with mocked dependencies, bypassing the Ray lifespan."""
    settings = MonitorSettings(
        _env_file=None,
        auth_token=auth_token,
        recipes_dir=str(FIXTURES),
    )
    app = create_app(settings)

    aggregator = FakeAggregator(aggregator_data or {})
    jc = job_client or FakeJobClient(job_data if job_data is not None else _DEFAULT_JOB_DATA)

    @asynccontextmanager
    async def _test_lifespan(app):
        from hip_cargo.monitoring.dispatcher import EventDispatcher

        app.state.aggregator = aggregator
        app.state.job_client = jc
        app.state.settings = settings
        app.state.dispatcher = EventDispatcher(aggregator=aggregator, poll_interval=0.1)
        app.state.dispatcher.start()
        yield
        await app.state.dispatcher.stop()

    app.router.lifespan_context = _test_lifespan
    return app


@pytest.fixture
def client():
    """TestClient with default mock data."""
    app = _create_test_app(
        aggregator_data={
            "latest": {"job1": {"job_id": "job1", "event_type": "progress", "current_step": 5}},
            "events": {"job1": [{"event_type": "started"}, {"event_type": "progress"}]},
            "jobs": [{"job_id": "job1", "status": "progress"}],
        }
    )
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# --- Tests ---


def test_root_returns_html(client):
    """GET / returns 200 with HTML content."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "hip-cargo Monitor" in resp.text
    assert "text/html" in resp.headers["content-type"]


def test_docs_available(client):
    """GET /docs returns 200 (Swagger UI)."""
    resp = client.get("/docs")
    assert resp.status_code == 200


def test_list_recipes(client):
    """GET /api/recipes lists the sara recipe from fixtures."""
    resp = client.get("/api/recipes")
    assert resp.status_code == 200
    recipes = resp.json()
    names = [r["name"] for r in recipes]
    assert "sara" in names


def test_get_recipe_sara(client):
    """GET /api/recipes/sara returns the parsed DAG."""
    resp = client.get("/api/recipes/sara")
    assert resp.status_code == 200
    dag = resp.json()
    assert dag["name"] == "pfb-sara"
    assert len(dag["steps"]) == 5
    assert len(dag["edges"]) == 4


def test_get_recipe_not_found(client):
    """GET /api/recipes/nonexistent returns 404."""
    resp = client.get("/api/recipes/nonexistent")
    assert resp.status_code == 404


def test_progress_latest(client):
    """GET /api/progress/{job_id} returns latest event from aggregator."""
    resp = client.get("/api/progress/job1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == "job1"
    assert data["current_step"] == 5


def test_progress_not_found():
    """GET /api/progress/{job_id} returns 404 for unknown job."""
    app = _create_test_app(aggregator_data={"latest": {}})
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/api/progress/unknown")
        assert resp.status_code == 404


def test_auth_blocks_without_token():
    """With auth_token configured, /api/ routes require Bearer token."""
    app = _create_test_app(auth_token="secret")
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/api/recipes")
        assert resp.status_code == 401


def test_auth_allows_with_correct_token():
    """With auth_token configured, correct Bearer token grants access."""
    app = _create_test_app(auth_token="secret")
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/api/recipes", headers={"Authorization": "Bearer secret"})
        assert resp.status_code == 200


def test_auth_not_required_when_unconfigured(client):
    """With auth_token=None, all endpoints are accessible."""
    resp = client.get("/api/recipes")
    assert resp.status_code == 200


def test_root_not_gated_by_auth():
    """Root page is not behind auth even when token is set."""
    app = _create_test_app(auth_token="secret")
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/")
        assert resp.status_code == 200


def test_list_jobs(client):
    """GET /api/jobs returns list of jobs with correct fields."""
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    jobs = resp.json()
    assert isinstance(jobs, list)
    assert len(jobs) == 1
    assert jobs[0]["job_id"] == "ray-job-1"
    assert jobs[0]["submission_id"] == "raysubmit_1"
    assert jobs[0]["status"] == "RUNNING"


def test_get_job(client):
    """GET /api/jobs/{job_id} returns job details."""
    resp = client.get("/api/jobs/ray-job-1")
    assert resp.status_code == 200
    job = resp.json()
    assert job["job_id"] == "ray-job-1"
    assert job["status"] == "RUNNING"


def test_get_job_not_found(client):
    """GET /api/jobs/{job_id} returns 404 for unknown job."""
    resp = client.get("/api/jobs/nonexistent")
    assert resp.status_code == 404


def test_get_job_logs(client):
    """GET /api/jobs/{job_id}/logs returns logs dict."""
    resp = client.get("/api/jobs/ray-job-1/logs")
    assert resp.status_code == 200
    assert resp.json() == {"logs": "some log output"}


def test_stop_job(client):
    """POST /api/jobs/{job_id}/stop returns stopped status."""
    resp = client.post("/api/jobs/ray-job-1/stop")
    assert resp.status_code == 200
    assert resp.json() == {"stopped": True}


def test_jobs_ray_unreachable():
    """503 is returned when Ray cluster is unreachable."""
    app = _create_test_app(job_client=FailingJobClient())
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/api/jobs")
        assert resp.status_code == 503


def test_submit_pipeline(client):
    """POST /api/pipelines/submit returns submission_id and entrypoint."""
    resp = client.post(
        "/api/pipelines/submit",
        json={"recipe": "sara", "params": {"niter": 10, "overwrite": True}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["submission_id"] == "raysubmit_test_123"
    assert "stimela run" in data["entrypoint"]
    assert "gosara" in data["entrypoint"]
    assert "niter=10" in data["entrypoint"]
    assert "overwrite=true" in data["entrypoint"]


def test_submit_pipeline_list_params(client):
    """Pipeline submission handles list params with comma-separated values."""
    resp = client.post(
        "/api/pipelines/submit",
        json={"recipe": "sara", "params": {"ms": ["/data/a.ms", "/data/b.ms"]}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "ms=/data/a.ms,/data/b.ms" in data["entrypoint"]


def test_submit_pipeline_missing_recipe(client):
    """Pipeline submission returns 400 when recipe field is missing."""
    resp = client.post("/api/pipelines/submit", json={"params": {}})
    assert resp.status_code == 400


def test_submit_pipeline_unknown_recipe(client):
    """Pipeline submission returns 404 for unknown recipe."""
    resp = client.post("/api/pipelines/submit", json={"recipe": "nonexistent"})
    assert resp.status_code == 404
