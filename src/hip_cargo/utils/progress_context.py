"""Ergonomic context manager for emitting progress events from workers."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from hip_cargo.utils.progress import EventType, ProgressEvent, emit


class ProgressTracker:
    """Tracks progress within a worker step, emitting events via the active backend.

    Maintains a step counter so callers just call `step()` to advance.

    Args:
        job_id: Unique identifier for this job.
        worker_name: Name of the current worker/step.
        total_steps: Total iterations expected, if known.
        pipeline_run_id: Pipeline run ID for grouping steps, stored in extra.
    """

    def __init__(
        self,
        job_id: str,
        worker_name: str,
        total_steps: int | None = None,
        pipeline_run_id: str | None = None,
    ) -> None:
        self.job_id = job_id
        self.worker_name = worker_name
        self.total_steps = total_steps
        self._current_step = 0
        self._extra: dict[str, str] = {}
        if pipeline_run_id is not None:
            self._extra["pipeline_run_id"] = pipeline_run_id

    def _make_event(self, event_type: EventType, **kwargs: object) -> ProgressEvent:
        """Build a ProgressEvent with common fields pre-filled."""
        return ProgressEvent(
            job_id=self.job_id,
            worker_name=self.worker_name,
            event_type=event_type,
            current_step=self._current_step,
            total_steps=self.total_steps,
            extra={**self._extra},
            **kwargs,  # type: ignore[arg-type]
        )

    def step(self, message: str = "") -> None:
        """Increment step counter and emit a PROGRESS event."""
        self._current_step += 1
        emit(self._make_event(EventType.PROGRESS, message=message))

    def metric(self, name: str, value: float) -> None:
        """Emit a METRIC event."""
        emit(self._make_event(EventType.METRIC, metric_name=name, metric_value=value))

    def artifact(self, path: str, artifact_type: str = "file") -> None:
        """Emit an ARTIFACT event."""
        emit(self._make_event(EventType.ARTIFACT, artifact_path=path, artifact_type=artifact_type))

    def log(self, message: str) -> None:
        """Emit a LOG event."""
        emit(self._make_event(EventType.LOG, message=message))


@contextmanager
def track_progress(
    worker_name: str,
    total_steps: int | None = None,
    job_id: str | None = None,
    pipeline_run_id: str | None = None,
) -> Iterator[ProgressTracker]:
    """Context manager that emits STARTED/COMPLETED/FAILED events around a block.

    Args:
        worker_name: Name of the worker or step.
        total_steps: Total iterations expected, if known.
        job_id: Unique job identifier. Auto-generated if not provided.
        pipeline_run_id: Pipeline run ID for grouping steps in a pipeline run.

    Yields:
        A ProgressTracker for emitting progress, metric, artifact, and log events.
    """
    if job_id is None:
        job_id = uuid.uuid4().hex[:8]

    tracker = ProgressTracker(job_id, worker_name, total_steps, pipeline_run_id)

    emit(tracker._make_event(EventType.STARTED))
    try:
        yield tracker
    except Exception as exc:
        emit(tracker._make_event(EventType.FAILED, message=str(exc)))
        raise
    else:
        emit(tracker._make_event(EventType.COMPLETED))
