"""FastAPI server for the hip-cargo monitoring dashboard.

A thin proxy over Ray's infrastructure that adds application-level
progress tracking, recipe parsing, and command discovery.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from hip_cargo.monitoring.config import MonitorSettings

logger = logging.getLogger(__name__)


async def _get_from_actor(ref):
    """Await a Ray object ref in an async context without blocking the event loop."""
    return await asyncio.wrap_future(ref.future())


def create_app(settings: MonitorSettings | None = None) -> FastAPI:
    """Create the hip-cargo monitoring FastAPI application.

    Args:
        settings: Monitoring configuration. Uses defaults if None.

    Returns:
        Configured FastAPI application.
    """
    if settings is None:
        settings = MonitorSettings(_env_file=None)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        import ray

        from hip_cargo.monitoring.ray_backend import get_or_create_aggregator

        ray.init(address=settings.ray_address or "auto", ignore_reinit_error=True)
        app.state.aggregator = get_or_create_aggregator(
            name=settings.aggregator_name,
            max_events=settings.max_events_per_job,
        )
        app.state.http_client = httpx.AsyncClient(
            base_url=settings.ray_dashboard_url,
            timeout=30.0,
        )
        app.state.settings = settings
        yield
        await app.state.http_client.aclose()

    app = FastAPI(
        title="hip-cargo Monitor",
        description="Pipeline monitoring dashboard for hip-cargo projects",
        lifespan=lifespan,
    )

    # --- Auth middleware ---
    if settings.auth_token is not None:

        class TokenAuthMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next):
                if not request.url.path.startswith("/api/"):
                    return await call_next(request)
                auth_header = request.headers.get("Authorization", "")
                if auth_header == f"Bearer {settings.auth_token}":
                    return await call_next(request)
                return JSONResponse(status_code=401, content={"detail": "Invalid or missing token"})

        app.add_middleware(TokenAuthMiddleware)

    # --- Root / static ---
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def root():
        return """
        <!DOCTYPE html>
        <html>
        <head><title>hip-cargo Monitor</title></head>
        <body>
            <h1>hip-cargo Monitor</h1>
            <p>Frontend not yet built. Use the API docs at
            <a href="/docs">/docs</a> to explore the API.</p>
        </body>
        </html>
        """

    # --- Jobs (proxy to Ray Dashboard) ---

    async def _proxy_ray(method: str, path: str, **kwargs) -> dict:
        """Proxy a request to the Ray Dashboard API."""
        try:
            resp = await app.state.http_client.request(method, path, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Ray Dashboard is unreachable")
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)

    @app.get("/api/jobs")
    async def list_jobs():
        ray_jobs = await _proxy_ray("GET", "/api/jobs/")
        # Enrich with progress data
        try:
            agg_jobs = await _get_from_actor(app.state.aggregator.get_all_jobs.remote())
            progress_by_id = {j["job_id"]: j for j in agg_jobs}
        except Exception:
            progress_by_id = {}
        if isinstance(ray_jobs, list):
            for job in ray_jobs:
                job_id = job.get("job_id") or job.get("submission_id", "")
                if job_id in progress_by_id:
                    job["progress"] = progress_by_id[job_id]
        return ray_jobs

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str):
        job = await _proxy_ray("GET", f"/api/jobs/{job_id}")
        try:
            latest = await _get_from_actor(app.state.aggregator.get_latest.remote(job_id))
            if latest:
                job["progress"] = latest
        except Exception:
            pass
        return job

    @app.get("/api/jobs/{job_id}/logs")
    async def get_job_logs(job_id: str):
        return await _proxy_ray("GET", f"/api/jobs/{job_id}/logs")

    @app.post("/api/jobs/{job_id}/stop")
    async def stop_job(job_id: str):
        return await _proxy_ray("POST", f"/api/jobs/{job_id}/stop")

    # --- Progress (from ProgressAggregator) ---

    async def _agg_call(method_name: str, *args):
        """Call an aggregator method, returning 503 if the actor is unreachable."""
        try:
            method = getattr(app.state.aggregator, method_name)
            return await _get_from_actor(method.remote(*args))
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Aggregator unavailable: {exc}")

    @app.get("/api/progress/{job_id}")
    async def get_progress(job_id: str):
        latest = await _agg_call("get_latest", job_id)
        if latest is None:
            raise HTTPException(status_code=404, detail=f"No progress data for job '{job_id}'")
        return latest

    @app.get("/api/progress/{job_id}/events")
    async def get_progress_events(job_id: str, since: int = Query(default=0, ge=0)):
        return await _agg_call("get_events", job_id, since)

    @app.get("/api/progress/{job_id}/metrics/{metric_name}")
    async def get_metrics(job_id: str, metric_name: str):
        return await _agg_call("get_metrics_history", job_id, metric_name)

    @app.get("/api/progress/{job_id}/dag")
    async def get_dag(job_id: str):
        dag = await _agg_call("get_pipeline_dag", job_id)
        if dag is None:
            raise HTTPException(status_code=404, detail=f"No DAG data for job '{job_id}'")
        return dag

    # --- Recipes ---

    @app.get("/api/recipes")
    async def list_recipes():
        from hip_cargo.monitoring.recipe_discovery import discover_recipes

        return discover_recipes(settings.recipes_dir)

    @app.get("/api/recipes/{recipe_name}")
    async def get_recipe(recipe_name: str):
        from hip_cargo.monitoring.recipe_discovery import find_recipe
        from hip_cargo.monitoring.recipe_parser import parse_recipe

        try:
            path = find_recipe(recipe_name, settings.recipes_dir)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Recipe '{recipe_name}' not found")
        dag = parse_recipe(path)
        return dag.to_dict()

    # --- Commands ---

    @app.get("/api/commands")
    async def list_commands():
        """List available commands and their parameter schemas from cab YAML files."""
        from hip_cargo.monitoring.cab_resolver import discover_project_cabs

        return discover_project_cabs(settings.cli_module)

    # --- Pipeline submission ---

    @app.post("/api/pipelines/submit")
    async def submit_pipeline(body: dict):
        from hip_cargo.monitoring.recipe_discovery import find_recipe
        from hip_cargo.monitoring.recipe_parser import parse_recipe

        recipe_name = body.get("recipe")
        if not recipe_name:
            raise HTTPException(status_code=400, detail="'recipe' field is required")

        try:
            recipe_path = find_recipe(recipe_name, settings.recipes_dir)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Recipe '{recipe_name}' not found")

        dag = parse_recipe(recipe_path)
        params = body.get("params", {})

        # Build stimela entrypoint command
        param_args = " ".join(f"{k}={v}" for k, v in params.items())
        entrypoint = f"stimela run {recipe_path} {dag.recipe_key} {param_args}".strip()

        runtime_env = body.get("ray_runtime_env", {})
        submission = {
            "entrypoint": entrypoint,
            "runtime_env": runtime_env,
        }

        result = await _proxy_ray("POST", "/api/jobs/", json=submission)
        return result

    # --- WebSocket ---

    @app.websocket("/ws/progress/{job_id}")
    async def ws_progress(websocket: WebSocket, job_id: str, token: str | None = None):
        ws_settings = websocket.app.state.settings
        if ws_settings.auth_token and token != ws_settings.auth_token:
            await websocket.close(code=4001, reason="Unauthorized")
            return

        await websocket.accept()
        agg = websocket.app.state.aggregator
        last_index = 0

        try:
            while True:
                events = await _get_from_actor(agg.get_events.remote(job_id, last_index))
                for event in events:
                    await websocket.send_json(event)
                last_index += len(events)

                # Check for terminal state
                if events:
                    last_type = events[-1].get("event_type", "")
                    if last_type in ("completed", "failed", "step_failed"):
                        await websocket.send_json({"type": "close", "reason": last_type})
                        break

                await asyncio.sleep(ws_settings.websocket_poll_interval)
        except WebSocketDisconnect:
            pass
        except Exception:
            await websocket.close(code=1011, reason="Internal error")

    return app
