"""Core implementation for the `hip-cargo monitor` command.

This module is the target of the monitor cab's ``command:`` entry
(``hip_cargo.core.monitor.monitor``), so it must be importable in a
lightweight install; the monitoring extra (Python 3.11+) is imported lazily
inside the function.
"""


def monitor(
    port: int = 8321,
    host: str = "0.0.0.0",
    ray_address: str | None = None,
    ray_dashboard_url: str = "http://localhost:8265",
    auth_token: str | None = None,
) -> None:
    """Launch the hip-cargo monitoring dashboard.

    Args:
        port: Port to serve the dashboard on.
        host: Host to bind to.
        ray_address: Ray cluster address. Defaults to auto-detect.
        ray_dashboard_url: URL of the Ray Dashboard.
        auth_token: Bearer token for API authentication.
    """
    import uvicorn

    from hip_cargo.monitoring.config import MonitorSettings
    from hip_cargo.monitoring.server import create_app

    settings = MonitorSettings(
        host=host,
        port=port,
        ray_address=ray_address,
        ray_dashboard_url=ray_dashboard_url,
        auth_token=auth_token,
    )
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
