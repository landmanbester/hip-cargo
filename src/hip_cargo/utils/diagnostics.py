"""Per-task resource diagnostics capture.

Stdlib-only, matching the ethos of ``utils/progress.py``: two ``getrusage``
syscalls per tracked block, zero overhead when no monitoring backend is
attached. The delta produced here rides in a ``DIAGNOSTIC`` event's
``extra["diagnostics"]`` payload; its key names are a public contract that
optimising agents depend on — do not rename them.

Honesty caveats (also documented in the design spec):
- ``ru_maxrss`` is a *process* high-water mark and Ray reuses worker
  processes, so ``peak_rss_mb`` can predate the task. Both ``rss_entry_mb``
  and ``peak_rss_mb`` are reported so consumers can detect a stale peak.
- ``RUSAGE_SELF`` excludes unreaped child processes.
"""

import os
import resource
import socket
import sys
import time
from dataclasses import dataclass
from typing import Any

# ru_maxrss is KiB on Linux, bytes on macOS.
_MAXRSS_TO_MB = 1.0 / (1024.0 * 1024.0) if sys.platform == "darwin" else 1.0 / 1024.0


@dataclass(frozen=True)
class ResourceSnapshot:
    """Point-in-time resource usage of the current process."""

    perf_s: float
    cpu_user_s: float
    cpu_system_s: float
    maxrss_mb: float
    inblocks: int
    oublocks: int


def capture_snapshot() -> ResourceSnapshot:
    """Capture a resource snapshot for the current process (RUSAGE_SELF)."""
    ru = resource.getrusage(resource.RUSAGE_SELF)
    return ResourceSnapshot(
        perf_s=time.perf_counter(),
        cpu_user_s=ru.ru_utime,
        cpu_system_s=ru.ru_stime,
        maxrss_mb=ru.ru_maxrss * _MAXRSS_TO_MB,
        inblocks=ru.ru_inblock,
        oublocks=ru.ru_oublock,
    )


def diagnostics_delta(entry: ResourceSnapshot, exit_: ResourceSnapshot) -> dict[str, Any]:
    """Compute the per-task diagnostics record between two snapshots.

    Args:
        entry: Snapshot taken at block entry.
        exit_: Snapshot taken at block exit.

    Returns:
        Dict with the stable, unit-suffixed field names agents consume.
    """
    return {
        "wall_s": exit_.perf_s - entry.perf_s,
        "cpu_user_s": exit_.cpu_user_s - entry.cpu_user_s,
        "cpu_system_s": exit_.cpu_system_s - entry.cpu_system_s,
        "rss_entry_mb": entry.maxrss_mb,
        "peak_rss_mb": exit_.maxrss_mb,
        "read_blocks": exit_.inblocks - entry.inblocks,
        "write_blocks": exit_.oublocks - entry.oublocks,
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
    }


# Per-process annotation stash. A task wrapper (e.g. a transpiled tasks.py)
# records fields the core function cannot know — import_s, the declared
# resource request, the memory mode — and the next DIAGNOSTIC emission merges
# and clears them. Safe per-process: Ray workers execute one task at a time.
_annotations: dict[str, Any] = {}


def annotate_diagnostics(**fields: Any) -> None:
    """Stash fields to merge into the next DIAGNOSTIC event's payload."""
    _annotations.update(fields)


def consume_diagnostic_annotations() -> dict[str, Any]:
    """Return and clear the stashed annotations."""
    global _annotations
    got = _annotations
    _annotations = {}
    return got


def clear_diagnostic_annotations() -> None:
    """Drop any stashed annotations (e.g. between tests or tasks)."""
    _annotations.clear()
