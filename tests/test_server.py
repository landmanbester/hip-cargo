"""Tests for the FastAPI monitoring server.

Uses a FakeAggregator and mock httpx transport so no real Ray cluster is needed.
"""

import concurrent.futures
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
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


# --- Mock httpx transport for Ray Dashboard proxy ---


def _mock_transport(handler):
    """Create an httpx.MockTransport from a sync handler."""
    return httpx.MockTransport(handler)


def _ray_dashboard_handler(request: httpx.Request) -> httpx.Response:
    """Default mock handler for Ray Dashboard API."""
    if request.url.path == "/api/jobs/":
        return httpx.Response(200, json=[{"job_id": "ray-job-1", "status": "RUNNING"}])
    if request.url.path.startswith("/api/jobs/") and request.url.path.endswith("/logs"):
        return httpx.Response(200, json={"logs": "some log output"})
    if "/api/jobs/" in str(request.url.path):
        job_id = request.url.path.split("/api/jobs/")[1].rstrip("/")
        if request.method == "POST" and job_id.endswith("stop"):
            return httpx.Response(200, json={"stopped": True})
        return httpx.Response(200, json={"job_id": job_id, "status": "RUNNING"})
    return httpx.Response(404)


# --- Fixtures ---


def _create_test_app(
    aggregator_data=None,
    auth_token=None,
    ray_handler=None,
):
    """Create a test app with mocked dependencies, bypassing the Ray lifespan."""
    settings = MonitorSettings(
        _env_file=None,
        auth_token=auth_token,
        recipes_dir=str(FIXTURES),
    )
    app = create_app(settings)

    # Replace the lifespan with a no-op that injects our mocks
    aggregator = FakeAggregator(aggregator_data or {})
    http_client = httpx.AsyncClient(
        transport=_mock_transport(ray_handler or _ray_dashboard_handler),
        base_url="http://fake-ray-dashboard:8265",
    )

    @asynccontextmanager
    async def _test_lifespan(app):
        app.state.aggregator = aggregator
        app.state.http_client = http_client
        app.state.settings = settings
        yield
        await http_client.aclose()

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
    # Use context manager to suppress lifespan (already injected state)
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
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/api/progress/unknown")
        assert resp.status_code == 404


def test_auth_blocks_without_token():
    """With auth_token configured, /api/ routes require Bearer token."""
    app = _create_test_app(auth_token="secret")
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/api/recipes")
        assert resp.status_code == 401


def test_auth_allows_with_correct_token():
    """With auth_token configured, correct Bearer token grants access."""
    app = _create_test_app(auth_token="secret")
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/api/recipes", headers={"Authorization": "Bearer secret"})
        assert resp.status_code == 200


def test_auth_not_required_when_unconfigured(client):
    """With auth_token=None, all endpoints are accessible."""
    resp = client.get("/api/recipes")
    assert resp.status_code == 200


def test_root_not_gated_by_auth():
    """Root page is not behind auth even when token is set."""
    app = _create_test_app(auth_token="secret")
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/")
        assert resp.status_code == 200


def test_proxy_jobs(client):
    """GET /api/jobs proxies to Ray Dashboard."""
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    jobs = resp.json()
    assert isinstance(jobs, list)


def test_proxy_job_logs(client):
    """GET /api/jobs/{job_id}/logs proxies to Ray Dashboard."""
    resp = client.get("/api/jobs/ray-job-1/logs")
    assert resp.status_code == 200


def test_proxy_ray_unreachable():
    """503 is returned when Ray Dashboard is unreachable."""

    def failing_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    app = _create_test_app(ray_handler=failing_handler)
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/api/jobs")
        assert resp.status_code == 503
