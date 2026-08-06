"""The decay worker (docs/07): nothing new arriving is itself information.

A silent port feed must go `unknown`, and a stale community "free" must stop being green even
though no new observation ever arrives to say so.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from balise_workers.status_worker import recompute_decay, reset_feed_counters, sweep_stale_feeds
from sqlalchemy import text
from sqlalchemy.orm import Session

SEED = """
INSERT INTO source (id, kind, licence, attribution)
VALUES ('osm', 'import', 'odbl-1.0', '© OSM (ODbL)');

INSERT INTO harbour (id, slug, name, geom, source_id, external_ids, attrs_provenance)
VALUES (1, 'port-test', 'Port de Test', ST_SetSRID(ST_MakePoint(-2.902, 47.541), 4326), 'osm',
        '{"osm":"way/1"}', '{}');

INSERT INTO spot (id, harbour_id, kind, code, geom, source_id, external_ids, attrs_provenance)
VALUES (1, 1, 'mooring_buoy', 'B14', ST_SetSRID(ST_MakePoint(-2.9021, 47.5412), 4326), 'osm',
        '{"osm":"node/1"}', '{"position":"osm"}'),
       (2, 1, 'berth', 'A12', ST_SetSRID(ST_MakePoint(-2.9030, 47.5420), 4326), 'osm',
        '{"osm":"node/2"}', '{"position":"osm"}');

