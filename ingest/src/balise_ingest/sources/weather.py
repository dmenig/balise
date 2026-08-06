"""Open-Meteo wind + wave, one call pair per harbour, cached 1 h in the DB (docs/03 §E)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import httpx
from balise_api.config import get_settings

TIMEOUT = 30.0
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WeatherRow:
    harbour_id: int
    at: datetime
    wind_kt: Decimal | None
    gust_kt: Decimal | None
    wind_dir_deg: int | None
    wave_m: Decimal | None


def _decimal(value: object) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _parse_time(raw: str) -> datetime:
    return datetime.fromisoformat(raw).replace(tzinfo=UTC)


def fetch_harbour(
    client: httpx.Client, harbour_id: int, lon: float, lat: float, days: int = 3
) -> list[WeatherRow]:
    settings = get_settings()
    wind = client.get(
        settings.open_meteo_forecast_url,
        params={
            "latitude": lat,
            "longitude": lon,
            "hourly": "wind_speed_10m,wind_gusts_10m,wind_direction_10m",
            "wind_speed_unit": "kn",
            "forecast_days": days,
            "timezone": "UTC",
        },
        timeout=TIMEOUT,
    )
    wind.raise_for_status()
    marine = client.get(
        settings.open_meteo_url,
        params={
            "latitude": lat,
            "longitude": lon,
            "hourly": "wave_height",
            "forecast_days": days,
            "timezone": "UTC",
        },
        timeout=TIMEOUT,
    )
    wave_by_time: dict[str, object] = {}
    if marine.status_code == 200:
        marine_hourly = marine.json()["hourly"]
        wave_by_time = dict(zip(marine_hourly["time"], marine_hourly["wave_height"], strict=False))
    else:
        logger.info("marine API unavailable for harbour %s (inland?)", harbour_id)

    hourly = wind.json()["hourly"]
    rows: list[WeatherRow] = []
    for index, stamp in enumerate(hourly["time"]):
        direction = hourly["wind_direction_10m"][index]
        rows.append(
            WeatherRow(
                harbour_id=harbour_id,
                at=_parse_time(stamp),
                wind_kt=_decimal(hourly["wind_speed_10m"][index]),
                gust_kt=_decimal(hourly["wind_gusts_10m"][index]),
                wind_dir_deg=int(direction) if direction is not None else None,
                wave_m=_decimal(wave_by_time.get(stamp)),
            )
        )
    return rows
