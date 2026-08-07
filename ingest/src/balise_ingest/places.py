"""Coastal places — the gazetteer the app's search box navigates by.

    uv run python -m balise_ingest.places --bbox=-5.4,47.15,-1.0,49.0 --out data

Not part of the référentiel: a sailor searches for *Quiberon* or *Belle-Île*, not for a buoy,
so the search box needs somewhere to send them. Places more than `NEAR_KM` from any charted
object are dropped, which leaves the coast and the islands and discards inland Brittany.
Islets are left out on purpose: 690 named rocks bury the 46 towns you actually search for.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from balise_api.config import get_settings

from balise_ingest.sources.osm import _post_overpass

#: Ranked by how far a sailor expects the camera to pull back for each.
PLACE_ZOOM: dict[str, float] = {
    "city": 11.5,
    "town": 12.5,
    "island": 12.0,
    "village": 13.5,
}
NEAR_KM = 5.0
logger = logging.getLogger("places")


def _query(bbox: str) -> str:
    west, south, east, north = (float(v) for v in bbox.split(","))
    box = f"{south},{west},{north},{east}"
    kinds = "|".join(PLACE_ZOOM)
    # Belle-Île, Groix, Bréhat and Ouessant are mapped as ways or relations, not nodes: querying
    # nodes alone silently drops every island a sailor actually navigates to.
    return f"""
    [out:json][timeout:300];
    (
      node["place"~"^({kinds})$"]["name"]({box});
      way["place"="island"]["name"]({box});
      relation["place"="island"]["name"]({box});
    );
    out tags center;
    """


def _point(element: dict[str, object]) -> tuple[float, float] | None:
    if "lon" in element and "lat" in element:
        return float(element["lon"]), float(element["lat"])  # type: ignore[arg-type]
    centre = element.get("center")
    if isinstance(centre, dict):
        return float(centre["lon"]), float(centre["lat"])
    return None


def fetch(bbox: str) -> pd.DataFrame:
    payload = _post_overpass(_query(bbox))
    rows = []
    for element in payload["elements"]:
        tags = element.get("tags") or {}
        point = _point(element)
        if not tags.get("name") or point is None:
            continue
        rows.append({"name": tags["name"], "kind": tags["place"], "lon": point[0], "lat": point[1]})
    frame = pd.DataFrame(rows)
    # An island mapped as both a node and a relation would otherwise appear twice.
    return frame.drop_duplicates(subset=["name", "kind"], keep="first")


def near_the_water(places: pd.DataFrame, objects: pd.DataFrame) -> pd.DataFrame:
    """Keep the places within `NEAR_KM` of a charted object — the rest are inland noise."""
    if places.empty:
        return places
    # Equirectangular is plenty at this scale and avoids a spatial index for 2k × 9k points.
    scale = np.cos(np.radians(48.0))
    px = places["lon"].to_numpy() * scale
    py = places["lat"].to_numpy()
    ox = objects["lon"].to_numpy() * scale
    oy = objects["lat"].to_numpy()
    limit = (NEAR_KM / 111.0) ** 2
    keep = [
        bool((((px[i] - ox) ** 2 + (py[i] - oy) ** 2) < limit).any()) for i in range(len(places))
    ]
    return places[keep].reset_index(drop=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bbox", required=True)
    parser.add_argument("--out", type=Path, default=Path("data"))
    arguments = parser.parse_args()
    get_settings()

    places = fetch(arguments.bbox)
    logger.info("overpass: %d places", len(places))
    objects = pd.concat(
        [
            pd.read_parquet(arguments.out / "points.parquet", columns=["lon", "lat"]),
            pd.read_parquet(arguments.out / "areas.parquet", columns=["lon", "lat"]),
        ]
    )
    coastal = near_the_water(places, objects).sort_values(["kind", "name"])
    coastal.to_parquet(arguments.out / "places.parquet", index=False, compression="zstd")
    logger.info(
        "gardé %d places côtières — %s", len(coastal), coastal["kind"].value_counts().to_dict()
    )


if __name__ == "__main__":
    main()
