"""Consumer step WITHOUT an in-memory sibling (disk-fallback path)."""


def delta(input_data, output, scale=1):
    """Disk-persisting cab entry point; no _inmem sibling exists."""
    return {"input": str(input_data), "output": str(output), "scale": scale}
