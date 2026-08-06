"""`balise-env-worker` — the v1 scheduler: tides and weather (docs/07).

It exists in v1 because tides and weather need a scheduler anyway, which is why adding the v2
status-worker later is a new job in an existing process, not a new deployment unit.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

import typer
from apscheduler.schedulers.blocking import BlockingScheduler
from balise_ingest.jobs import refresh_tides, refresh_weather

app = typer.Typer(add_completion=False, help="Worker d'environnement Balise (marées, météo)")
logger = logging.getLogger("balise_workers.env")


@app.command()
def once(weather_limit: int = 200, tide_days: int = 7) -> None:
    """One pass of each job — what CI and the smoke tests call."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    report = {
        "weather": refresh_weather(weather_limit),
        "tides": refresh_tides(tide_days),
    }
    typer.echo(json.dumps(report, ensure_ascii=False, default=str))


@app.command()
def run(weather_minutes: int = 60, tide_hours: int = 24, weather_limit: int = 200) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    scheduler = BlockingScheduler(timezone="UTC")

    def _weather() -> None:
        logger.info("weather: %s", refresh_weather(weather_limit))

    def _tides() -> None:
        logger.info("tides: %s", refresh_tides())

    scheduler.add_job(
        _weather,
        "interval",
        minutes=weather_minutes,
        next_run_time=datetime.now(UTC) + timedelta(seconds=2),
    )
    scheduler.add_job(_tides, "interval", hours=tide_hours)
    logger.info("env worker démarré (marées, météo)")
    scheduler.start()


if __name__ == "__main__":  # pragma: no cover
    app()
