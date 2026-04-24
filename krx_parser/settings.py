"""Runtime configuration via pydantic-settings.

Environment variables (all prefixed `KRX_`):

- `KRX_DATABASE_URL` — SQLAlchemy DSN. Default
  `sqlite:///data/krx.db` (relative to the process CWD).
- `KRX_SCHEMA_DIR` — override the YAML schema directory.
- `KRX_LOG_LEVEL` — Python logging level name. Default `INFO`.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KRX_", env_file=None)

    database_url: str = "sqlite:///data/krx.db"
    schema_dir: Path | None = None
    log_level: str = "INFO"


def get_settings() -> Settings:
    return Settings()
