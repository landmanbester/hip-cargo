"""Tests for the monitoring configuration module."""

from pathlib import Path

from hip_cargo.monitoring.config import MonitorSettings


def test_defaults():
    """MonitorSettings defaults are correct without any env vars or .env file."""
    settings = MonitorSettings(_env_file=None)
    assert settings.port == 8321
    assert settings.host == "0.0.0.0"
    assert settings.auth_token is None
    assert settings.ray_address is None
    assert settings.ray_dashboard_url == "http://localhost:8265"
    assert settings.aggregator_name == "progress_aggregator"
    assert settings.max_events_per_job == 1000
    assert settings.websocket_poll_interval == 0.5


def test_env_var_override(monkeypatch):
    """Environment variables with HIPCARGO_ prefix override defaults."""
    monkeypatch.setenv("HIPCARGO_PORT", "9999")
    monkeypatch.setenv("HIPCARGO_AUTH_TOKEN", "secret")
    settings = MonitorSettings(_env_file=None)
    assert settings.port == 9999
    assert settings.auth_token == "secret"


def test_env_prefix(monkeypatch):
    """Unprefixed env vars do NOT affect settings."""
    monkeypatch.setenv("PORT", "1234")
    monkeypatch.delenv("HIPCARGO_PORT", raising=False)
    settings = MonitorSettings(_env_file=None)
    assert settings.port == 8321  # default, not 1234


def test_dotenv_file(tmp_path: Path):
    """Settings are read from a .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text("HIPCARGO_PORT=7777\nHIPCARGO_AUTH_TOKEN=fromfile\n")
    settings = MonitorSettings(_env_file=str(env_file))
    assert settings.port == 7777
    assert settings.auth_token == "fromfile"
