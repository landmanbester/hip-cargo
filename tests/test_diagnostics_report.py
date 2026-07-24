"""Tests for the diagnostics report join (pure function, no Ray)."""

from hip_cargo.monitoring.diagnostics_report import build_diagnostics_report


def _ev(event_type, worker, ts, extra=None):
    return {
        "job_id": "j",
        "worker_name": worker,
        "event_type": event_type,
        "timestamp": ts,
        "extra": extra or {},
    }


def _diag(worker, ts, payload):
    e = _ev("diagnostic", worker, ts)
    e["extra"]["diagnostics"] = payload
    return e


PAYLOAD = {
    "wall_s": 10.0,
    "cpu_user_s": 36.0,
    "cpu_system_s": 4.0,
    "rss_entry_mb": 100.0,
    "peak_rss_mb": 900.0,
    "read_blocks": 0,
    "write_blocks": 8,
    "hostname": "n1",
    "pid": 42,
    "requested": {"num_cpus": 4},
}


def test_report_joins_queue_lag_and_utilisation():
    events = [
        _ev("pipeline_started", "pipe", 100.0, {"pipeline_run_id": "run1"}),
        _ev("step_started", "init", 100.5),
        _ev("started", "init", 101.5),
        _diag("init", 111.5, dict(PAYLOAD)),
        # a worker-level completed must not be mistaken for the terminal event
        _ev("completed", "init", 111.9),
        _ev("step_completed", "init", 112.0),
        _ev("completed", "pipe", 112.5),
    ]
    report = build_diagnostics_report("j", events)
    assert report["job_id"] == "j"
    assert report["pipeline_run_id"] == "run1"
    assert len(report["tasks"]) == 1
    task = report["tasks"][0]
    assert task["step"] == "init"
    assert task["queue_lag_s"] == 1.0  # started 101.5 - step_started 100.5
    assert task["cpu_utilisation"] == (36.0 + 4.0) / (10.0 * 4)
    assert task["peak_rss_mb"] == 900.0
    assert report["pipeline"]["wall_s"] == 12.5  # terminal completed - pipeline_started
    assert report["pipeline"]["cpu_core_seconds"] == 40.0


def test_report_nulls_when_no_request_or_timeline():
    events = [_diag("solo", 5.0, {k: v for k, v in PAYLOAD.items() if k != "requested"})]
    report = build_diagnostics_report("j", events)
    task = report["tasks"][0]
    assert task["queue_lag_s"] is None
    assert task["cpu_utilisation"] is None
    assert report["pipeline"]["wall_s"] is None
    assert report["pipeline"]["cpu_core_seconds"] == 40.0


def test_report_empty_when_no_diagnostics():
    events = [_ev("started", "w", 1.0)]
    report = build_diagnostics_report("j", events)
    assert report["tasks"] == []
