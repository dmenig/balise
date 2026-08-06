from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from balise_api import attribution
from balise_api.schemas.spots import (
    TideExtreme,
    TideSummary,
    WeatherPoint,
    WeatherSummary,
)

#: SHOM charted depths and SPM tide heights share the same vertical datum (zéro hydrographique),
#: so the offset is zero for our sources. Kept explicit because it is the term people get wrong.
CHART_DATUM_OFFSET_M = 0.0

_EXTREMES_SQL = """
SELECT at, height_m, kind, coefficient
FROM tide_prediction
WHERE harbour_id = :harbour_id AND kind = :kind AND at >= :now
ORDER BY at
LIMIT 1
"""

_RANGE_SQL = """
SELECT at, height_m, kind, coefficient
FROM tide_prediction
WHERE harbour_id = :harbour_id AND at >= :from_at AND at <= :to_at
ORDER BY at
"""


def _extreme(row: object) -> TideExtreme:
    return TideExtreme(
        at=row.at,  # type: ignore[attr-defined]
        height_m=float(row.height_m),  # type: ignore[attr-defined]
        kind=str(row.kind),  # type: ignore[attr-defined]
        coefficient=row.coefficient,  # type: ignore[attr-defined]
    )


async def tide_summary(
    session: AsyncSession, harbour_id: int, now: datetime, charted_depth_m: float | None
) -> TideSummary | None:
    high = (
        await session.execute(
            text(_EXTREMES_SQL), {"harbour_id": harbour_id, "kind": "HW", "now": now}
        )
    ).one_or_none()
    low = (
        await session.execute(
            text(_EXTREMES_SQL), {"harbour_id": harbour_id, "kind": "LW", "now": now}
        )
    ).one_or_none()
    if high is None and low is None:
        return None
    depth_at_low = None
    if low is not None and charted_depth_m is not None:
        depth_at_low = round(charted_depth_m + float(low.height_m) - CHART_DATUM_OFFSET_M, 1)
    return TideSummary(
        harbour_id=f"harbour_{harbour_id}",
        next_high_water=_extreme(high) if high is not None else None,
        next_low_water=_extreme(low) if low is not None else None,
        depth_at_next_low_water_m=depth_at_low,
        note=attribution.DEPTH_WARNING,
        attribution=[attribution.SHOM_TIDES],
    )


async def tide_range(
    session: AsyncSession, harbour_id: int, from_at: datetime, to_at: datetime
) -> list[TideExtreme]:
    rows = (
        await session.execute(
            text(_RANGE_SQL), {"harbour_id": harbour_id, "from_at": from_at, "to_at": to_at}
        )
    ).all()
    return [
        TideExtreme(
            at=row.at,
            height_m=float(row.height_m),
            kind=str(row.kind) if row.kind else "curve",
            coefficient=row.coefficient,
        )
        for row in rows
    ]


_WEATHER_SQL = """
SELECT at, wind_kt, gust_kt, wind_dir_deg, wave_m
FROM weather_forecast
WHERE harbour_id = :harbour_id AND at >= :now AND at <= :until
ORDER BY at
"""


async def weather_summary(
    session: AsyncSession, harbour_id: int, now: datetime, hours: int = 48
) -> WeatherSummary | None:
    rows = (
        await session.execute(
            text(_WEATHER_SQL),
            {"harbour_id": harbour_id, "now": now, "until": now + timedelta(hours=hours)},
        )
    ).all()
    if not rows:
        return None
    return WeatherSummary(
        harbour_id=f"harbour_{harbour_id}",
        points=[
            WeatherPoint(
                at=row.at,
                wind_kt=float(row.wind_kt) if row.wind_kt is not None else None,
                gust_kt=float(row.gust_kt) if row.gust_kt is not None else None,
                wind_dir_deg=row.wind_dir_deg,
                wave_m=float(row.wave_m) if row.wave_m is not None else None,
            )
            for row in rows
        ],
        attribution=[attribution.OPEN_METEO],
    )


async def nearest_harbour_id(session: AsyncSession, lon: float, lat: float) -> int | None:
    row = await session.execute(
        text(
            """
            SELECT id FROM harbour
            ORDER BY geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
            LIMIT 1
            """
        ),
        {"lon": lon, "lat": lat},
    )
    value = row.scalar_one_or_none()
    return int(value) if value is not None else None
