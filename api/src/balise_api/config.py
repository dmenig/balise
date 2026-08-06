from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "postgresql+psycopg://balise:balise@localhost:5432/balise"
    redis_url: str = "redis://localhost:6379/0"

    api_base_url: str = "http://localhost:8000"
    # NoDecode: the value is a comma-separated list in `.env`, not JSON.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )
    secret_key: str = "change-me-32-bytes-minimum-secret-key"
    device_token_salt: str = "change-me"
    env: Literal["local", "test", "staging", "prod"] = "local"
    log_level: str = "INFO"

    shom_wfs_url: str = "https://services.data.shom.fr/INSPIRE/wfs"
    shom_tide_api_url: str = "https://services.data.shom.fr/hdm/spm/ports"
    shom_tide_api_key: str = ""
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    overpass_user_agent: str = "balise.fr (contact@balise.fr)"
    geofabrik_url: str = "https://download.geofabrik.de/europe/france-latest.osm.pbf"
    open_meteo_url: str = "https://marine-api.open-meteo.com/v1/marine"
    open_meteo_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    aisstream_url: str = "wss://stream.aisstream.io/v0/stream"
    aisstream_api_key: str = ""

    # The availability switch is deliberately *not* a Settings field: it is read once, in
    # `main.py`, so it cannot spread (docs/11). These two are read only by the 🔌 v2 workers.
    feature_ais: bool = False
    feature_websocket: bool = False

    s3_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "balise-media"
    s3_access_key: str = "minio"
    s3_secret_key: str = "minio123"

    raw_dir: Path = Path("raw")

    rate_limit_anonymous_per_min: int = 60
    # Tiles get their own, far larger bucket (docs/08): one "télécharger cette zone" is legitimately
    # hundreds of tile requests, and refusing them would break the offline pack the sailor came for.
    rate_limit_tiles_per_min: int = 1200
    rate_limit_feed_per_min: int = 600

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("+asyncpg", "+psycopg")

    @property
    def tides_enabled(self) -> bool:
        return bool(self.shom_tide_api_key)

    @property
    def ais_enabled(self) -> bool:
        return self.feature_ais and bool(self.aisstream_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
