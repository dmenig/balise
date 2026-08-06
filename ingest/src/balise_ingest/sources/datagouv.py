"""data.gouv.fr fetch (docs/03 §C). ZMEL datasets are departmental and heterogeneous — the
resource URL is resolved through the data.gouv API rather than hard-coded, because these
resources are re-uploaded regularly."""

from __future__ import annotations

import logging

import httpx

from balise_ingest.records import RawFeature, SourceRecord

API = "https://www.data.gouv.fr/api/1/datasets"
TIMEOUT = 120.0
_GEO_FORMATS = ("geojson", "json")
logger = logging.getLogger(__name__)


class ResourceNotFound(RuntimeError):
    """Fail hard: a silently skipped département is a silently missing mooring field."""


def source_for(dept: str) -> SourceRecord:
    return SourceRecord(
        id=f"zmel.{dept}",
        kind="import",
        licence="etalab-2.0",
        attribution=f"ZMEL {dept} — DDTM/DREAL via data.gouv.fr (Licence Ouverte Etalab 2.0)",
        url=f"{API}/",
    )


def resolve_geojson_url(dataset_slug: str) -> str:
    response = httpx.get(f"{API}/{dataset_slug}/", timeout=TIMEOUT, follow_redirects=True)
    if response.status_code == 404:
        raise ResourceNotFound(f"dataset data.gouv introuvable: {dataset_slug}")
    response.raise_for_status()
    resources = response.json().get("resources", [])
    for resource in resources:
        if str(resource.get("format", "")).lower() in _GEO_FORMATS:
            return str(resource["url"])
    raise ResourceNotFound(f"aucune ressource GeoJSON dans {dataset_slug}")


def fetch_geojson(url: str, layer: str) -> list[RawFeature]:
    response = httpx.get(url, timeout=TIMEOUT, follow_redirects=True)
    response.raise_for_status()
    payload = response.json()
    features = payload.get("features", payload if isinstance(payload, list) else [])
    out: list[RawFeature] = []
    for index, feature in enumerate(features):
        properties = feature.get("properties") or {}
        identity = (
            feature.get("id")
            or properties.get("id")
            or properties.get("gid")
            or properties.get("objectid")
            or f"{layer}.{index}"
        )
        out.append(
            RawFeature(
                external_id=str(identity),
                layer=layer,
                geometry=feature.get("geometry"),
                properties=properties,
            )
        )
    logger.info("data.gouv %s: %d features", layer, len(out))
    return out
