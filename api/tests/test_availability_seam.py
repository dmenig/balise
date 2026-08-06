"""The seam tests (docs/13). Three cheap tests that keep pluggability real rather than aspirational.

If the first one needs more than swapping the provider to pass, the seam has rotted — and the fix
belongs in that PR, not "later". They run on every build for the whole life of v1.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from balise_api.domain.enums import ConfidenceBucket, SourceKind, SpotState
from balise_api.schemas.common import FieldStatusOut, StatusOut
from balise_api.schemas.spots import ObservationTrace
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

REPO_ROOT = Path(__file__).resolve().parents[2]
BBOX = "-3.0,47.4,-2.8,47.7"
AS_OF = datetime(2026, 8, 6, 13, 41, 30, tzinfo=UTC)

SEED = """
INSERT INTO source (id, kind, licence, attribution)
VALUES ('osm', 'import', 'odbl-1.0', '© OSM (ODbL)');

INSERT INTO harbour (id, slug, name, geom, phone, vhf_channel, source_id, external_ids,
                     attrs_provenance)
VALUES (1, 'port-test', 'Port de Test', ST_SetSRID(ST_MakePoint(-2.902, 47.541), 4326),
        '+33 2 97 00 00 00', 9, 'osm', '{"osm":"way/1"}', '{}');

INSERT INTO field (id, harbour_id, name, kind, capacity, source_id, external_ids)
VALUES (1, 1, 'Panne A', 'berth', 48, 'osm', '{"osm":"way/2"}');

INSERT INTO spot (id, field_id, harbour_id, kind, code, geom, depth_m, source_id, external_ids,
                  attrs_provenance)
VALUES
 (1, 1, 1, 'berth', 'A12', ST_SetSRID(ST_MakePoint(-2.9021, 47.5412), 4326), 2.4, 'osm',
  '{"osm":"node/1"}', '{"position":"osm"}'),
 (2, NULL, 1, 'mooring_buoy', 'B14', ST_SetSRID(ST_MakePoint(-2.9030, 47.5420), 4326), 1.2, 'osm',
  '{"osm":"node/2"}', '{"position":"osm"}');
"""


class FakeAvailabilityProvider:
    """Returns one known status and nothing else. Nothing else in the app changes."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self._session = session

    async def status_for(self, spot_ids: list[int]) -> dict[int, StatusOut]:
        return {
            spot_id: StatusOut(
                state=SpotState.FREE,
                confidence=0.9,
                bucket=ConfidenceBucket.CONFIRMED,
                as_of=AS_OF,
                source_kind=SourceKind.PORT_FEED,
                age_seconds=0,
            )
            for spot_id in spot_ids
        }

    async def observations_for(self, spot_id: int) -> list[ObservationTrace]:
        return [
            ObservationTrace(
                source_kind=SourceKind.PORT_FEED,
                state=SpotState.FREE,
                age_seconds=0,
                confidence=0.9,
            )
        ]

    async def field_status_for(self, field_ids: list[int]) -> dict[int, FieldStatusOut]:
        return {
            1: FieldStatusOut(
                free=5,
                capacity=48,
                confidence=0.9,
                as_of=AS_OF,
                source_kind=SourceKind.PORT_FEED,
            )
        }


@pytest.fixture(autouse=True)
async def seeded(session: AsyncSession) -> None:
    await session.execute(text(SEED))
    await session.commit()


@pytest.fixture
async def client_with_fake_provider(migrated_database: str) -> AsyncClient:
    from balise_api.main import create_app

    app = create_app()
    app.state.availability_provider_factory = FakeAvailabilityProvider  # the whole swap
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://testserver")


async def test_seam_carries_status_when_a_provider_is_wired(
    client_with_fake_provider: AsyncClient,
) -> None:
    async with client_with_fake_provider as client:
        body = (await client.get(f"/v1/spots?bbox={BBOX}")).json()
    assert body["features"][0]["properties"]["status"] == {
        "state": "free",
        "confidence": 0.9,
        "bucket": "confirmed",
        "as_of": "2026-08-06T13:41:30Z",
        "source_kind": "port_feed",
        "age_seconds": 0,
    }


