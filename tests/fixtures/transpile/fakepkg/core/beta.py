"""Consumer step with an in-memory sibling."""


def beta(input_data, output, memory_mode="greedy", factor=2.0):
    """Disk-persisting cab entry point."""
    return {"input": str(input_data), "output": str(output), "factor": factor}


def beta_inmem(dataset, memory_mode, job_id, pipeline_run_id, work_dir, factor=2.0):
    """In-memory sibling: first positional is the upstream dataset."""
    return {"data": [x * factor for x in dataset["data"]], "memory_mode": memory_mode}
