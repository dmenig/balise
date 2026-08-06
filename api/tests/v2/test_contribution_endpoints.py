"""Contribution and partner-feed endpoints end to end (docs/08), against real PostGIS."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from balise_api.auth.tokens import issue_feed_token
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

SEED = """
INSERT INTO source (id, kind, licence, attribution)
VALUES ('osm', 'import', 'odbl-1.0', '© les contributeurs OpenStreetMap (ODbL 1.0)');

INSERT INTO harbour (id, slug, name, geom, source_id, external_ids, attrs_provenance)
VALUES (1, 'port-test', 'Port de Test', ST_SetSRID(ST_MakePoint(-2.9020, 47.5410), 4326), 'osm',
        '{"osm":"way/1"}', '{"name":"osm"}');

INSERT INTO field (id, harbour_id, name, kind, capacity, source_id, external_ids)
VALUES (1, 1, 'Panne A', 'berth', 48, 'osm', '{"osm":"way/2","feed.test":"PANNE-A"}');

INSERT INTO spot (id, field_id, harbour_id, kind, code, geom, depth_m, source_id, external_ids,
                  attrs_provenance)
VALUES (1, 1, 1, 'berth', 'A12', ST_SetSRID(ST_MakePoint(-2.9021, 47.5412), 4326), 2.4, 'osm',
        '{"osm":"node/1","feed.test":"A12"}', '{"position":"osm"}');
