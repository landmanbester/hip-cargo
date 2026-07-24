"""Producer step with an in-memory sibling."""


def alpha(output, memory_mode="greedy", n_items=3):
    """Disk-persisting cab entry point."""
    return {"output": str(output), "n_items": n_items, "memory_mode": memory_mode}


def alpha_inmem(memory_mode, job_id, pipeline_run_id, work_dir, n_items=3):
    """In-memory sibling following the v1 transpile contract."""
    return {"data": list(range(n_items)), "memory_mode": memory_mode}
