"""The v1 API contract against a real PostGIS database (docs/13 priority #3).

Filters actually filter; `status` is always `null`; availability params and endpoints answer `501`.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

BBOX = "-3.0,47.4,-2.8,47.7"
MORBIHAN = (-2.9021, 47.5412)
AVAILABILITY_PROBLEM = {
    "type": "https://balise.fr/problems/availability-not-enabled",
    "title": "Availability is not enabled",
    "status": 501,
    "detail": "Live availability is not part of this release. See /a-propos/donnees.",
}

SEED = """
INSERT INTO source (id, kind, licence, attribution) VALUES
  ('shom.balisage', 'import', 'etalab-2.0', 'Shom, 2026 (Licence Ouverte Etalab 2.0)'),
  ('osm', 'import', 'odbl-1.0', '© les contributeurs OpenStreetMap (ODbL 1.0)');

INSERT INTO harbour (id, slug, name, geom, vhf_channel, phone, services, source_id,
                     external_ids, attrs_provenance)
VALUES (1, 'port-test', 'Port de Test', ST_SetSRID(ST_MakePoint(-2.9020, 47.5410), 4326), 9,
        '+33 2 97 00 00 00', ARRAY['water','fuel'], 'osm', '{"osm":"way/1"}',
        '{"name":"osm"}');

INSERT INTO field (id, harbour_id, name, kind, capacity, visitor_capacity,
                   price_per_night_cents, source_id, external_ids)
VALUES (1, 1, 'Panne A', 'berth', 48, 12, 2800, 'osm', '{"osm":"way/2"}');

INSERT INTO spot (id, field_id, harbour_id, kind, code, geom, depth_m, max_loa_m, max_draft_m,
                  visitor, exposure, source_id, external_ids, attrs_provenance)
VALUES
 (1, 1, 1, 'berth', 'A12', ST_SetSRID(ST_MakePoint(-2.9021, 47.5412), 4326), 2.4, 12.0, 2.0,
  true, ARRAY['NW'], 'osm', '{"osm":"node/1"}', '{"position":"osm"}'),
 (2, NULL, 1, 'mooring_buoy', 'B14', ST_SetSRID(ST_MakePoint(-2.9030, 47.5420), 4326), 1.2, 8.0,
  1.0, true, ARRAY['S','SW'], 'osm', '{"osm":"node/2"}', '{"position":"osm"}'),
 (3, NULL, NULL, 'anchorage', NULL, ST_SetSRID(ST_MakePoint(-2.9500, 47.6000), 4326), 5.0, NULL,
  NULL, false, ARRAY[]::text[], 'shom.balisage', '{"shom.balisage":"FR1"}',
  '{"position":"shom.balisage"}');

INSERT INTO nav_aid (id, inspire_id, s57_class, geom, name, colour, shape, topmark, category,
                     light, source_id, raw)
VALUES (1, 'FR000001264400001', 'boylat',
        ST_SetSRID(ST_MakePoint(-2.9277, 47.5512), 4326), 'Kerpenhir', 'rouge', 'cylindrique',
        'cylindre', 'bâbord',
        '{"litchr": 2, "colour": "3", "sigper": 4, "valnmr": 7}',
        'shom.balisage', '{"inspireid":"FR000001264400001"}');
