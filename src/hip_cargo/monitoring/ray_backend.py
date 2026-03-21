"""Ray actor and backend for aggregating progress events from distributed workers."""

import ray

from hip_cargo.utils.progress import ProgressEvent


@ray.remote
class ProgressAggregator:
    """Ray actor that collects progress events from all workers.

    Processes one method call at a time (actor model) so no explicit
    locking is needed. The FastAPI server queries this actor to get
    current pipeline state.

    Args:
        max_events: Maximum events to retain per job. When exceeded,
            the oldest half is trimmed (ring buffer behaviour).
    """

    def __init__(self, max_events: int = 1000) -> None:
        self._events: dict[str, list[dict]] = {}
        self._latest: dict[str, dict] = {}
        self._jobs: dict[str, dict] = {}
        self._max_events = max_events

    def push_event(self, event_dict: dict) -> None:
        """Receive an event from a worker (fire-and-forget on caller side).

        Args:
            event_dict: Serialised ProgressEvent dict.
        """
        job_id = event_dict["job_id"]

        # Append to event list
        if job_id not in self._events:
            self._events[job_id] = []
        self._events[job_id].append(event_dict)

        # Trim if over max — keep the most recent half
        if len(self._events[job_id]) > self._max_events:
            half = self._max_events // 2
            self._events[job_id] = self._events[job_id][-half:]

        # Update latest snapshot
        self._latest[job_id] = event_dict

        # Update job registry
        event_type = event_dict.get("event_type", "")
        if job_id not in self._jobs:
            self._jobs[job_id] = {
                "job_id": job_id,
                "worker_name": event_dict.get("worker_name", ""),
                "status": event_type,
                "started_at": event_dict.get("timestamp"),
                "updated_at": event_dict.get("timestamp"),
            }
        else:
            self._jobs[job_id]["status"] = event_type
            self._jobs[job_id]["updated_at"] = event_dict.get("timestamp")
            if event_type in ("completed", "failed"):
                self._jobs[job_id]["finished_at"] = event_dict.get("timestamp")

    def get_latest(self, job_id: str) -> dict | None:
        """Get the most recent event for a job."""
        return self._latest.get(job_id)

    def get_events(self, job_id: str, since_index: int = 0) -> list[dict]:
        """Get events since a given index (for incremental polling).

        Args:
            job_id: The job to query.
            since_index: Return events from this index onwards.
        """
        events = self._events.get(job_id, [])
        return events[since_index:]

    def get_all_jobs(self) -> list[dict]:
        """Get summary of all known jobs."""
        return list(self._jobs.values())

    def get_metrics_history(self, job_id: str, metric_name: str) -> list[dict]:
        """Get time series for a specific metric.

        Args:
            job_id: The job to query.
            metric_name: Name of the metric to filter by.

        Returns:
            List of {"step": int, "value": float, "timestamp": float} dicts.
        """
        return [
            {
                "step": e.get("current_step"),
                "value": e.get("metric_value"),
                "timestamp": e.get("timestamp"),
            }
            for e in self._events.get(job_id, [])
            if e.get("event_type") == "metric" and e.get("metric_name") == metric_name
        ]

    def get_pipeline_dag(self, job_id: str) -> dict | None:
        """Get the DAG structure from a pipeline_started event.

        Args:
            job_id: The job/pipeline run to query.

        Returns:
            The extra dict from the pipeline_started event, or None.
        """
        for e in self._events.get(job_id, []):
            if e.get("event_type") == "pipeline_started":
                return e.get("extra")
        return None


class RayProgressBackend:
    """ProgressBackend that pushes events to a Ray ProgressAggregator actor.

    Uses fire-and-forget (no blocking on the remote call) so workers
    are not slowed down by progress reporting.
    """

    def __init__(self, aggregator_handle: ray.actor.ActorHandle) -> None:
        self._aggregator = aggregator_handle

    def emit(self, event: ProgressEvent) -> None:
        """Emit an event to the aggregator (fire-and-forget)."""
        self._aggregator.push_event.remote(event.to_dict())

    def close(self) -> None:
        """No-op — the detached actor outlives this backend."""
        pass


def get_or_create_aggregator(
    name: str = "progress_aggregator",
    max_events: int = 1000,
) -> ray.actor.ActorHandle:
    """Get an existing named ProgressAggregator or create a new one.

    The actor is created with lifetime="detached" so it persists
    independently of the creating process.

    Args:
        name: Name for the Ray actor.
        max_events: Maximum events per job.

    Returns:
        Handle to the ProgressAggregator actor.
    """
    try:
        return ray.get_actor(name)
    except ValueError:
        return ProgressAggregator.options(
            name=name,
            lifetime="detached",
        ).remote(max_events)
