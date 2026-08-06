"""Golden-file tests on real SHOM payloads (docs/13).

The fixtures are verbatim WFS responses, trimmed to three features. When SHOM changes a schema the
diff here is explicit and reviewable — the earliest possible warning of a broken referential.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from balise_api.domain.enums import SpotKind
from balise_ingest.normalisers import shom as normaliser
from balise_ingest.records import RawFeature
from balise_ingest.s57_codes import UnknownS57Code, validate_layer
from balise_ingest.sources import shom

Loader = Callable[[str], Any]


def features_from(payload: dict[str, Any], layer: str) -> list[RawFeature]:
    return [
        RawFeature(
            external_id=str(feature["properties"].get("inspireid") or feature["id"]),
            layer=layer,
            geometry=feature.get("geometry"),
            properties=feature["properties"],
        )
        for feature in payload["features"]
    ]


def test_type_names_carry_the_right_namespace() -> None:
    assert shom.type_name("morfac") == "BALISAGE_BDD_WFS:morfac"
    assert shom.type_name("achare_point") == "REGLEMENTATION_NAVIGATION_BDD_WFS:achare_point"
    assert shom.type_name("hrbfac_point") == "INFORMATIONS_PORTUAIRES_BDD_WFS:hrbfac_point"
    with pytest.raises(KeyError):
        shom.type_name("nope")


def test_a_lateral_buoy_normalises_into_a_labelled_nav_aid(load_json: Loader) -> None:
    layers = {
        "boylat": features_from(load_json("shom_boylat.json"), "boylat"),
        "lights": features_from(load_json("shom_lights.json"), "lights"),
        "topmar": features_from(load_json("shom_topmar.json"), "topmar"),
    }
    batch = normaliser.normalise("balisage", layers, shom.SOURCES["balisage"])
    assert len(batch.nav_aids) == 3
    first = batch.nav_aids[0]
    assert first.s57_class == "boylat"
    assert first.source_id == "shom.balisage"
    assert first.category in {
        "bâbord",
        "tribord",
        "chenal préféré à bâbord",
        "chenal préféré à tribord",
    }
    assert first.colour  # decoded French colour, never a raw code
    assert first.raw, "the whole original properties object is kept (never lossy)"
    assert first.inspire_id == first.external_id


def test_morfac_becomes_a_spot_only_when_it_is_a_place_to_stop(load_json: Loader) -> None:
    layers = {"morfac": features_from(load_json("shom_morfac.json"), "morfac")}
    batch = normaliser.normalise("balisage", layers, shom.SOURCES["balisage"])
    kinds = {spot.kind for spot in batch.spots}
    assert kinds <= {SpotKind.MOORING_BUOY, SpotKind.PILE, SpotKind.QUAY}
    assert not batch.nav_aids, "a mooring facility is a spot, never a nav aid (docs/01)"
    for spot in batch.spots:
        assert spot.attrs_provenance == {
            "position": "shom.balisage",
            "kind": "shom.balisage",
        }


def test_anchorage_points_become_anchorage_spots(load_json: Loader) -> None:
    layers = {"achare_point": features_from(load_json("shom_achare_point.json"), "achare_point")}
    batch = normaliser.normalise("reglementation", layers, shom.SOURCES["reglementation"])
    assert {spot.kind for spot in batch.spots} == {SpotKind.ANCHORAGE}
    assert batch.source.licence == "etalab-2.0"


def test_unnamed_harbour_facilities_are_skipped_rather_than_slugged_badly(
    load_json: Loader,
) -> None:
    layers = {"hrbfac_point": features_from(load_json("shom_hrbfac_point.json"), "hrbfac_point")}
    batch = normaliser.normalise("ports", layers, shom.SOURCES["ports"])
    # The real payload has `objnam: null` on these three: no name, no slug, no harbour.
    assert batch.harbours == ()


def test_small_craft_facilities_become_harbour_services(load_json: Loader) -> None:
    layers = {"smcfac_point": features_from(load_json("shom_smcfac_point.json"), "smcfac_point")}
    batch = normaliser.normalise("ports", layers, shom.SOURCES["ports"])
    assert batch.service_points
    assert all(point.service for point in batch.service_points)


def test_spm_ports_provide_the_tide_join_key(load_json: Loader) -> None:
    layers = {
        "liste_ports_spm_h2m": features_from(
            load_json("shom_spm_ports.json"), "liste_ports_spm_h2m"
        )
    }
    batch = normaliser.normalise("spm", layers, shom.SOURCES["spm"])
    assert len(batch.spm_ports) == 3
    first = batch.spm_ports[0]
    assert first.key and first.name
    assert -180 <= first.lon <= 180


def test_heights_survive_as_decimals(load_json: Loader) -> None:
    layers = {"morfac": features_from(load_json("shom_morfac.json"), "morfac")}
    normaliser.normalise("balisage", layers, shom.SOURCES["balisage"])
    payload = load_json("shom_morfac.json")
    heights = [f["properties"].get("height") for f in payload["features"]]
    assert any(height is not None for height in heights)
    assert normaliser._decimal(heights[0]) in {None, Decimal(str(heights[0]))}


def test_an_unknown_code_in_a_real_layer_fails_the_job(load_json: Loader) -> None:
    payload = load_json("shom_boylat.json")
    properties = dict(payload["features"][0]["properties"])
    properties["catlam"] = 42
    with pytest.raises(UnknownS57Code):
        validate_layer("boylat", properties)


def test_bbox_filtering_keeps_only_local_features() -> None:
    box = shom.Bbox.parse("-3.2,47.4,-2.6,47.8")
    assert box.contains({"type": "Point", "coordinates": [-2.9, 47.55]}) is True
    assert box.contains({"type": "Point", "coordinates": [9.6, 42.2]}) is False
    assert box.contains(None) is False
    assert (
        box.contains(
            {"type": "Polygon", "coordinates": [[[-2.9, 47.55], [-2.89, 47.56], [-2.9, 47.55]]]}
        )
        is True
    )
