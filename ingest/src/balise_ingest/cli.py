"""`balise-ingest` — one command per stage, all idempotent, all re-runnable from snapshots."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

import typer
from balise_api.config import get_settings
from balise_api.db import sync_session

from balise_ingest import jobs, snapshots, staging
from balise_ingest.adapters.zmel import adapter_for
from balise_ingest.conflate import explain as explain_target
from balise_ingest.load import load_batch
from balise_ingest.normalisers import osm as osm_normaliser
from balise_ingest.normalisers import shom as shom_normaliser
from balise_ingest.records import NormalisedBatch
from balise_ingest.seed import seed as seed_fixture
from balise_ingest.sources import datagouv, osm, shom

app = typer.Typer(
    add_completion=False, help="Ingestion Balise (fetch → normalise → conflate → load)"
)
shom_app = typer.Typer(help="SHOM WFS (balisage, ports, réglementation, marées)")
osm_app = typer.Typer(help="OpenStreetMap / OpenSeaMap")
datagouv_app = typer.Typer(help="data.gouv.fr (ZMEL par département)")
app.add_typer(shom_app, name="shom")
app.add_typer(osm_app, name="osm")
app.add_typer(datagouv_app, name="datagouv")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("balise_ingest")

BboxOption = Annotated[str | None, typer.Option(help="min_lon,min_lat,max_lon,max_lat")]
DryRunOption = Annotated[bool, typer.Option("--dry-run", help="fetch + normalise, pas de load")]
ForceOption = Annotated[bool, typer.Option("--force", help="passe outre la garde de comptage")]
SnapshotOption = Annotated[Path | None, typer.Option("--from-snapshot", help="répertoire raw/…")]


def _report(payload: dict[str, object]) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, default=str))


def _load(batch: NormalisedBatch, force: bool) -> None:
    with sync_session() as session:
        report = load_batch(session, batch, force=force)
        session.commit()
    _report(report.as_dict())


@shom_app.command("balisage")
def shom_balisage(
    bbox: BboxOption = None,
    dry_run: DryRunOption = False,
    force: ForceOption = False,
    from_snapshot: SnapshotOption = None,
) -> None:
    _run_shom("balisage", bbox, dry_run, force, from_snapshot)


@shom_app.command("ports")
def shom_ports(
    bbox: BboxOption = None,
    dry_run: DryRunOption = False,
    force: ForceOption = False,
    from_snapshot: SnapshotOption = None,
) -> None:
    _run_shom("ports", bbox, dry_run, force, from_snapshot)


@shom_app.command("reglementation")
def shom_reglementation(
    bbox: BboxOption = None,
    dry_run: DryRunOption = False,
    force: ForceOption = False,
    from_snapshot: SnapshotOption = None,
) -> None:
    _run_shom("reglementation", bbox, dry_run, force, from_snapshot)


@shom_app.command("spm")
def shom_spm(dry_run: DryRunOption = False, force: ForceOption = False) -> None:
    """Tide reference ports — the join key for the tide API."""
    _run_shom("spm", None, dry_run, force, None)


def _run_shom(
    group: str, bbox: str | None, dry_run: bool, force: bool, from_snapshot: Path | None
) -> None:
    if from_snapshot is not None:
        layers = snapshots.read_dir(from_snapshot)
    else:
        box = shom.Bbox.parse(bbox) if bbox else None
        layers = asyncio.run(shom.fetch_group(group, box))
        for layer, features in layers.items():
            snapshots.write(f"shom-{group}", layer, features)
    batch = shom_normaliser.normalise(group, layers, shom.SOURCES[group])
    if not dry_run:
        with sync_session() as session:
            for features in layers.values():
                staging.write(session, batch.source.id, features)
            session.commit()
    _report({"stage": "normalise", "group": group, **batch.counts()})
    if dry_run:
        return
    _load(batch, force)


@osm_app.command("delta")
def osm_delta(
    bbox: BboxOption = None,
    hours: Annotated[
        int, typer.Option(help="ne prendre que les objets modifiés depuis N heures")
    ] = 0,
    dry_run: DryRunOption = False,
    force: ForceOption = False,
) -> None:
    """Overpass, hourly. Polite by construction: one query, User-Agent with a contact address."""
    box = _overpass_bbox(bbox)
    newer = datetime.now(UTC) - timedelta(hours=hours) if hours else None
    features = osm.fetch_overpass(box, newer)
    snapshots.write("osm", "overpass", features)
    batch = osm_normaliser.normalise(features)
    _report({"stage": "normalise", "source": "osm", **batch.counts()})
    if dry_run:
        return
    with sync_session() as session:
        staging.write(session, "osm", features)
        session.commit()
    _load(batch, force)


@osm_app.command("full")
def osm_full(
    pbf: Annotated[Path | None, typer.Option(help="fichier .osm.pbf déjà téléchargé")] = None,
    from_snapshot: SnapshotOption = None,
    dry_run: DryRunOption = False,
    force: ForceOption = False,
) -> None:
    """Bulk path: Geofabrik extract filtered with osmium (docs/10)."""
    if from_snapshot is not None:
        features = [
            feature
            for layer_features in snapshots.read_dir(from_snapshot).values()
            for feature in layer_features
        ]
    else:
        settings = get_settings()
        target = pbf or (settings.raw_dir / "osm" / "france-latest.osm.pbf")
        if not target.exists():
            typer.echo(f"téléchargement {settings.geofabrik_url} → {target}")
            osm.download_pbf(target)
        features = osm.read_geojsonseq(osm.filter_pbf(target, settings.raw_dir / "osm" / "work"))
        snapshots.write("osm", "pbf", features)
    batch = osm_normaliser.normalise(features)
    _report({"stage": "normalise", "source": "osm-pbf", **batch.counts()})
    if dry_run:
        return
    with sync_session() as session:
        staging.write(session, "osm", features)
        session.commit()
    _load(batch, force)


def _overpass_bbox(bbox: str | None) -> tuple[float, float, float, float]:
    if bbox is None:
        return osm.FRANCE_BBOX
    box = shom.Bbox.parse(bbox)
    return (box.min_lat, box.min_lon, box.max_lat, box.max_lon)


@datagouv_app.command("zmel")
def datagouv_zmel(
    dept: Annotated[str, typer.Option("--dept", help="code département, ex. 56")],
    url: Annotated[str | None, typer.Option(help="URL GeoJSON explicite")] = None,
    dry_run: DryRunOption = False,
    force: ForceOption = False,
) -> None:
    """ZMEL: polygons with a buoy count, or one point per buoy — both are handled (docs/10)."""
    adapter = adapter_for(dept)
    resolved = url or datagouv.resolve_geojson_url(adapter.dataset_slug)
    features = datagouv.fetch_geojson(resolved, f"zmel-{dept}")
    snapshots.write(f"zmel-{dept}", "zmel", features)
    fields = [record for feature in features for record in adapter.to_fields(feature)]
    spots = [record for feature in features for record in adapter.to_spots(feature)]
    batch = NormalisedBatch(
        source=datagouv.source_for(dept), fields=tuple(fields), spots=tuple(spots)
    )
    _report({"stage": "normalise", "source": batch.source.id, **batch.counts()})
    if dry_run:
        return
    with sync_session() as session:
        staging.write(session, batch.source.id, features)
        session.commit()
    _load(batch, force)


@app.command("tides")
def ingest_tides(
    days: Annotated[int, typer.Option(help="jours de prédiction à précalculer")] = 7,
) -> None:
    """Precompute predictions so the frontend never calls SHOM and offline works (docs/03 §D)."""
    _report(jobs.refresh_tides(days))


@app.command("weather")
def ingest_weather(
    limit: Annotated[int, typer.Option(help="nombre de ports à rafraîchir")] = 200,
) -> None:
    _report(jobs.refresh_weather(limit))


@app.command("conflate")
def conflate_command(
    explain: Annotated[str | None, typer.Option("--explain", help="ex. spot_18421")] = None,
) -> None:
    """Conflation is applied during `load`; `--explain` shows why one object looks like it does."""
    if explain is None:
        typer.echo(
            "La conflation tourne dans le load. Utilisez --explain spot_<id> pour la tracer."
        )
        raise typer.Exit(0)
    table, _, raw_id = explain.partition("_")
    mapping = {"spot": "spot", "harbour": "harbour", "navaid": "nav_aid", "field": "field"}
    with sync_session() as session:
        rows = explain_target(session, mapping[table], int(raw_id))
    for row in rows:
        typer.echo(json.dumps(row, ensure_ascii=False, default=str))


@app.command("seed")
def seed_command(
    fixture: Annotated[Path | None, typer.Option(help="GeoJSON de fixtures")] = None,
    with_demo_feed: Annotated[
        bool, typer.Option(help="🔌 v2 : ajoute un flux MBFS de démonstration et son jeton")
    ] = False,
) -> None:
    """Load the checked-in Morbihan fixture: a working map with no network access (docs/11)."""
    _report(seed_fixture(fixture, with_demo_feed=with_demo_feed))


@app.command("prune-snapshots")
def prune_snapshots(source: Annotated[str, typer.Argument()], keep_days: int = 90) -> None:
    removed = snapshots.prune(source, keep_days)
    _report({"stage": "prune", "source": source, "removed": [str(path) for path in removed]})


if __name__ == "__main__":  # pragma: no cover
    app()
