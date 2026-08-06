"""OSM tag mapping (docs/03 §B) on an Overpass payload shaped like the real thing."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from balise_api.domain.enums import SpotKind
from balise_ingest.normalisers import osm as normaliser
from balise_ingest.records import RawFeature
from balise_ingest.sources import osm

Loader = Callable[[str], Any]


def features(payload: dict[str, Any]) -> list[RawFeature]:
    out: list[RawFeature] = []
    for element in payload["elements"]:
        tags = element.get("tags") or {}
        lon, lat = osm._element_point(element)
        if lon is None or lat is None or not tags:
            continue
        out.append(
            RawFeature(
                external_id=f"{element['type']}/{element['id']}",
                layer="overpass",
                geometry={"type": "Point", "coordinates": [lon, lat]},
                properties=tags,
            )
        )
    return out


def test_the_full_payload_maps_to_the_expected_families(load_json: Loader) -> None:
    batch = normaliser.normalise(features(load_json("overpass_seamarks.json")))
    assert batch.counts() == {
        "nav_aids": 1,
        "harbours": 1,
        "fields": 1,
        "spots": 3,
        "service_points": 0,
        "spm_ports": 0,
    }
    assert batch.source.licence == "odbl-1.0"


def test_a_mooring_buoy_carries_the_boat_limits(load_json: Loader) -> None:
    batch = normaliser.normalise(features(load_json("overpass_seamarks.json")))
    buoy = next(spot for spot in batch.spots if spot.external_id == "node/1001")
    assert buoy.kind is SpotKind.MOORING_BUOY
    assert (buoy.code, buoy.max_draft_m, buoy.max_loa_m) == ("B14", Decimal("2.0"), Decimal("12"))
    assert buoy.visitor is True
    assert buoy.attrs_provenance["position"] == "osm"


def test_a_private_pile_is_not_offered_to_visitors(load_json: Loader) -> None:
    batch = normaliser.normalise(features(load_json("overpass_seamarks.json")))
    pile = next(spot for spot in batch.spots if spot.external_id == "node/1002")
    assert (pile.kind, pile.visitor, pile.code) == (SpotKind.PILE, False, "P3")


def test_an_anchorage_keeps_its_holding_and_depth(load_json: Loader) -> None:
    batch = normaliser.normalise(features(load_json("overpass_seamarks.json")))
    anchorage = next(spot for spot in batch.spots if spot.kind is SpotKind.ANCHORAGE)
    assert (anchorage.holding, anchorage.depth_m) == ("sand", Decimal("3.5"))


def test_a_marina_becomes_a_harbour_with_contacts_and_services(load_json: Loader) -> None:
    batch = normaliser.normalise(features(load_json("overpass_seamarks.json")))
    harbour = batch.harbours[0]
    assert (harbour.slug, harbour.name) == ("port-du-crouesty", "Port du Crouesty")
    assert (harbour.vhf_channel, harbour.phone) == (9, "+33 2 97 53 73 33")
    assert set(harbour.services) == {"water", "fuel", "showers"}
    assert harbour.attrs_provenance["name"] == "osm"


def test_a_pontoon_becomes_a_field_with_capacity(load_json: Loader) -> None:
    batch = normaliser.normalise(features(load_json("overpass_seamarks.json")))
    field = batch.fields[0]
    assert (field.kind, field.capacity, field.visitor_capacity) == (SpotKind.BERTH, 48, 12)
    assert field.operator == "SAGEMOR"


def test_a_lateral_buoy_becomes_a_nav_aid_with_a_french_category(load_json: Loader) -> None:
    batch = normaliser.normalise(features(load_json("overpass_seamarks.json")))
    nav_aid = batch.nav_aids[0]
    assert (nav_aid.s57_class, nav_aid.category, nav_aid.name) == (
        "boylat",
        "bâbord",
        "Le Grand Mouton",
    )
    assert nav_aid.light == {
        "osm_character": "Fl",
        "osm_colour": "red",
        "osm_period": "4",
        "osm_range": None,
    }


def test_non_maritime_objects_are_dropped(load_json: Loader) -> None:
    batch = normaliser.normalise(features(load_json("overpass_seamarks.json")))
    identifiers = {
        record.external_id
        for group in (batch.spots, batch.harbours, batch.nav_aids, batch.fields)
        for record in group
    }
    assert "node/1006" not in identifiers
