"""Step whose in-memory sibling always fails (failure-path fixture)."""


def omega(input_data, output, factor=1.0):
    """Disk-persisting cab entry point."""
    raise RuntimeError("omega always fails")


def omega_inmem(dataset, memory_mode, job_id, pipeline_run_id, work_dir, factor=1.0):
    """In-memory sibling that always raises."""
    raise RuntimeError("omega always fails")
