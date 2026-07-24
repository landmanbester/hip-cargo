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


def _last_timestamp(events: list[dict], event_type: str) -> float | None:
    for e in reversed(events):
        if e.get("event_type") == event_type:
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
        record["queue_lag_s"] = started - step_started if step_started is not None and started is not None else None

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
    finished = _last_timestamp(events, "completed") or _last_timestamp(events, "failed")
    pipeline_wall = finished - pipeline_started if pipeline_started is not None and finished is not None else None
    cpu_core_seconds = sum(t.get("cpu_user_s", 0.0) + t.get("cpu_system_s", 0.0) for t in tasks)

    return {
        "job_id": job_id,
        "pipeline_run_id": pipeline_run_id,
        "tasks": tasks,
        "pipeline": {"wall_s": pipeline_wall, "cpu_core_seconds": cpu_core_seconds},
    }
