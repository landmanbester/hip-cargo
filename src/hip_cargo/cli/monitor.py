"""CLI command to launch the hip-cargo monitoring dashboard."""

from typing import Annotated

import typer

from hip_cargo.utils.decorators import stimela_cab


@stimela_cab(
    name="monitor",
    info="Launch the monitoring dashboard for the current project.",
)
def monitor(
    port: Annotated[
        int,
        typer.Option(help="Port to serve the dashboard on."),
    ] = 8321,
    host: Annotated[
        str,
        typer.Option(help="Host to bind to."),
    ] = "0.0.0.0",
    ray_address: Annotated[
        str | None,
        typer.Option(help="Ray cluster address. Defaults to auto-detect."),
    ] = None,
    ray_dashboard_url: Annotated[
        str,
        typer.Option(help="URL of the Ray Dashboard."),
    ] = "http://localhost:8265",
    auth_token: Annotated[
        str | None,
        typer.Option(help="Bearer token for API authentication.", envvar="HIPCARGO_AUTH_TOKEN"),
    ] = None,
):
    """Launch the hip-cargo monitoring dashboard."""
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

    app = create_app(settings)
    uvicorn.run(app, host=settings.host, port=settings.port)