INSERT INTO contributor (id, device_hash, reputation) VALUES (1, 'hash-a', 1.0);
"""


@pytest.fixture(autouse=True)
def seeded(session: Session) -> None:
    session.execute(text(SEED))
    session.commit()


def add_observation(
    session: Session,
    spot_id: int,
    state: str,
    age: timedelta,
    *,
    source: str = "community",
    report_kind: str = "check_out",
    confidence: float = 0.55,
    source_ref: str = "hash-a",
) -> None:
    session.execute(
        text(
            """
            INSERT INTO observation (spot_id, state, source_kind, source_ref, contributor_id,
                                     observed_at, confidence, payload)
            VALUES (:spot_id, CAST(:state AS spot_state), CAST(:source AS source_kind), :source_ref,
                    CASE WHEN :source = 'community' THEN 1 ELSE NULL END,
                    now() - :age, :confidence, CAST(:payload AS jsonb))
            """
        ),
        {
            "spot_id": spot_id,
            "state": state,
            "source": source,
            "source_ref": source_ref,
            "age": age,
            "confidence": confidence,
            "payload": f'{{"report_kind": "{report_kind}"}}',
        },
    )
    session.commit()


def set_status(
    session: Session, spot_id: int, state: str, confidence: float, age: timedelta
) -> None:
    session.execute(
        text(
            """
            INSERT INTO spot_status (spot_id, state, confidence, as_of, source_kind, updated_at)
            VALUES (:spot_id, CAST(:state AS spot_state), :confidence, now() - :age, 'community',
                    now() - interval '10 minutes')
            ON CONFLICT (spot_id) DO UPDATE SET state = EXCLUDED.state,
                confidence = EXCLUDED.confidence, as_of = EXCLUDED.as_of,
                updated_at = EXCLUDED.updated_at
            """
        ),
        {"spot_id": spot_id, "state": state, "confidence": confidence, "age": age},
    )
    session.commit()


def status_of(session: Session, spot_id: int) -> tuple[str, float]:
    row = session.execute(
        text("SELECT state::text, confidence FROM spot_status WHERE spot_id = :id"),
        {"id": spot_id},
    ).one()
    return row[0], float(row[1])


def test_a_stale_free_is_recomputed_down_without_any_new_observation(session: Session) -> None:
    add_observation(session, 1, "free", timedelta(minutes=135))
    set_status(session, 1, "free", 0.55, timedelta(minutes=135))

    report = recompute_decay(session, datetime.now(UTC))
    session.commit()

    assert report.checked == 1
    state, confidence = status_of(session, 1)
    assert state == "free"
    assert confidence < 0.4  # below the display gate: the map stops showing it as free


def test_a_hard_expired_observation_leaves_the_spot_unknown(session: Session) -> None:
    add_observation(session, 1, "free", timedelta(hours=9))
    set_status(session, 1, "free", 0.55, timedelta(hours=9))
    recompute_decay(session, datetime.now(UTC))
    session.commit()
    assert status_of(session, 1)[0] == "unknown"


def test_a_fresh_status_keeps_its_confidence(session: Session) -> None:
    add_observation(session, 1, "occupied", timedelta(minutes=2), report_kind="check_in")
    set_status(session, 1, "occupied", 0.55, timedelta(minutes=2))
    recompute_decay(session, datetime.now(UTC))
    session.commit()
    state, confidence = status_of(session, 1)
    assert (state, confidence) == ("occupied", 0.55)


def test_a_suppressed_observation_stops_counting(session: Session) -> None:
    add_observation(session, 1, "free", timedelta(minutes=5))
    set_status(session, 1, "free", 0.55, timedelta(minutes=5))
    session.execute(text("UPDATE observation SET suppressed = true"))
    session.commit()
    recompute_decay(session, datetime.now(UTC))
    session.commit()
    assert status_of(session, 1)[0] == "unknown"


def test_a_silent_feed_turns_its_spots_unknown_not_green(session: Session) -> None:
    session.execute(
        text(
            """
            INSERT INTO feed (id, harbour_id, kind, contact_email, token_hash, ttl_seconds,
                              last_seen_at)
            VALUES ('feed.test', 1, 'port_feed', 'cap@example.test', 'hash', 60,
                    now() - interval '10 minutes')
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO spot_status (spot_id, state, confidence, as_of, source_kind)
            VALUES (2, 'free', 0.95, now() - interval '10 minutes', 'port_feed')
            """
        )
    )
    session.commit()

    result = sweep_stale_feeds(session)
    session.commit()

    assert result == {"feed.test": 1}
    assert status_of(session, 2) == ("unknown", 0.0)


def test_a_live_feed_is_left_alone(session: Session) -> None:
    session.execute(
        text(
            """
            INSERT INTO feed (id, harbour_id, kind, contact_email, token_hash, ttl_seconds,
                              last_seen_at)
            VALUES ('feed.live', 1, 'port_feed', 'cap@example.test', 'hash', 60, now())
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO spot_status (spot_id, state, confidence, as_of, source_kind)
            VALUES (2, 'free', 0.95, now(), 'port_feed')
            """
        )
    )
    session.commit()
    assert sweep_stale_feeds(session) == {}
    assert status_of(session, 2) == ("free", 0.95)


def test_feed_counters_are_reset_once_a_day(session: Session) -> None:
    session.execute(
        text(
            """
            INSERT INTO feed (id, harbour_id, kind, contact_email, token_hash, accepted_24h,
                              rejected_24h, last_seen_at)
            VALUES ('feed.old', 1, 'port_feed', 'cap@example.test', 'hash', 500, 3,
                    now() - interval '30 hours')
            """
        )
    )
    session.commit()
    reset_feed_counters(session)
    session.commit()
    row = session.execute(text("SELECT accepted_24h, rejected_24h FROM feed")).one()
    assert row == (0, 0)


def test_the_recompute_emits_a_notify_for_the_websocket_relay(session: Session) -> None:
    add_observation(session, 1, "free", timedelta(minutes=5))
    set_status(session, 1, "free", 0.55, timedelta(minutes=5))
    session.execute(text("LISTEN status_changed"))
    session.commit()
    recompute_decay(session, datetime.now(UTC))
    session.commit()
    connection = session.connection().connection.driver_connection
    notifications = list(connection.notifies(timeout=1, stop_after=1))  # type: ignore[union-attr]
    assert notifications
    assert "spot_1" in notifications[0].payload
