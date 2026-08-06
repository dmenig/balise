"""MBFS validator (ADR-0004). This is the tool a vendor runs before ever talking to us, so its
verdicts must be exactly the ones production would give."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from balise_ingest.mbfs import validate_payload
from balise_ingest.mbfs.validator import Finding

NOW = datetime(2026, 8, 6, 13, 42, tzinfo=UTC)


def document(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "last_updated": NOW.isoformat().replace("+00:00", "Z"),
        "ttl": 60,
        "version": "0.1",
        "data": {
            "harbours": [
                {
                    "harbour_id": "FR-56-CROUESTY",
                    "fields": [
                        {
                            "field_id": "PANNE-A",
                            "capacity": 48,
                            "visitor_capacity": 12,
                            "num_free": 5,
                            "last_reported": NOW.isoformat().replace("+00:00", "Z"),
                            "spots": [
                                {"spot_id": "A12", "state": "free", "max_loa_m": 12.0},
                                {"spot_id": "A13", "state": "occupied"},
                            ],
                        }
                    ],
                }
            ]
        },
    }
    payload.update(overrides)
    return payload


def errors(findings: list[Finding]) -> list[str]:
    return [finding.path for finding in findings if finding.severity == "error"]


def test_the_documented_example_validates() -> None:
    findings = validate_payload(document(), NOW)
    assert errors(findings) == []
    assert "valide" in findings[0].message


def test_a_field_with_only_num_free_is_valid() -> None:
    payload = document()
    payload["data"]["harbours"][0]["fields"][0].pop("spots")
    assert errors(validate_payload(payload, NOW)) == []


def test_a_field_with_neither_count_nor_spots_is_rejected() -> None:
    payload = document()
    field = payload["data"]["harbours"][0]["fields"][0]
    field.pop("spots")
    field.pop("num_free")
    assert errors(validate_payload(payload, NOW)) == ["data.harbours[0].fields[0]"]


def test_more_free_than_capacity_is_rejected() -> None:
    payload = document()
    payload["data"]["harbours"][0]["fields"][0]["num_free"] = 60
    assert errors(validate_payload(payload, NOW)) == ["data.harbours[0].fields[0].num_free"]


def test_a_duplicate_spot_id_inside_a_field_is_rejected() -> None:
    payload = document()
    payload["data"]["harbours"][0]["fields"][0]["spots"].append({"spot_id": "A12", "state": "free"})
    assert errors(validate_payload(payload, NOW)) == ["data.harbours[0].fields[0].spots"]


def test_a_stale_document_is_rejected_because_a_dead_feed_must_not_look_alive() -> None:
    payload = document(last_updated=(NOW - timedelta(hours=4)).isoformat().replace("+00:00", "Z"))
    assert errors(validate_payload(payload, NOW)) == ["last_updated"]


def test_a_clock_in_the_future_is_rejected() -> None:
    payload = document(last_updated=(NOW + timedelta(hours=4)).isoformat().replace("+00:00", "Z"))
    assert errors(validate_payload(payload, NOW)) == ["last_updated"]


def test_an_unknown_state_is_a_schema_error() -> None:
    payload = document()
    payload["data"]["harbours"][0]["fields"][0]["spots"][0]["state"] = "peut-être"
    assert any("state" in path for path in errors(validate_payload(payload, NOW)))


def test_a_missing_ttl_is_a_schema_error() -> None:
    payload = document()
    payload.pop("ttl")
    assert errors(validate_payload(payload, NOW)) == ["ttl"]


def test_an_expired_reservation_is_only_a_warning() -> None:
    payload = document()
    payload["data"]["harbours"][0]["fields"][0]["spots"][1]["until"] = (
        (NOW - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    )
    findings = validate_payload(payload, NOW)
    assert errors(findings) == []
    assert any(finding.severity == "warning" for finding in findings)


def test_a_wrong_version_is_a_warning_not_a_rejection() -> None:
    findings = validate_payload(document(version="0.9"), NOW)
    assert errors(findings) == []
    assert any(finding.path == "version" for finding in findings)
