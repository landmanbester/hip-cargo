"""Tests for the per-task diagnostics capture layer."""

import time

import pytest

from hip_cargo.utils.diagnostics import (
    ResourceSnapshot,
    annotate_diagnostics,
    capture_snapshot,
    clear_diagnostic_annotations,
    consume_diagnostic_annotations,
    diagnostics_delta,
)

STDLIB_KEYS = {
    "wall_s",
    "cpu_user_s",
    "cpu_system_s",
    "rss_entry_mb",
    "peak_rss_mb",
    "read_blocks",
    "write_blocks",
    "hostname",
    "pid",
}


@pytest.fixture(autouse=True)
def _clean_annotations():
    clear_diagnostic_annotations()
    yield
    clear_diagnostic_annotations()


def test_capture_snapshot_fields():
    snap = capture_snapshot()
    assert isinstance(snap, ResourceSnapshot)
    assert snap.perf_s > 0
    assert snap.cpu_user_s >= 0
    assert snap.cpu_system_s >= 0
    assert snap.maxrss_mb > 0


def test_delta_key_set_is_stable_contract():
    entry = capture_snapshot()
    delta = diagnostics_delta(entry, capture_snapshot())
    assert set(delta) == STDLIB_KEYS


def test_delta_arithmetic():
    entry = capture_snapshot()
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 0.05:
        sum(range(1000))  # burn a little CPU and wall time
    delta = diagnostics_delta(entry, capture_snapshot())
    assert delta["wall_s"] >= 0.05
    assert delta["cpu_user_s"] >= 0
    # maxrss is monotone: peak can never be below the entry RSS
    assert delta["peak_rss_mb"] >= delta["rss_entry_mb"]
    assert delta["pid"] > 0
    assert isinstance(delta["hostname"], str) and delta["hostname"]


def test_annotations_merge_and_clear_on_consume():
    annotate_diagnostics(import_s=1.5, memory_mode="greedy")
    annotate_diagnostics(requested={"num_cpus": 2})
    got = consume_diagnostic_annotations()
    assert got == {"import_s": 1.5, "memory_mode": "greedy", "requested": {"num_cpus": 2}}
    assert consume_diagnostic_annotations() == {}
