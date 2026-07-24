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
import threading
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


class _Sampler:
    """Background RSS sampler backed by psutil (optional enrichment tier)."""

    def __init__(self, interval: float) -> None:
        import psutil

        self._proc = psutil.Process()
        self._interval = interval
        self._stop_event = threading.Event()
        self._peak_rss = self._proc.memory_info().rss
        try:
            self._io_entry = self._proc.io_counters()
        except (AttributeError, NotImplementedError, psutil.AccessDenied):
            self._io_entry = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval):
            try:
                self._peak_rss = max(self._peak_rss, self._proc.memory_info().rss)
            except Exception:
                return

    def stop(self) -> dict[str, Any]:
        """Stop sampling and return the enrichment fields."""
        self._stop_event.set()
        self._thread.join(timeout=self._interval * 4)
        result: dict[str, Any] = {
            "peak_rss_mb": self._peak_rss / (1024.0 * 1024.0),
            "sampled": True,
        }
        if self._io_entry is not None:
            try:
                io_exit = self._proc.io_counters()
                result["read_mb"] = (io_exit.read_bytes - self._io_entry.read_bytes) / (1024.0 * 1024.0)
                result["write_mb"] = (io_exit.write_bytes - self._io_entry.write_bytes) / (1024.0 * 1024.0)
            except Exception:
                pass
        return result


def start_sampler(interval: float = 0.5) -> "_Sampler | None":
    """Start the psutil enrichment sampler, or return None when unavailable."""
    try:
        import psutil  # noqa: F401
    except ImportError:
        return None
    return _Sampler(interval)