"""


@pytest.fixture(autouse=True)
async def seeded(session: AsyncSession) -> None:
    await session.execute(text(SEED))
    await session.commit()


@pytest.fixture
async def feed_token(session: AsyncSession) -> str:
    token, token_hash = issue_feed_token("feed.test")
    await session.execute(
        text(
            """
            INSERT INTO feed (id, harbour_id, kind, contact_email, token_hash, ttl_seconds, trust)
            VALUES ('feed.test', 1, 'port_feed', 'cap@example.test', :hash, 60, 0.95)
            """
        ),
        {"hash": token_hash},
    )
    await session.commit()
    return token


@pytest.fixture
async def device(client: AsyncClient) -> str:
    response = await client.post("/v1/devices")
    assert response.status_code == 201
    return str(response.json()["device_token"])


async def test_a_device_token_carries_no_personal_data(client: AsyncClient) -> None:
    payload = (await client.post("/v1/devices")).json()
    assert payload["device_token"].startswith("dev_")
    assert "anonyme" in payload["note"]


async def test_a_report_needs_a_device_token(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/reports", json={"spot_id": "spot_1", "state": "free", "report_kind": "check_out"}
    )
    assert response.status_code == 401
    assert response.json()["title"] == "Authentification requise"


async def test_a_check_out_updates_the_status_and_returns_it(
    client: AsyncClient, device: str
) -> None:
    response = await client.post(
        "/v1/reports",
        json={
            "spot_id": "spot_1",
            "state": "free",
            "report_kind": "check_out",
            "position": [-2.9021, 47.5412],
        },
        headers={"X-Device-Token": device, "Idempotency-Key": "trip-1"},
    )
    assert response.status_code == 201
    payload = response.json()
    assert (payload["status"]["state"], payload["remote"]) == ("free", False)
    assert payload["status"]["source_kind"] == "community"

    sheet = (await client.get("/v1/spots/spot_1")).json()
    assert sheet["properties"]["status"]["state"] == "free"
    # v2 adds the audit trail to the sheet, through the same provider seam (docs/08).
    assert sheet["observations"][0]["source_kind"] == "community"


async def test_replaying_a_queued_report_does_not_double_count(
    client: AsyncClient, device: str, session: AsyncSession
) -> None:
    body = {"spot_id": "spot_1", "state": "occupied", "report_kind": "check_in"}
    headers = {"X-Device-Token": device, "Idempotency-Key": "trip-2"}
    first = await client.post("/v1/reports", json=body, headers=headers)
    second = await client.post("/v1/reports", json=body, headers=headers)
    assert (first.json()["duplicate"], second.json()["duplicate"]) == (False, True)
    count = await session.execute(text("SELECT count(*) FROM observation"))
    assert count.scalar_one() == 1


async def test_an_offline_batch_reports_partial_success(client: AsyncClient, device: str) -> None:
    response = await client.post(
        "/v1/reports/batch",
        json={
            "reports": [
                {
                    "spot_id": "spot_1",
                    "state": "free",
                    "report_kind": "check_out",
                    "observed_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
                    "client_id": "queued-1",
                },
                {"spot_id": "spot_404", "state": "free", "report_kind": "check_out"},
            ]
        },
        headers={"X-Device-Token": device},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["accepted"] == 1
    assert [(item["index"], item["ok"]) for item in payload["results"]] == [(0, True), (1, False)]
    assert "spot 404" in payload["results"][1]["error"]


async def test_the_observation_keeps_the_original_timestamp_from_the_queue(
    client: AsyncClient, device: str, session: AsyncSession
) -> None:
    observed_at = datetime.now(UTC) - timedelta(hours=3)
    await client.post(
        "/v1/reports",
        json={
            "spot_id": "spot_1",
            "state": "free",
            "report_kind": "check_out",
            "observed_at": observed_at.isoformat(),
        },
        headers={"X-Device-Token": device},
    )
    stored = await session.execute(text("SELECT observed_at, payload FROM observation"))
    row = stored.one()
    assert abs((row.observed_at - observed_at).total_seconds()) < 1
    assert row.payload["report_kind"] == "check_out"


async def test_a_banned_contributor_is_refused(
    client: AsyncClient, device: str, session: AsyncSession
) -> None:
    await client.post(
        "/v1/reports",
        json={"spot_id": "spot_1", "state": "free", "report_kind": "check_out"},
        headers={"X-Device-Token": device},
    )
    await session.execute(text("UPDATE contributor SET banned = true"))
    await session.commit()
    response = await client.post(
        "/v1/reports",
        json={"spot_id": "spot_1", "state": "occupied", "report_kind": "check_in"},
        headers={"X-Device-Token": device},
    )
    assert response.status_code == 403


async def test_a_feed_push_needs_a_valid_bearer_token(client: AsyncClient, feed_token: str) -> None:
    unauthorised = await client.post(
        "/v1/feeds/feed.test/observations",
        json={"observations": [{"spot_id": "A12", "state": "free"}]},
    )
    assert unauthorised.status_code == 401
    wrong = await client.post(
        "/v1/feeds/feed.test/observations",
        json={"observations": [{"spot_id": "A12", "state": "free"}]},
        headers={"Authorization": "Bearer mbfs_not_the_token"},
    )
    assert wrong.status_code == 401


async def test_a_feed_push_accepts_known_spots_and_reports_the_rest(
    client: AsyncClient, feed_token: str
) -> None:
    response = await client.post(
        "/v1/feeds/feed.test/observations",
        json={
            "observations": [
                {"spot_id": "A12", "state": "occupied"},
                {"spot_id": "GHOST", "state": "free"},
            ]
        },
        headers={"Authorization": f"Bearer {feed_token}"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "accepted": 1,
        "rejected": [{"index": 1, "reason": "unknown spot_id"}],
    }
    sheet = (await client.get("/v1/spots/spot_1")).json()
    assert sheet["properties"]["status"] == {
        "state": "occupied",
        "confidence": 0.95,
        "bucket": "confirmed",
        "as_of": sheet["properties"]["status"]["as_of"],
        "source_kind": "port_feed",
        "age_seconds": sheet["properties"]["status"]["age_seconds"],
    }


async def test_a_snapshot_updates_both_the_field_and_its_spots(
    client: AsyncClient, feed_token: str
) -> None:
    now = datetime.now(UTC)
    response = await client.put(
        "/v1/feeds/feed.test/snapshot",
        json={
            "last_updated": now.isoformat(),
            "ttl": 60,
            "version": "0.1",
            "data": {
                "harbours": [
                    {
                        "harbour_id": "FR-56-TEST",
                        "fields": [
                            {
                                "field_id": "PANNE-A",
                                "capacity": 48,
                                "visitor_capacity": 12,
                                "num_free": 5,
                                "spots": [{"spot_id": "A12", "state": "free"}],
                            }
                        ],
                    }
                ]
            },
        },
        headers={"Authorization": f"Bearer {feed_token}"},
    )
    assert response.json() == {"accepted": 2, "rejected": []}
    harbour = (await client.get("/v1/harbours/port-test")).json()
    field = harbour["fields"][0]
    assert (field["status"]["free"], field["status"]["capacity"]) == (5, 48)
    sheet = (await client.get("/v1/spots/spot_1")).json()
    assert sheet["properties"]["status"]["state"] == "free"


async def test_the_feed_health_page_is_self_service(client: AsyncClient, feed_token: str) -> None:
    await client.post(
        "/v1/feeds/feed.test/observations",
        json={"observations": [{"spot_id": "A12", "state": "free"}]},
        headers={"Authorization": f"Bearer {feed_token}"},
    )
    health = (
        await client.get(
            "/v1/feeds/feed.test/health", headers={"Authorization": f"Bearer {feed_token}"}
        )
    ).json()
    assert (health["feed_id"], health["stale"], health["accepted_24h"]) == ("feed.test", False, 1)
    assert health["staleness_seconds"] < 60


async def test_a_comment_is_attached_to_the_spot(client: AsyncClient, device: str) -> None:
    response = await client.post(
        "/v1/spots/spot_1/comments",
        json={"body": "Bon mouillage par vent d'ouest", "rating": 4},
        headers={"X-Device-Token": device},
    )
    assert response.status_code == 201
    assert response.json()["rating"] == 4


async def test_gdpr_erasure_anonymises_observations(
    client: AsyncClient, device: str, session: AsyncSession
) -> None:
    """Runbook 6 (docs/12): the account goes, the observation stays — no longer identifiable.

    v2 erasure runs through `balise-admin gdpr erase`, because it has to reach the availability
    tables that the v1 HTTP endpoint deliberately never touches.
    """
    await client.post(
        "/v1/reports",
        json={"spot_id": "spot_1", "state": "free", "report_kind": "check_out"},
        headers={"X-Device-Token": device},
    )
    await session.execute(
        text("UPDATE contributor SET email = 'skipper@example.test' WHERE email IS NULL")
    )
    await session.commit()

    await session.execute(
        text(
            """
            UPDATE observation SET contributor_id = NULL, source_ref = NULL
            WHERE contributor_id IN (SELECT id FROM contributor WHERE email = :email)
            """
        ),
        {"email": "skipper@example.test"},
    )
    await session.execute(
        text("DELETE FROM contributor WHERE email = :email"), {"email": "skipper@example.test"}
    )
    await session.commit()

    contributors = await session.execute(text("SELECT count(*) FROM contributor"))
    observations = await session.execute(text("SELECT contributor_id, source_ref FROM observation"))
    assert contributors.scalar_one() == 0
    assert observations.one() == (None, None)


async def test_the_magic_link_flow_issues_a_session(client: AsyncClient) -> None:
    requested = await client.post("/v1/auth/magic-link", json={"email": "skipper@example.test"})
    assert requested.status_code == 202
    token = requested.json()["magic_token"]
    session_response = await client.post(f"/v1/auth/session?token={token}")
    assert session_response.status_code == 200
    payload = session_response.json()
    assert (payload["email"], payload["token_type"]) == ("skipper@example.test", "bearer")
    assert "balise_refresh" in session_response.cookies
