"""SHOM WFS fetch (docs/03 §A, docs/10). No API key, GeoJSON out, Etalab 2.0."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from balise_api.config import get_settings

from balise_ingest.records import RawFeature, SourceRecord

PAGE = 1000
TIMEOUT = 120.0
ATTEMPTS = 3

BALISAGE_LAYERS = (
    "bcnlat",
    "bcncar",
    "bcnisd",
    "bcnspp",
    "boylat",
    "boycar",
    "boyisd",
    "boysaw",
    "boyspp",
    "boyinb",
    "lights",
    "topmar",
    "daymar",
    "fogsig",
    "lndmrk",
    "morfac",
)
PORT_LAYERS = ("hrbfac_point", "hrbfac_polygon", "berths_point", "smcfac_point")
REGLEMENTATION_LAYERS = ("achare_point", "achare_polygon")
SPM_LAYERS = ("liste_ports_spm_h2m",)

_NAMESPACES = {
    **dict.fromkeys(BALISAGE_LAYERS, "BALISAGE_BDD_WFS"),
    **dict.fromkeys(PORT_LAYERS, "INFORMATIONS_PORTUAIRES_BDD_WFS"),
    **dict.fromkeys(REGLEMENTATION_LAYERS, "REGLEMENTATION_NAVIGATION_BDD_WFS"),
    **dict.fromkeys(SPM_LAYERS, "SPM_PORTS_WFS"),
}

GROUPS: dict[str, tuple[str, ...]] = {
    "balisage": BALISAGE_LAYERS,
    "ports": PORT_LAYERS,
    "reglementation": REGLEMENTATION_LAYERS,
    "spm": SPM_LAYERS,
}

SOURCES: dict[str, SourceRecord] = {
    "balisage": SourceRecord(
        id="shom.balisage",
        kind="import",
        licence="etalab-2.0",
        attribution="Shom, 2026 (Licence Ouverte Etalab 2.0)",
        url="https://diffusion.shom.fr/donnees/base-de-donnees-maritimes-et-littorales/balisage_maritime.html",
    ),
    "ports": SourceRecord(
        id="shom.ports",
        kind="import",
        licence="etalab-2.0",
        attribution="Shom, 2026 (Licence Ouverte Etalab 2.0)",
        url="https://services.data.shom.fr/INSPIRE/wfs",
    ),
    "reglementation": SourceRecord(
        id="shom.reglementation",
        kind="import",
        licence="etalab-2.0",
        attribution="Shom, 2026 (Licence Ouverte Etalab 2.0)",
        url="https://services.data.shom.fr/INSPIRE/wfs",
    ),
    "spm": SourceRecord(
        id="shom.spm",
        kind="import",
        licence="etalab-2.0",
        attribution="Shom, 2026 (Licence Ouverte Etalab 2.0)",
        url="https://diffusion.shom.fr/api-shom.html",
    ),
}

logger = logging.getLogger(__name__)


class CountMismatch(RuntimeError):
    """`numberMatched` and the number of features we collected disagree — never load that."""


@dataclass(frozen=True, slots=True)
class Bbox:
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    @classmethod
    def parse(cls, raw: str) -> Bbox:
        values = [float(part) for part in raw.split(",")]
        if len(values) != 4:
            raise ValueError("bbox attend min_lon,min_lat,max_lon,max_lat")
        return cls(*values)

    def contains(self, geometry: dict[str, Any] | None) -> bool:
        if geometry is None:
            return False
        lon, lat = _representative_point(geometry)
        return self.min_lon <= lon <= self.max_lon and self.min_lat <= lat <= self.max_lat


def _representative_point(geometry: dict[str, Any]) -> tuple[float, float]:
    coordinates: Any = geometry["coordinates"]
    while isinstance(coordinates, list) and coordinates and isinstance(coordinates[0], list):
        coordinates = coordinates[0]
    return float(coordinates[0]), float(coordinates[1])


def type_name(layer: str) -> str:
    namespace = _NAMESPACES.get(layer)
    if namespace is None:
        raise KeyError(f"couche SHOM inconnue: {layer}")
    return f"{namespace}:{layer}"


async def fetch_layer(client: httpx.AsyncClient, layer: str) -> list[RawFeature]:
    features: list[RawFeature] = []
    start = 0
    matched: int | None = None
    while True:
        page = await _get_page(client, layer, start)
        page_matched = page.get("numberMatched")
        matched = int(page_matched) if page_matched is not None else matched
        for index, feature in enumerate(page["features"]):
            properties = feature.get("properties") or {}
            external_id = str(
                properties.get("inspireid") or feature.get("id") or f"{layer}.{start + index}"
            )
            features.append(
                RawFeature(
                    external_id=external_id,
                    layer=layer,
                    geometry=feature.get("geometry"),
                    properties=properties,
                )
            )
        returned = int(page.get("numberReturned", len(page["features"])))
        if returned < PAGE:
            break
        start += PAGE
    if matched is not None and matched != len(features):
        raise CountMismatch(f"{layer}: numberMatched={matched}, collecté={len(features)}")
    logger.info("shom %s: %d features", layer, len(features))
    return features


async def _get_page(client: httpx.AsyncClient, layer: str, start: int) -> dict[str, Any]:
    params: dict[str, str | int] = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": type_name(layer),
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "count": PAGE,
        "startIndex": start,
    }
    last_error: Exception | None = None
    for attempt in range(ATTEMPTS):
        try:
            response = await client.get(get_settings().shom_wfs_url, params=params, timeout=TIMEOUT)
            response.raise_for_status()
            if "json" not in response.headers.get("content-type", ""):
                raise RuntimeError(
                    f"{layer}: réponse non-JSON ({response.headers.get('content-type')}) — "
                    "vérifier outputFormat=application/json"
                )
            payload: dict[str, Any] = response.json()
            return payload
        except (httpx.HTTPError, RuntimeError) as exc:
            last_error = exc
            await asyncio.sleep(2**attempt)
    raise RuntimeError(f"SHOM WFS indisponible pour {layer}") from last_error


async def fetch_group(group: str, bbox: Bbox | None = None) -> dict[str, list[RawFeature]]:
    layers = GROUPS[group]
    async with httpx.AsyncClient(
        headers={"User-Agent": get_settings().overpass_user_agent}
    ) as client:
        result: dict[str, list[RawFeature]] = {}
        for layer in layers:
            features = await fetch_layer(client, layer)
            if bbox is not None:
                features = [feature for feature in features if bbox.contains(feature.geometry)]
            result[layer] = features
        return result