async def test_the_seam_reaches_the_sheet_and_the_harbour_page_too(
    client_with_fake_provider: AsyncClient,
) -> None:
    """One swap must light up every surface, or the seam is only half a seam."""
    async with client_with_fake_provider as client:
        sheet = (await client.get("/v1/spots/spot_1")).json()
        harbour = (await client.get("/v1/harbours/port-test")).json()
    assert sheet["properties"]["status"]["state"] == "free"
    assert sheet["field"]["status"] == {
        "free": 5,
        "capacity": 48,
        "confidence": 0.9,
        "as_of": "2026-08-06T13:41:30Z",
        "source_kind": "port_feed",
    }
    assert harbour["fields"][0]["status"]["free"] == 5
    assert sheet["observations"] == [
        {"source_kind": "port_feed", "state": "free", "age_seconds": 0, "confidence": 0.9}
    ]


async def test_the_mooring_caveat_follows_whether_a_status_exists(
    client: AsyncClient, client_with_fake_provider: AsyncClient
) -> None:
    """v1 warns about the tackle; v2 warns that a report is not a state of the tackle."""
    v1 = (await client.get("/v1/spots/spot_2")).json()
    async with client_with_fake_provider as wired:
        v2 = (await wired.get("/v1/spots/spot_2")).json()
    assert v1["warnings"][0].startswith("Bouée recensée, pas un amarrage garanti")
    assert v2["warnings"][0].startswith("Disponibilité rapportée, pas un état de l'amarrage")


async def test_v1_serves_null_status_everywhere(client: AsyncClient) -> None:
    """The same surfaces, with the provider v1 actually wires."""
    listing = (await client.get(f"/v1/spots?bbox={BBOX}")).json()
    sheet = (await client.get("/v1/spots/spot_1")).json()
    harbour = (await client.get("/v1/harbours/port-test")).json()
    assert listing["features"][0]["properties"]["status"] is None
    assert sheet["properties"]["status"] is None
    assert sheet["field"]["status"] is None
    assert sheet["observations"] == []
    assert harbour["fields"][0]["status"] is None


async def test_v1_never_writes_to_availability_tables(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Exercise the v1 surface, then prove the 🔌 tables are still empty (docs/13)."""
    await client.get(f"/v1/spots?bbox={BBOX}")
    await client.get("/v1/spots/spot_1")
    await client.get("/v1/harbours/port-test")
    await client.get("/v1/harbours?q=Test")
    await client.get("/v1/tiles/spots/13/4029/2862.mvt")
    device = (await client.post("/v1/devices")).json()["device_token"]
    await client.post(
        "/v1/issues",
        json={
            "target": {"type": "spot", "id": "spot_1"},
            "kind": "wrong_position",
            "note": "la bouée est ~40 m plus au sud",
            "position": [-2.9024, 47.5407],
        },
        headers={"X-Device-Token": device},
    )
    await client.get("/v1/opendata/referential-osm.geojson")

    counts = {}
    for table in ("observation", "spot_status", "field_status", "feed"):
        result = await session.execute(text(f"SELECT count(*) FROM {table}"))
        counts[table] = int(result.scalar_one())
    assert counts == {"observation": 0, "spot_status": 0, "field_status": 0, "feed": 0}


def test_availability_flag_has_exactly_one_reference() -> None:
    """One switch, one place (docs/11). This is what stops the flag metastasising."""
    found = subprocess.run(
        ["grep", "-rn", "FEATURE_AVAILABILITY", "api/src"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    references = [line for line in found.stdout.splitlines() if line.strip()]
    assert len(references) == 1, references
    assert references[0].startswith("api/src/balise_api/main.py")
