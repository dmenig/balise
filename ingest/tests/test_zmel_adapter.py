"""ZMEL adapters (docs/10): polygons with a count, points per buoy, or just a site name."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from balise_api.domain.enums import SpotKind
from balise_ingest.adapters import adapter_for
from balise_ingest.records import RawFeature

Loader = Callable[[str], Any]


def features(payload: dict[str, Any]) -> list[RawFeature]:
    return [
        RawFeature(
            external_id=str(feature["id"]),
            layer="zmel-56",
            geometry=feature["geometry"],
            properties=feature["properties"],
        )
        for feature in payload["features"]
    ]


def test_a_polygon_with_a_buoy_count_becomes_one_field(load_json: Loader) -> None:
    adapter = adapter_for("56")
    polygon = features(load_json("zmel_56.geojson"))[0]
    fields = adapter.to_fields(polygon)
    assert len(fields) == 1
    field = fields[0]
    assert (field.name, field.capacity, field.visitor_capacity) == ("ZMEL de Port-Navalo", 42, 4)
    assert (field.kind, field.operator) == (SpotKind.MOORING_BUOY, "Commune d'Arzon")
    assert field.area_geojson is not None
    # A field of 42 buoys we cannot enumerate stays one field — never 42 invented spots.
    assert adapter.to_spots(polygon) == []


def test_a_point_per_buoy_becomes_a_spot_with_a_comma_decimal_depth(load_json: Loader) -> None:
    adapter = adapter_for("56")
    point = features(load_json("zmel_56.geojson"))[1]
    spots = adapter.to_spots(point)
    assert len(spots) == 1
    spot = spots[0]
    assert (spot.code, spot.depth_m, spot.kind) == ("17", Decimal("2.4"), SpotKind.MOORING_BUOY)
    assert spot.source_id == "zmel.56"
    assert adapter.to_fields(point) == []


def test_a_site_with_only_a_name_still_yields_a_field(load_json: Loader) -> None:
    adapter = adapter_for("56")
    multipolygon = features(load_json("zmel_56.geojson"))[2]
    field = adapter.to_fields(multipolygon)[0]
    assert (field.name, field.capacity) == ("Zone de mouillage du Logeo", None)


def test_the_five_densest_departements_are_registered() -> None:
    for dept in ("56", "29", "22", "17", "83"):
        assert adapter_for(dept).dataset_slug
    with pytest.raises(KeyError):
        adapter_for("99")
