"""Environment cache refresh jobs (docs/10 schedule). Called by the CLI and the status worker."""

from __future__ import annotations

import logging

import httpx
from balise_api.config import get_settings
from balise_api.db import sync_session
from sqlalchemy import text
from sqlalchemy.orm import Session

from balise_ingest.sources import tides, weather

logger = logging.getLogger(__name__)

_TIDE_UPSERT = text(
    """
    INSERT INTO tide_prediction (harbour_id, at, height_m, kind, coefficient)
    VALUES (:harbour_id, :at, :height_m, :kind, :coefficient)
    ON CONFLICT (harbour_id, at) DO UPDATE SET height_m = EXCLUDED.height_m,
        kind = EXCLUDED.kind, coefficient = EXCLUDED.coefficient, fetched_at = now()
    """
)

_WEATHER_UPSERT = text(
    """
    INSERT INTO weather_forecast (harbour_id, at, wind_kt, gust_kt, wind_dir_deg, wave_m)
    VALUES (:harbour_id, :at, :wind_kt, :gust_kt, :wind_dir_deg, :wave_m)
    ON CONFLICT (harbour_id, at) DO UPDATE SET wind_kt = EXCLUDED.wind_kt,
        gust_kt = EXCLUDED.gust_kt, wind_dir_deg = EXCLUDED.wind_dir_deg,
        wave_m = EXCLUDED.wave_m, fetched_at = now()
    """
)


def refresh_tides(days: int = 7, session: Session | None = None) -> dict[str, object]:
    if not get_settings().tides_enabled:
        return {"stage": "tides", "skipped": "SHOM_TIDE_API_KEY absent", "rows": 0}
    if session is None:
        with sync_session() as owned:
            result = refresh_tides(days, owned)
            owned.commit()
            return result
    rows = session.execute(
        text(
            "SELECT id, external_ids ->> 'shom_spm' AS spm FROM harbour "
            "WHERE external_ids ? 'shom_spm' ORDER BY id"
        )
    ).all()
    written = 0
    with httpx.Client() as client:
        for row in rows:
            for prediction in tides.fetch_harbour(client, int(row.id), str(row.spm), days):
                session.execute(_TIDE_UPSERT, _tide_params(prediction))
                written += 1
    return {"stage": "tides", "harbours": len(rows), "rows": written}


def _tide_params(prediction: tides.TideRow) -> dict[str, object]:
    return {
        "harbour_id": prediction.harbour_id,
        "at": prediction.at,
        "height_m": prediction.height_m,
        "kind": prediction.kind,
        "coefficient": prediction.coefficient,
    }


def refresh_weather(limit: int = 200, session: Session | None = None) -> dict[str, object]:
    """One call pair per harbour, hourly. Harbours with the most spots first."""
    if session is None:
        with sync_session() as owned:
            result = refresh_weather(limit, owned)
            owned.commit()
            return result
    rows = session.execute(
        text(
            """
            SELECT h.id, ST_X(h.geom) AS lon, ST_Y(h.geom) AS lat,
                   (SELECT count(*) FROM spot s WHERE s.harbour_id = h.id AND s.active) AS spots
            FROM harbour h
            ORDER BY spots DESC, h.id
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).all()
    written = 0
    with httpx.Client() as client:
        for row in rows:
            for point in weather.fetch_harbour(client, int(row.id), float(row.lon), float(row.lat)):
                session.execute(
                    _WEATHER_UPSERT,
                    {
                        "harbour_id": point.harbour_id,
                        "at": point.at,
                        "wind_kt": point.wind_kt,
                        "gust_kt": point.gust_kt,
                        "wind_dir_deg": point.wind_dir_deg,
                        "wave_m": point.wave_m,
                    },
                )
                written += 1
    return {"stage": "weather", "harbours": len(rows), "rows": written}
