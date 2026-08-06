"""The nightly data-quality audit (docs/13). It runs against production, so every check must be
expressible in one honest SQL statement and must not page anyone at 3 a.m."""

from __future__ import annotations

import pytest
from balise_ingest.audit import CHECKS, run_checks
from sqlalchemy import text
from sqlalchemy.orm import Session

SEED = """
INSERT INTO source (id, kind, licence, attribution)
VALUES ('osm', 'import', 'odbl-1.0', '© OSM (ODbL)');

INSERT INTO harbour (id, slug, name, geom, phone, source_id, external_ids, attrs_provenance)
VALUES (1, 'port-test', 'Port de Test', ST_SetSRID(ST_MakePoint(-2.902, 47.541), 4326),
        '+33 2 97 00 00 00', 'osm', '{"osm":"way/1"}', '{}');

INSERT INTO field (id, harbour_id, name, kind, capacity, source_id, external_ids, area)
VALUES (1, 1, 'ZMEL', 'mooring_buoy', 42, 'osm', '{"osm":"way/2"}',
        ST_Multi(ST_GeomFromText('POLYGON((-2.91 47.54, -2.91 47.55, -2.89 47.55, -2.89 47.54,
                                           -2.91 47.54))', 4326)));

INSERT INTO spot (id, field_id, harbour_id, kind, code, geom, source_id, external_ids,
                  attrs_provenance)
VALUES (1, 1, 1, 'mooring_buoy', 'B14', ST_SetSRID(ST_MakePoint(-2.9000, 47.5450), 4326), 'osm',
        '{"osm":"node/1"}', '{"position":"osm"}');

-- Explicit ids do not advance the sequences: keep them in step so later inserts work.
SELECT setval(pg_get_serial_sequence('spot', 'id'), (SELECT max(id) FROM spot));
SELECT setval(pg_get_serial_sequence('field', 'id'), (SELECT max(id) FROM field));
SELECT setval(pg_get_serial_sequence('harbour', 'id'), (SELECT max(id) FROM harbour));
"""


@pytest.fixture(autouse=True)
def seeded(session_sync: Session) -> None:
    session_sync.execute(text(SEED))
    session_sync.commit()


def results(session_sync: Session) -> dict[str, dict[str, object]]:
    return {str(row["check"]): row for row in run_checks(session_sync)}


def test_a_clean_referential_passes_every_v1_check(session_sync: Session) -> None:
    outcome = results(session_sync)
    assert len(outcome) == len([check for check in CHECKS if not check.availability])
    assert all(row["ok"] for row in outcome.values()), outcome


def test_the_availability_checks_are_skipped_in_v1(session_sync: Session) -> None:
    """They cannot fire on empty tables, and pretending to run them would be theatre (docs/13)."""
    assert "field_free_over_capacity" not in results(session_sync)
    with_availability = {row["check"]: row for row in run_checks(session_sync, availability=True)}
    assert with_availability["field_free_over_capacity"]["ok"] is True


def test_a_harbour_reachable_by_neither_phone_nor_vhf_is_caught(session_sync: Session) -> None:
    """In v1 the phone *is* the availability feature (docs/13), so this one is a zero-tolerance."""
    assert results(session_sync)["harbours_without_phone_and_vhf"]["ok"] is True
    session_sync.execute(text("UPDATE harbour SET phone = NULL, vhf_channel = NULL"))
    session_sync.commit()
    assert results(session_sync)["harbours_without_phone_and_vhf"]["ok"] is False


def test_a_spot_without_provenance_is_caught(session_sync: Session) -> None:
    session_sync.execute(text("UPDATE spot SET attrs_provenance = '{}'::jsonb WHERE id = 1"))
    session_sync.commit()
    assert results(session_sync)["spots_without_provenance"]["ok"] is False


def test_a_spot_far_from_its_field_is_caught(session_sync: Session) -> None:
    session_sync.execute(
        text("UPDATE spot SET geom = ST_SetSRID(ST_MakePoint(-2.80, 47.60), 4326) WHERE id = 1")
    )
    session_sync.commit()
    assert results(session_sync)["spots_far_from_field"]["ok"] is False


def test_more_free_than_capacity_is_caught_even_though_the_constraint_exists(
    session_sync: Session,
) -> None:
    # The database refuses it, which is the real guard; the audit proves the guard is on.
    with pytest.raises(Exception, match="ck_field_status_capacity"):
        session_sync.execute(
            text(
                """
                INSERT INTO field_status (field_id, free_count, capacity, confidence, as_of,
                                          source_kind)
                VALUES (1, 60, 48, 0.9, now(), 'port_feed')
                """
            )
        )
    session_sync.rollback()


def test_a_stale_free_status_is_caught(session_sync: Session) -> None:
    session_sync.execute(
        text(
            """
            INSERT INTO spot_status (spot_id, state, confidence, as_of, source_kind)
            VALUES (1, 'free', 0.9, now() - interval '10 hours', 'community')
            """
        )
    )
    session_sync.commit()
    stale = {row["check"]: row for row in run_checks(session_sync, availability=True)}
    assert stale["stale_free_statuses"]["ok"] is False


def test_duplicate_spots_within_ten_metres_are_counted_with_a_tolerance(
    session_sync: Session,
) -> None:
    session_sync.execute(
        text(
            """
            INSERT INTO spot (field_id, harbour_id, kind, code, geom, source_id, external_ids,
                              attrs_provenance)
            VALUES (1, 1, 'mooring_buoy', 'B15',
                    ST_SetSRID(ST_MakePoint(-2.90005, 47.54502), 4326), 'osm',
                    '{"osm":"node/2"}', '{"position":"osm"}')
            """
        )
    )
    session_sync.commit()
    duplicates = results(session_sync)["duplicate_spots_within_10m"]
    assert duplicates["value"] == 1
    assert duplicates["ok"] is True  # under the national tolerance of 20


def test_harbours_without_contact_are_measured_as_a_percentage(session_sync: Session) -> None:
    session_sync.execute(text("UPDATE harbour SET phone = NULL"))
    session_sync.commit()
    contacts = results(session_sync)["harbours_without_contact"]
    assert (contacts["value"], contacts["unit"], contacts["ok"]) == (100, "%", False)
