"""Conflation and loading against real PostGIS (docs/13 priority #2).

Spatial matching cannot be mocked: a fake would test nothing. These tests are the guard on
"why did my buoy move" and on "never wipe the map when an upstream hiccups".
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from balise_api.domain.enums import SpotKind
from balise_ingest.conflate import TOLERANCE_M, explain, rank, wins
from balise_ingest.load import CountAnomaly, check_anomaly, load_batch
from balise_ingest.overrides import Overrides, Ref
from balise_ingest.records import (
    FieldRecord,
    HarbourRecord,
    NavAidRecord,
    NormalisedBatch,
    ServicePoint,
    SourceRecord,
    SpmPort,
    SpotRecord,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

OSM = SourceRecord(id="osm", kind="import", licence="odbl-1.0", attribution="© OSM (ODbL)")
SHOM = SourceRecord(
    id="shom.balisage", kind="import", licence="etalab-2.0", attribution="Shom, 2026"
)
ZMEL = SourceRecord(id="zmel.56", kind="import", licence="etalab-2.0", attribution="ZMEL 56")


def buoy(
    source: SourceRecord,
    external_id: str,
    lon: float = -2.9021,
    lat: float = 47.5412,
    **kwargs: object,
) -> SpotRecord:
    return SpotRecord(
        external_id=external_id,
        source_id=source.id,
        kind=SpotKind.MOORING_BUOY,
        lon=lon,
        lat=lat,
        attrs_provenance={"position": source.id, "kind": source.id},
        **kwargs,  # type: ignore[arg-type]
    )


def count(session: Session, table: str, where: str = "TRUE") -> int:
    return int(session.execute(text(f"SELECT count(*) FROM {table} WHERE {where}")).scalar_one())


def test_attribute_priority_follows_the_documented_table() -> None:
    # position of a mooring buoy: ZMEL (surveyed) > OSM > SHOM
    assert rank("position", "zmel.56") < rank("position", "osm") < rank("position", "shom.balisage")
    assert wins("depth_m", "shom.balisage", "osm") is True
    assert wins("depth_m", "osm", "shom.balisage") is False
    assert wins("code", "zmel.56", "osm") is True


def test_the_count_guard_only_fires_on_meaningful_moves() -> None:
    assert check_anomaly({"spots": 100}, {"spots": 95}) is None
    assert check_anomaly({"spots": 100}, {"spots": 50}) is not None
    # Tiny sources are noisy by nature and must not block a run.
    assert check_anomaly({"spots": 10}, {"spots": 2}) is None


def test_two_sources_describing_one_buoy_are_merged_and_logged(session_sync: Session) -> None:
    osm_batch = NormalisedBatch(source=OSM, spots=(buoy(OSM, "node/1", depth_m=Decimal("2.4")),))
    load_batch(session_sync, osm_batch, force=True)

    # 12 m away, within the 25 m mooring tolerance, surveyed by the département.
    zmel_batch = NormalisedBatch(
        source=ZMEL, spots=(buoy(ZMEL, "117", lon=-2.90226, lat=47.54126, code="117"),)
    )
    report = load_batch(session_sync, zmel_batch, force=True)

    assert report.conflated == 1
    assert count(session_sync, "spot") == 1
    row = session_sync.execute(
        text("SELECT external_ids, attrs_provenance, code, depth_m FROM spot")
    ).one()
    assert row.external_ids == {"osm": "node/1", "zmel.56": "117"}
    # ZMEL wins the position, OSM keeps the depth it alone provides.
    assert row.attrs_provenance["position"] == "zmel.56"
    assert (row.code, row.depth_m) == ("117", Decimal("2.4"))

    trace = explain(session_sync, "spot", 1)
    assert len(trace) == 2
    assert any("distance<=25m" in entry["rule"] for entry in trace)


def test_contradicting_codes_prevent_a_merge(session_sync: Session) -> None:
    load_batch(
        session_sync,
        NormalisedBatch(source=OSM, spots=(buoy(OSM, "node/1", code="B14"),)),
        force=True,
    )
    load_batch(
        session_sync,
        NormalisedBatch(
            source=ZMEL, spots=(buoy(ZMEL, "9", lon=-2.90215, lat=47.54122, code="B99"),)
        ),
        force=True,
    )
    assert count(session_sync, "spot") == 2


def test_distant_buoys_are_never_merged(session_sync: Session) -> None:
    load_batch(session_sync, NormalisedBatch(source=OSM, spots=(buoy(OSM, "node/1"),)), force=True)
    load_batch(
        session_sync,
        NormalisedBatch(source=ZMEL, spots=(buoy(ZMEL, "far", lon=-2.9100, lat=47.5500),)),
        force=True,
    )
    assert count(session_sync, "spot") == 2


def test_berths_use_a_tighter_tolerance_than_buoys() -> None:
    assert TOLERANCE_M[SpotKind.BERTH] < TOLERANCE_M[SpotKind.MOORING_BUOY]


def test_shom_wins_over_osm_for_nav_aids(session_sync: Session) -> None:
    shom_aid = NavAidRecord(
        external_id="FR1",
        source_id=SHOM.id,
        s57_class="boylat",
        lon=-2.9277,
        lat=47.5512,
        inspire_id="FR1",
        name="Kerpenhir",
        category="bâbord",
        raw={"inspireid": "FR1"},
    )
    load_batch(session_sync, NormalisedBatch(source=SHOM, nav_aids=(shom_aid,)), force=True)
    osm_aid = NavAidRecord(
        external_id="node/9",
        source_id=OSM.id,
        s57_class="boylat",
        lon=-2.92772,  # ~2 m away: the same mark
        lat=47.55121,
        name="Kerpenhir (OSM)",
        raw={},
    )
    report = load_batch(session_sync, NormalisedBatch(source=OSM, nav_aids=(osm_aid,)), force=True)

    assert report.rejected == 1
    assert count(session_sync, "nav_aid") == 1
    assert session_sync.execute(text("SELECT name FROM nav_aid")).scalar_one() == "Kerpenhir"


def test_an_osm_nav_aid_is_kept_where_shom_has_nothing(session_sync: Session) -> None:
    osm_aid = NavAidRecord(
        external_id="node/9",
        source_id=OSM.id,
        s57_class="bcnlat",
        lon=-1.5,
        lat=47.2,  # inland waters, no SHOM coverage
        raw={},
    )
    load_batch(session_sync, NormalisedBatch(source=OSM, nav_aids=(osm_aid,)), force=True)
    assert count(session_sync, "nav_aid") == 1
    assert session_sync.execute(text("SELECT inspire_id FROM nav_aid")).scalar_one() == "osm:node/9"


def test_reruns_are_idempotent(session_sync: Session) -> None:
    batch = NormalisedBatch(
        source=OSM,
        spots=(buoy(OSM, "node/1"),),
        fields=(
            FieldRecord(external_id="way/2", source_id=OSM.id, kind=SpotKind.BERTH, name="Panne A"),
        ),
        nav_aids=(
            NavAidRecord(
                external_id="node/9",
                source_id=OSM.id,
                s57_class="bcnlat",
                lon=-1.5,
                lat=47.2,
                raw={},
            ),
        ),
    )
    load_batch(session_sync, batch, force=True)
    second = load_batch(session_sync, batch, force=True)
    assert count(session_sync, "spot") == 1
    assert count(session_sync, "spot", "active") == 1
    # And the report says so: a re-run that inserts nothing must not claim inserts, or the ops
    # dashboards and the 20 % anomaly guard read a growth that never happened (docs/10).
    assert second.inserted == {}
    assert second.updated == {"spots": 1, "fields": 1, "nav_aids": 1}


def test_absence_deactivates_only_after_three_runs(session_sync: Session) -> None:
    present = NormalisedBatch(
        source=OSM, spots=(buoy(OSM, "node/1"), buoy(OSM, "node/2", lon=-2.95))
    )
    load_batch(session_sync, present, force=True)
    shrunk = NormalisedBatch(source=OSM, spots=(buoy(OSM, "node/1"),))
    for run in range(1, 4):
        report = load_batch(session_sync, shrunk, force=True)
        assert count(session_sync, "spot", "active") == (2 if run < 3 else 1)
    assert report.deactivated == 1
    # Nothing is ever deleted: the row survives, deactivated, with its provenance.
    assert count(session_sync, "spot") == 2


def test_a_collapsing_source_is_blocked_until_forced(session_sync: Session) -> None:
    many = NormalisedBatch(
        source=OSM,
        spots=tuple(buoy(OSM, f"node/{index}", lon=-2.90 - index / 1000) for index in range(60)),
    )
    load_batch(session_sync, many, force=True)
    collapsed = NormalisedBatch(source=OSM, spots=(buoy(OSM, "node/0"),))
    with pytest.raises(CountAnomaly):
        load_batch(session_sync, collapsed)
    assert count(session_sync, "spot", "active") == 60  # previous data kept

    load_batch(session_sync, collapsed, force=True)  # explicit human decision
    assert count(session_sync, "spot") == 60


def test_the_ref_version_is_bumped_so_tiles_invalidate(session_sync: Session) -> None:
    before = session_sync.execute(
        text("SELECT value FROM meta WHERE key = 'ref_version'")
    ).scalar_one()
    load_batch(session_sync, NormalisedBatch(source=OSM, spots=(buoy(OSM, "node/1"),)), force=True)
    after = session_sync.execute(
        text("SELECT value FROM meta WHERE key = 'ref_version'")
    ).scalar_one()
    assert int(after) == int(before) + 1


def test_overrides_blacklist_and_pin_positions() -> None:
    overrides = Overrides(
        blacklist=frozenset({Ref("osm", "node/2")}),
        pins={Ref("osm", "node/1"): (-2.90211, 47.54118)},
    )
    batch = NormalisedBatch(source=OSM, spots=(buoy(OSM, "node/1"), buoy(OSM, "node/2")))
    applied = overrides.apply(batch)
    assert [spot.external_id for spot in applied.spots] == ["node/1"]
    assert (applied.spots[0].lon, applied.spots[0].lat) == (-2.90211, 47.54118)


def test_a_forced_split_keeps_two_distinct_buoys(session_sync: Session) -> None:
    overrides = Overrides(
        splits=frozenset(
            {
                (Ref("zmel.56", "2222"), Ref("osm", "node/1")),
                (Ref("osm", "node/1"), Ref("zmel.56", "2222")),
            }
        )
    )
    load_batch(
        session_sync,
        NormalisedBatch(source=OSM, spots=(buoy(OSM, "node/1"),)),
        overrides=overrides,
        force=True,
    )
    load_batch(
        session_sync,
        NormalisedBatch(source=ZMEL, spots=(buoy(ZMEL, "2222", lon=-2.90212, lat=47.54121),)),
        overrides=overrides,
        force=True,
    )
    assert count(session_sync, "spot") == 2


def test_harbours_fields_services_and_tide_ports_are_wired_together(session_sync: Session) -> None:
    harbour = HarbourRecord(
        external_id="way/1",
        source_id=OSM.id,
        slug="port-du-crouesty",
        name="Port du Crouesty",
        lon=-2.8946,
        lat=47.5288,
        vhf_channel=9,
        services=("water",),
        attrs_provenance={"name": "osm"},
    )
    field = FieldRecord(
        external_id="way/2",
        source_id=OSM.id,
        kind=SpotKind.BERTH,
        name="Panne A",
        harbour_external_id="way/1",
        capacity=48,
    )
    spot = SpotRecord(
        external_id="node/5",
        source_id=OSM.id,
        kind=SpotKind.BERTH,
        lon=-2.89465,
        lat=47.52885,
        code="A12",
        attrs_provenance={"position": "osm"},
    )
    load_batch(
        session_sync,
        NormalisedBatch(
            source=OSM,
            harbours=(harbour,),
            fields=(field,),
            spots=(spot,),
            service_points=(
                ServicePoint(external_id="FRS1", service="fuel", lon=-2.8947, lat=47.5289),
            ),
            spm_ports=(SpmPort(key="PORT_NAVALO", name="Port-Navalo", lon=-2.895, lat=47.529),),
        ),
        force=True,
    )
    row = session_sync.execute(
        text("SELECT services, external_ids FROM harbour WHERE slug = 'port-du-crouesty'")
    ).one()
    assert sorted(row.services) == ["fuel", "water"]
    assert row.external_ids["shom_spm"] == "PORT_NAVALO"
    linked = session_sync.execute(
        text("SELECT harbour_id, field_id FROM spot WHERE code = 'A12'")
    ).one()
    # The berth is attached to its harbour by proximity. Its *field* stays unset on purpose: an OSM
    # pontoon carries no polygon, and guessing which panne a berth belongs to would invent data.
    # That link comes from the partner feed (`external_ids`) or from a ZMEL polygon — see below.
    assert linked.harbour_id is not None
    assert linked.field_id is None


def test_a_zmel_polygon_captures_the_buoys_inside_it(session_sync: Session) -> None:
    field = FieldRecord(
        external_id="zmel-56-1",
        source_id=ZMEL.id,
        kind=SpotKind.MOORING_BUOY,
        name="ZMEL de Port-Navalo",
        capacity=42,
        area_geojson={
            "type": "Polygon",
            "coordinates": [
                [
                    [-2.9100, 47.5400],
                    [-2.9100, 47.5500],
                    [-2.8900, 47.5500],
                    [-2.8900, 47.5400],
                    [-2.9100, 47.5400],
                ]
            ],
        },
    )
    inside = buoy(ZMEL, "117", lon=-2.9000, lat=47.5450, code="117")
    outside = buoy(ZMEL, "999", lon=-2.8000, lat=47.5450, code="999")
    load_batch(
        session_sync,
        NormalisedBatch(source=ZMEL, fields=(field,), spots=(inside, outside)),
        force=True,
    )
    rows: dict[str, int | None] = {
        row["code"]: row["field_id"]
        for row in session_sync.execute(
            text("SELECT code, field_id FROM spot ORDER BY code")
        ).mappings()
    }
    assert rows["117"] is not None
    assert rows["999"] is None
    # The field keeps its declared capacity: 42 buoys we cannot enumerate stay one field.
    capacity = session_sync.execute(text("SELECT capacity FROM field")).scalar_one()
    assert capacity == 42


def test_a_harbour_found_by_two_sources_is_one_harbour(session_sync: Session) -> None:
    osm_harbour = HarbourRecord(
        external_id="way/1",
        source_id=OSM.id,
        slug="port-du-crouesty",
        name="Port du Crouesty",
        lon=-2.8946,
        lat=47.5288,
        attrs_provenance={"name": "osm"},
    )
    shom_harbour = HarbourRecord(
        external_id="FR000010101400003",
        source_id="shom.ports",
        slug="port-du-crouesty",
        name="Port du Crouesty",
        lon=-2.8948,
        lat=47.5290,
        attrs_provenance={"name": "shom.ports", "position": "shom.ports"},
    )
    load_batch(session_sync, NormalisedBatch(source=OSM, harbours=(osm_harbour,)), force=True)
    shom_ports = SourceRecord(
        id="shom.ports", kind="import", licence="etalab-2.0", attribution="Shom, 2026"
    )
    report = load_batch(
        session_sync, NormalisedBatch(source=shom_ports, harbours=(shom_harbour,)), force=True
    )
    assert report.conflated == 1
    assert count(session_sync, "harbour") == 1
    row = session_sync.execute(text("SELECT name, external_ids FROM harbour")).one()
    # The operator/OSM name wins over SHOM's (docs/10 priority table).
    assert row.name == "Port du Crouesty"
    assert set(row.external_ids) == {"osm", "shom.ports"}
