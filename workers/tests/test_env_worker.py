"""The v1 worker: tides and weather refresh (docs/07).

It exists in v1 because the environment cache needs a scheduler anyway — which is what makes the v2
status-worker a new job in an existing process rather than a new deployment unit.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from balise_ingest import jobs
from balise_ingest.sources import tides, weather
from sqlalchemy import text
from sqlalchemy.orm import Session

SEED = """
INSERT INTO source (id, kind, licence, attribution)
VALUES ('osm', 'import', 'odbl-1.0', '© OSM (ODbL)');

INSERT INTO harbour (id, slug, name, geom, source_id, external_ids, attrs_provenance)
VALUES (1, 'port-test', 'Port de Test', ST_SetSRID(ST_MakePoint(-2.902, 47.541), 4326), 'osm',
        '{"osm":"way/1"}', '{}');
"""


@pytest.fixture(autouse=True)
def seeded(session: Session) -> None:
    session.execute(text(SEED))
    session.commit()


def test_weather_refresh_caches_hourly_points(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    rows = [
        weather.WeatherRow(
            harbour_id=1,
            at=now + timedelta(hours=hour),
            wind_kt=Decimal("12.4"),
            gust_kt=Decimal("18.0"),
            wind_dir_deg=200,
            wave_m=Decimal("1.20"),
        )
        for hour in range(3)
    ]
    monkeypatch.setattr(weather, "fetch_harbour", lambda *args, **kwargs: rows)

    report = jobs.refresh_weather(10, session)
    session.commit()

    assert report == {"stage": "weather", "harbours": 1, "rows": 3}
    stored = session.execute(
        text("SELECT wind_kt, gust_kt, wind_dir_deg, wave_m FROM weather_forecast ORDER BY at")
    ).all()
    assert stored[0] == (Decimal("12.4"), Decimal("18.0"), 200, Decimal("1.20"))


def test_weather_refresh_is_idempotent(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    row = weather.WeatherRow(
        harbour_id=1, at=now, wind_kt=Decimal("10.0"), gust_kt=None, wind_dir_deg=0, wave_m=None
    )
    monkeypatch.setattr(weather, "fetch_harbour", lambda *args, **kwargs: [row])
    jobs.refresh_weather(10, session)
    jobs.refresh_weather(10, session)
    session.commit()
    count = session.execute(text("SELECT count(*) FROM weather_forecast")).scalar_one()
    assert count == 1


def test_tides_are_skipped_without_a_key(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """The app must boot and serve the referential with no third-party credentials (docs/11)."""
    from balise_api.config import get_settings

    monkeypatch.setattr(get_settings(), "shom_tide_api_key", "")
    report = jobs.refresh_tides(7, session)
    assert report["rows"] == 0
    assert "SHOM_TIDE_API_KEY" in str(report["skipped"])


def test_tides_only_query_harbours_with_a_spm_key(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from balise_api.config import get_settings
    from balise_ingest.sources import tides

    monkeypatch.setattr(get_settings(), "shom_tide_api_key", "test-key")
    session.execute(
        text(
            'UPDATE harbour SET external_ids = external_ids || \'{"shom_spm": "PORT_TEST"}\'::jsonb'
        )
    )
    session.commit()

    asked: list[str] = []

    def fake_fetch(
        client: httpx.Client, harbour_id: int, spm_key: str, days: int = 7
    ) -> list[tides.TideRow]:
        asked.append(spm_key)
        return [
            tides.TideRow(
                harbour_id=harbour_id,
                at=datetime.now(UTC) + timedelta(hours=3),
                height_m=Decimal("5.20"),
                kind="HW",
                coefficient=78,
            )
        ]

    monkeypatch.setattr(tides, "fetch_harbour", fake_fetch)
    report = jobs.refresh_tides(7, session)
    session.commit()

    assert asked == ["PORT_TEST"]
    assert report == {"stage": "tides", "harbours": 1, "rows": 1}
    stored = session.execute(text("SELECT height_m, kind, coefficient FROM tide_prediction")).one()
    assert stored == (Decimal("5.20"), "HW", 78)
