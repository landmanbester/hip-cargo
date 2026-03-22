"""FastAPI server for the hip-cargo monitoring dashboard.

Uses the Ray Jobs Python SDK (JobSubmissionClient) for job management
and the ProgressAggregator actor for application-level progress tracking.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from hip_cargo.monitoring.config import MonitorSettings

logger = logging.getLogger(__name__)


async def _get_from_actor(ref):
    """Await a Ray object ref in an async context without blocking the event loop."""
    return await asyncio.wrap_future(ref.future())


async def _run_sync(func, *args, **kwargs):
    """Run a sync function in the default thread pool executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))


def _job_details_to_dict(jd) -> dict:
    """Convert a JobDetails object to a plain dict."""
    return {
        "job_id": jd.job_id,
        "submission_id": jd.submission_id,
        "status": jd.status.value if hasattr(jd.status, "value") else str(jd.status),
        "entrypoint": jd.entrypoint,
        "message": jd.message,
        "error_type": jd.error_type,
        "start_time": jd.start_time,
        "end_time": jd.end_time,
        "metadata": jd.metadata,
        "runtime_env": jd.runtime_env,
    }


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
        from ray.job_submission import JobSubmissionClient

        from hip_cargo.monitoring.dispatcher import EventDispatcher
        from hip_cargo.monitoring.ray_backend import get_or_create_aggregator

        ray.init(address=settings.ray_address or "auto", ignore_reinit_error=True)
        app.state.aggregator = get_or_create_aggregator(
            name=settings.aggregator_name,
            max_events=settings.max_events_per_job,
        )
        app.state.job_client = JobSubmissionClient(
            address=settings.ray_dashboard_url,
        )
        app.state.dispatcher = EventDispatcher(
            aggregator=app.state.aggregator,
            poll_interval=settings.websocket_poll_interval,
        )
        app.state.dispatcher.start()
        app.state.settings = settings
        yield
        await app.state.dispatcher.stop()

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

    # --- Jobs (via Ray Jobs SDK) ---

    @app.get("/api/jobs")
    async def list_jobs():
        """List all jobs, enriched with application-level progress data."""
        try:
            job_details_list = await _run_sync(app.state.job_client.list_jobs)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Ray cluster unreachable: {exc}")

        jobs = [_job_details_to_dict(jd) for jd in job_details_list]

        # Enrich with progress data from aggregator
        try:
            agg_jobs = await _get_from_actor(app.state.aggregator.get_all_jobs.remote())
            progress_by_id = {j["job_id"]: j for j in agg_jobs}
        except Exception:
            progress_by_id = {}

        for job in jobs:
            jid = job.get("submission_id") or job.get("job_id", "")
            if jid in progress_by_id:
                job["progress"] = progress_by_id[jid]

        return jobs

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str):
        """Get details for a specific job."""
        try:
            jd = await _run_sync(app.state.job_client.get_job_info, job_id)
        except RuntimeError:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Ray cluster unreachable: {exc}")

        job_dict = _job_details_to_dict(jd)

        # Enrich with progress data
        try:
            latest = await _get_from_actor(app.state.aggregator.get_latest.remote(job_id))
            if latest:
                job_dict["progress"] = latest
        except Exception:
            pass

        return job_dict

    @app.get("/api/jobs/{job_id}/logs")
    async def get_job_logs(job_id: str):
        """Get logs for a specific job."""
        try:
            logs = await _run_sync(app.state.job_client.get_job_logs, job_id)
        except RuntimeError:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Ray cluster unreachable: {exc}")
        return {"logs": logs}

    @app.post("/api/jobs/{job_id}/stop")
    async def stop_job(job_id: str):
        """Stop a running job."""
        try:
            stopped = await _run_sync(app.state.job_client.stop_job, job_id)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Failed to stop job: {exc}")
        return {"stopped": stopped}

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

        dag = parse_recipe(recipe_path, resolve_cabs=False)
        params = body.get("params", {})

        # Build stimela entrypoint command with proper quoting
        param_parts = []
        for k, v in params.items():
            if isinstance(v, list):
                param_parts.append(f"{k}={','.join(str(item) for item in v)}")
            elif isinstance(v, bool):
                param_parts.append(f"{k}={'true' if v else 'false'}")
            else:
                str_val = str(v)
                if " " in str_val:
                    str_val = f"'{str_val}'"
                param_parts.append(f"{k}={str_val}")

        param_args = " ".join(param_parts)
        entrypoint = f"stimela run {recipe_path} {dag.recipe_key} {param_args}".strip()

        runtime_env = body.get("ray_runtime_env", {})
        metadata = body.get("metadata", {})
        metadata.setdefault("recipe", recipe_name)
        metadata.setdefault("project", "hip-cargo")

        try:
            submission_id = await _run_sync(
                app.state.job_client.submit_job,
                entrypoint=entrypoint,
                runtime_env=runtime_env or None,
                metadata=metadata,
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Failed to submit job: {exc}")

        return {"submission_id": submission_id, "entrypoint": entrypoint}

    # --- WebSocket ---

    @app.websocket("/ws/progress/{job_id}")
    async def ws_progress(websocket: WebSocket, job_id: str, token: str | None = None):
        ws_settings = websocket.app.state.settings
        if ws_settings.auth_token and token != ws_settings.auth_token:
            await websocket.close(code=4001, reason="Unauthorized")
            return

        await websocket.accept()
        dispatcher = websocket.app.state.dispatcher
        queue, sub_id = dispatcher.subscribe(job_id)

        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    # Send a heartbeat to keep the connection alive
                    await websocket.send_json({"type": "heartbeat"})
                    continue

                await websocket.send_json(event)

                # Check for terminal state
                event_type = event.get("event_type", "")
                if event_type in ("completed", "failed", "step_failed"):
                    await websocket.send_json({"type": "close", "reason": event_type})
                    break
        except WebSocketDisconnect:
            pass
        except Exception:
            try:
                await websocket.close(code=1011, reason="Internal error")
            except Exception:
                pass
        finally:
            dispatcher.unsubscribe(job_id, sub_id)

    return app
