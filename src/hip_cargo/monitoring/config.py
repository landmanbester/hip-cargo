"""Configuration for the hip-cargo monitoring server.

Uses pydantic-settings to read from environment variables (HIPCARGO_ prefix)
and optionally from a .env file. No Ray dependency here — this is pure config.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class MonitorSettings(BaseSettings):
    """Configuration for the hip-cargo monitoring server.

    All settings can be provided via environment variables with the
    HIPCARGO_ prefix, or via a .env file in the working directory.

    Examples:
        HIPCARGO_AUTH_TOKEN=secret123
        HIPCARGO_RAY_DASHBOARD_URL=http://head-node:8265
        HIPCARGO_PORT=8321
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="HIPCARGO_",
        case_sensitive=False,
        extra="ignore",
    )

    # Authentication
    auth_token: str | None = None

    # Server
    host: str = "0.0.0.0"
    port: int = 8321

    # Ray
    ray_address: str | None = None
    ray_dashboard_url: str = "http://localhost:8265"
    aggregator_name: str = "progress_aggregator"

    # Monitoring behaviour
    max_events_per_job: int = 1000
    websocket_poll_interval: float = 0.5

    # Discovery
    recipes_dir: str | None = None  # overrides auto-discovery
    cli_module: str | None = None  # e.g. "pfb.cli" for pfb-imaging
