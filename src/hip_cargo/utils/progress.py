"""Progress event protocol for hip-cargo monitoring.

Defines the core event types, dataclass, and backend protocol that form
the foundation of the monitoring layer. Uses only stdlib — no new dependencies.

Thread safety: the module-level _backend is a simple global. This is safe
because in Ray each worker process has its own Python interpreter, so there
is no cross-worker contention.
"""

import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class EventType(StrEnum):
    """Types of progress events emitted by workers."""

    STARTED = "started"
    PROGRESS = "progress"
    LOG = "log"
    ARTIFACT = "artifact"
    METRIC = "metric"
    COMPLETED = "completed"
    FAILED = "failed"
    PIPELINE_STARTED = "pipeline_started"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"


@dataclass
class ProgressEvent:
    """A single progress event emitted by a worker or pipeline step.

    Args:
        job_id: Unique identifier for this job/pipeline run.
        worker_name: Name of the current step (e.g. "grid", "clean", "sara").
        event_type: The type of event.
        timestamp: Unix timestamp, defaults to current time.
        current_step: Current iteration (major cycle).
        total_steps: Total iterations expected.
        message: Human-readable message.
        metric_name: Name of the metric (for METRIC events).
        metric_value: Value of the metric (for METRIC events).
        artifact_path: Path to the artifact (for ARTIFACT events).
        artifact_type: Type of artifact — "image", "fits", "zarr", etc.
        extra: Extensibility dict for future fields (DAG structure, object refs, etc.).
    """

    job_id: str
    worker_name: str
    event_type: EventType
    timestamp: float = field(default_factory=time.time)
    current_step: int | None = None
    total_steps: int | None = None
    message: str = ""
    metric_name: str | None = None
    metric_value: float | None = None
    artifact_path: str | None = None
    artifact_type: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict, converting event_type to its string value."""
        d = asdict(self)
        d["event_type"] = self.event_type.value
        return d


@runtime_checkable
class ProgressBackend(Protocol):
    """Protocol for progress event backends."""

    def emit(self, event: ProgressEvent) -> None: ...

    def close(self) -> None: ...


class NullBackend:
    """No-op backend used when monitoring is not enabled. Zero overhead."""

    def emit(self, event: ProgressEvent) -> None:
        pass

    def close(self) -> None:
        pass


_backend: ProgressBackend = NullBackend()


def set_backend(backend: ProgressBackend) -> None:
    """Swap the active progress backend."""
    global _backend
    _backend = backend


def get_backend() -> ProgressBackend:
    """Retrieve the active progress backend."""
    return _backend


def emit(event: ProgressEvent) -> None:
    """Emit a progress event to the active backend."""
    _backend.emit(event)