"""


@pytest.fixture(autouse=True)
async def seeded(session: AsyncSession) -> None:
    await session.execute(text(SEED))
    await session.commit()


def tile_of(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    """Web-mercator tile containing a point — computed, never hardcoded."""
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    radians = math.radians(lat)
    y = int((1.0 - math.log(math.tan(radians) + 1 / math.cos(radians)) / math.pi) / 2.0 * n)
    return x, y


# --- the read surface -------------------------------------------------------


async def test_spots_returns_geojson_with_attribution_and_disclaimer(client: AsyncClient) -> None:
    response = await client.get(f"/v1/spots?bbox={BBOX}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    assert {feature["id"] for feature in payload["features"]} == {"spot_1", "spot_2", "spot_3"}
    assert payload["attribution"] == [
        "Shom, 2026 (Licence Ouverte Etalab 2.0)",
        "© les contributeurs OpenStreetMap (ODbL 1.0)",
    ]
    assert "Ne pas utiliser pour la navigation" in payload["disclaimer"]
    assert response.headers["etag"]


async def test_every_spot_carries_a_null_status_in_v1(client: AsyncClient) -> None:
    """The S3 seam: the key is present and null, so a v1 client keeps working in v2 (docs/08)."""
    payload = (await client.get(f"/v1/spots?bbox={BBOX}")).json()
    for feature in payload["features"]:
        assert "status" in feature["properties"]
        assert feature["properties"]["status"] is None


async def test_the_kind_filter_filters(client: AsyncClient) -> None:
    payload = (await client.get(f"/v1/spots?bbox={BBOX}&kind=mooring_buoy")).json()
    assert [feature["id"] for feature in payload["features"]] == ["spot_2"]


async def test_the_boat_filter_only_returns_spots_that_fit(client: AsyncClient) -> None:
    payload = (await client.get(f"/v1/spots?bbox={BBOX}&max_draft_m=1.8&max_loa_m=11")).json()
    # spot_2 takes 1.0 m draught / 8 m LOA: it does not fit an 11 m boat drawing 1.8 m.
    assert sorted(feature["id"] for feature in payload["features"]) == ["spot_1", "spot_3"]


async def test_the_shelter_filter_excludes_exposed_spots(client: AsyncClient) -> None:
    """« Abrité de secteur NW » must drop everything exposed to NW (docs/00 in scope)."""
    payload = (await client.get(f"/v1/spots?bbox={BBOX}&sheltered_from=NW")).json()
    assert sorted(feature["id"] for feature in payload["features"]) == ["spot_2", "spot_3"]
    both = (await client.get(f"/v1/spots?bbox={BBOX}&sheltered_from=NW,S")).json()
    assert [feature["id"] for feature in both["features"]] == ["spot_3"]


async def test_an_unknown_wind_sector_is_refused_with_a_readable_message(
    client: AsyncClient,
) -> None:
    response = await client.get(f"/v1/spots?bbox={BBOX}&sheltered_from=XX")
    assert response.status_code == 422
    assert "secteurs inconnus" in response.json()["detail"]


async def test_the_visitor_filter_filters(client: AsyncClient) -> None:
    payload = (await client.get(f"/v1/spots?bbox={BBOX}&visitor=true")).json()
    assert sorted(feature["id"] for feature in payload["features"]) == ["spot_1", "spot_2"]


async def test_sorting_by_price_puts_priced_spots_first(client: AsyncClient) -> None:
    payload = (await client.get(f"/v1/spots?bbox={BBOX}&sort=price")).json()
    assert payload["features"][0]["id"] == "spot_1"  # the only one with a price


async def test_an_oversized_bbox_is_refused(client: AsyncClient) -> None:
    response = await client.get("/v1/spots?bbox=-10,40,10,50")
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "bbox" in response.json()["detail"]


async def test_the_spot_sheet_is_complete_and_honest(client: AsyncClient) -> None:
    response = await client.get("/v1/spots/spot_2")
    payload = response.json()
    assert payload["properties"]["status"] is None
    assert payload["observations"] == []  # 🔌 v2 adds the trace
    # v1 warns about the tackle, not about a report it cannot have (docs/06 §A/S3).
    assert payload["warnings"][0].startswith("Bouée recensée, pas un amarrage garanti")
    assert not any("Disponibilité rapportée" in warning for warning in payload["warnings"])
    assert any("estimation" in warning for warning in payload["warnings"])
    assert payload["harbour"]["slug"] == "port-test"
    assert payload["harbour"]["phone"] == "+33 2 97 00 00 00"  # v1's answer to "is it free"
    assert payload["harbour"]["vhf_channel"] == 9


async def test_a_missing_spot_is_a_problem_document(client: AsyncClient) -> None:
    response = await client.get("/v1/spots/spot_999")
    assert response.status_code == 404
    assert response.json()["title"] == "Mouillage inconnu"


async def test_navaids_are_translated_and_never_carry_a_status(client: AsyncClient) -> None:
    payload = (await client.get("/v1/navaids/navaid_1")).json()
    assert payload["label"] == "Bouée latérale bâbord"
    assert payload["light"]["text"] == "Fl R 4s 7M"
    assert "bâbord" in payload["explainer"]
    assert "status" not in payload
    spots = (await client.get(f"/v1/spots?bbox={BBOX}")).json()
    assert all(not feature["id"].startswith("navaid") for feature in spots["features"])


async def test_harbour_search_and_sheet(client: AsyncClient) -> None:
    search = (await client.get("/v1/harbours?q=Test")).json()
    assert [item["slug"] for item in search["harbours"]] == ["port-test"]
    assert search["harbours"][0]["spot_count"] == 2
    near = (await client.get(f"/v1/harbours?near={MORBIHAN[0]},{MORBIHAN[1]}")).json()
    assert near["harbours"][0]["distance_nm"] == 0.01

    sheet = (await client.get("/v1/harbours/port-test")).json()
    assert (sheet["name"], sheet["vhf_channel"], sheet["spot_count"]) == ("Port de Test", 9, 2)
    assert sheet["services"] == ["water", "fuel"]
    assert [field["name"] for field in sheet["fields"]] == ["Panne A"]
    assert sheet["fields"][0]["capacity"] == 48
    assert sheet["fields"][0]["status"] is None  # 🔌 v2 adds free_count
    assert "free_spot_count" not in sheet


async def test_tiles_render_and_are_versioned(client: AsyncClient) -> None:
    x, y = tile_of(*MORBIHAN, 13)
    response = await client.get(f"/v1/tiles/spots/13/{x}/{y}.mvt")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.mapbox-vector-tile"
    assert response.headers["etag"] == f'W/"spots-0-13-{x}-{y}"'
    assert len(response.content) > 0
    # No status inside a tile, ever (ADR-0002, seam S4).
    assert b"free" not in response.content

    navaid_x, navaid_y = tile_of(-2.9277, 47.5512, 12)
    navaids = await client.get(f"/v1/tiles/navaids/12/{navaid_x}/{navaid_y}.mvt")
    assert navaids.status_code == 200 and len(navaids.content) > 0


async def test_a_tile_out_of_range_is_refused(client: AsyncClient) -> None:
    assert (await client.get("/v1/tiles/spots/4/1/1.mvt")).status_code == 404
    assert (await client.get("/v1/tiles/nope/13/4029/2862.mvt")).status_code == 404
    assert (await client.get("/v1/tiles/spots/13/99999/2862.mvt")).status_code == 404


async def test_conditional_requests_are_answered_with_304(client: AsyncClient) -> None:
    first = await client.get(f"/v1/spots?bbox={BBOX}")
    again = await client.get(
        f"/v1/spots?bbox={BBOX}", headers={"If-None-Match": first.headers["etag"]}
    )
    assert again.status_code == 304
    assert again.content == b""


async def test_v1_list_responses_are_cacheable_for_a_minute(client: AsyncClient) -> None:
    """60 s in v1; it drops to 10 s in v2 when status becomes volatile (docs/07)."""
    response = await client.get(f"/v1/spots?bbox={BBOX}")
    assert response.headers["cache-control"] == "public, max-age=60"


# --- the 🔌 availability surface: specified, refusing --------------------------


async def test_the_availability_state_filter_refuses_politely(client: AsyncClient) -> None:
    response = await client.get(f"/v1/spots?bbox={BBOX}&state=free")
    assert response.status_code == 501
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json() == AVAILABILITY_PROBLEM


async def test_the_min_confidence_filter_refuses_politely(client: AsyncClient) -> None:
    response = await client.get(f"/v1/spots?bbox={BBOX}&min_confidence=0.5")
    assert response.status_code == 501
    assert response.json() == AVAILABILITY_PROBLEM


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/v1/status?bbox=-3,47,-2,48", None),
        ("POST", "/v1/reports", {"spot_id": "spot_1", "state": "free"}),
        ("POST", "/v1/reports/batch", {"reports": []}),
        ("POST", "/v1/spots/spot_1/comments", {"body": "joli mouillage"}),
        ("POST", "/v1/uploads", None),
        ("POST", "/v1/feeds/feed.test/observations", {"observations": []}),
        (
            "PUT",
            "/v1/feeds/feed.test/snapshot",
            {
                "last_updated": "2026-08-06T13:42:00Z",
                "ttl": 60,
                "version": "0.1",
                "data": {"harbours": []},
            },
        ),
        ("GET", "/v1/feeds/feed.test/health", None),
        ("GET", "/v1/opendata/mbfs", None),
        ("GET", "/v1/opendata/stats.json", None),
    ],
)
async def test_every_availability_endpoint_is_specified_and_refuses(
    client: AsyncClient, method: str, path: str, body: dict[str, object] | None
) -> None:
    """Specified-and-refusing beats undefined (docs/06 §A/S3): documented 501, never a 404."""
    response = await client.request(method, path, json=body)
    assert response.status_code == 501, path
    assert response.json() == AVAILABILITY_PROBLEM


async def test_the_availability_surface_is_in_the_openapi_schema(client: AsyncClient) -> None:
    """A client generated from v1 types must already know these routes (docs/08)."""
    schema = (await client.get("/v1/openapi.json")).json()
    for path in ("/v1/status", "/v1/reports", "/v1/feeds/{feed_id}/observations"):
        assert path in schema["paths"], path


# --- the v1 contribution loop ------------------------------------------------


async def test_a_correction_lands_in_the_moderation_queue(
    client: AsyncClient, session: AsyncSession
) -> None:
    device = (await client.post("/v1/devices")).json()["device_token"]
    response = await client.post(
        "/v1/issues",
        json={
            "target": {"type": "spot", "id": "spot_1"},
            "kind": "wrong_position",
            "note": "la bouée est ~40 m plus au sud",
            "position": [-2.9024, 47.5407],
        },
        headers={"X-Device-Token": device},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["kind"] == "wrong_position"
    assert "revue" in payload["note"]

    row = (await session.execute(text("SELECT spot_id, category, body, payload FROM issue"))).one()
    assert (row.spot_id, row.category) == (1, "wrong_position")
    assert row.payload == {"target_type": "spot", "proposed_position": [-2.9024, 47.5407]}


async def test_a_correction_on_an_unknown_object_is_refused(client: AsyncClient) -> None:
    device = (await client.post("/v1/devices")).json()["device_token"]
    response = await client.post(
        "/v1/issues",
        json={"target": {"type": "spot", "id": "spot_9999"}, "kind": "removed", "note": "disparue"},
        headers={"X-Device-Token": device},
    )
    assert response.status_code == 404
    assert response.json()["title"] == "Objet inconnu"


async def test_a_correction_needs_a_device_token(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/issues",
        json={"target": {"type": "harbour", "id": "harbour_1"}, "kind": "other", "note": "test"},
    )
    assert response.status_code == 401


async def test_corrections_accept_every_documented_target(client: AsyncClient) -> None:
    device = (await client.post("/v1/devices")).json()["device_token"]
    for target, identifier in (
        ("spot", "spot_1"),
        ("harbour", "harbour_1"),
        ("navaid", "navaid_1"),
    ):
        response = await client.post(
            "/v1/issues",
            json={"target": {"type": target, "id": identifier}, "kind": "other", "note": "à voir"},
            headers={"X-Device-Token": device},
        )
        assert response.status_code == 202, target


async def test_gdpr_erasure_removes_the_account_and_keeps_the_correction(
    client: AsyncClient, session: AsyncSession
) -> None:
    device = (await client.post("/v1/devices")).json()["device_token"]
    await client.post(
        "/v1/issues",
        json={"target": {"type": "spot", "id": "spot_1"}, "kind": "other", "note": "à vérifier"},
        headers={"X-Device-Token": device},
    )
    response = await client.request("DELETE", "/v1/me", headers={"X-Device-Token": device})
    assert response.status_code == 202
    contributors = await session.execute(text("SELECT count(*) FROM contributor"))
    issues = await session.execute(text("SELECT contributor_id FROM issue"))
    assert contributors.scalar_one() == 0
    assert issues.scalar_one() is None


# --- environment and ops -----------------------------------------------------


async def test_the_tide_summary_computes_depth_at_low_water(
    client: AsyncClient, session: AsyncSession
) -> None:
    now = datetime.now(UTC)
    await session.execute(
        text(
            """
            INSERT INTO tide_prediction (harbour_id, at, height_m, kind, coefficient)
            VALUES (1, :hw, 5.20, 'HW', 78), (1, :lw, 1.10, 'LW', 78)
            """
        ),
        {"hw": now + timedelta(hours=2), "lw": now + timedelta(hours=8)},
    )
    await session.commit()
    detail = (await client.get("/v1/spots/spot_1")).json()
    tide = detail["tide"]
    assert tide["next_high_water"]["height_m"] == 5.2
    # 2.4 m charted + 1.10 m predicted = 3.5 m under the keel at low water.
    assert tide["depth_at_next_low_water_m"] == 3.5
    assert tide["is_estimate"] is True


async def test_health_and_readiness(client: AsyncClient) -> None:
    assert (await client.get("/health")).json() == {"status": "ok"}
    ready = (await client.get("/ready")).json()
    assert ready["database"] is True and ready["ref_version"] == "0"
    data = (await client.get("/v1/health/data")).json()
    assert {source["id"] for source in data["sources"]} == {"shom.balisage", "osm"}


async def test_the_open_data_export_only_contains_osm_derived_rows(client: AsyncClient) -> None:
    payload = (await client.get("/v1/opendata/referential-osm.geojson")).json()
    assert payload["licence"] == "ODbL-1.0"
    sources = {feature["properties"].get("source_id") for feature in payload["features"]}
    assert sources == {"osm"}


async def test_the_rate_limiter_refuses_a_flood_with_retry_after(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """60 req/min per IP in production (docs/08); here the limit is lowered to prove it bites."""
    from balise_api.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_anonymous_per_min", 2)
    statuses = [(await client.get("/v1/health")).status_code for _ in range(4)]
    assert 429 in statuses
    refused = await client.get("/v1/health")
    if refused.status_code == 429:
        assert refused.headers["retry-after"] == "60"
        assert refused.json()["title"] == "Trop de requêtes"


async def test_downloading_tiles_does_not_spend_the_readers_request_budget(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "Télécharger cette zone" is hundreds of tiles; it must not 429 the next sheet (docs/08)."""
    from balise_api.config import get_settings

    monkeypatch.setattr(get_settings(), "rate_limit_anonymous_per_min", 3)
    tiles = [
        (await client.get(f"/v1/tiles/spots/12/{2010 + offset}/1431.mvt")).status_code
        for offset in range(10)
    ]
    assert 429 not in tiles
    assert (await client.get("/v1/spots?bbox=-3.2,47.4,-2.6,47.8&limit=1")).status_code == 200
