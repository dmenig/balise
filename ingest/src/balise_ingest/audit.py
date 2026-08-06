"""`balise-audit` — data-quality checks run against production nightly, not in CI (docs/13).

Failures open an issue; they never page anyone at 3 a.m.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import typer
from balise_api.db import sync_session
from balise_api.queries.display import FREE_HARD_EXPIRY
from sqlalchemy import text
from sqlalchemy.orm import Session

app = typer.Typer(add_completion=False, help="Audit qualité des données Balise")


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    sql: str
    threshold: int
    unit: str = "lignes"
    #: 🔌 v2 checks only run once availability is switched on (docs/13).
    availability: bool = False


CHECKS: tuple[Check, ...] = (
    Check(
        "spots_without_provenance",
        "SELECT count(*) FROM spot WHERE source_id IS NULL OR attrs_provenance = '{}'::jsonb",
        0,
    ),
    Check(
        "navaids_without_class_label",
        "SELECT count(*) FROM nav_aid WHERE s57_class IS NULL OR s57_class = ''",
        0,
    ),
    Check(
        "spots_far_from_field",
        """
        SELECT count(*) FROM spot s JOIN field f ON f.id = s.field_id
        WHERE f.area IS NOT NULL
          AND ST_Distance(s.geom::geography, f.area::geography) > 500
        """,
        0,
    ),
    Check(
        "harbours_without_phone_and_vhf",
        """
        SELECT count(*) FROM harbour
        WHERE (phone IS NULL OR phone = '') AND vhf_channel IS NULL
        """,
        0,
    ),
    Check(
        "field_free_over_capacity",
        "SELECT count(*) FROM field_status WHERE capacity IS NOT NULL AND free_count > capacity",
        0,
        availability=True,
    ),
    Check(
        "stale_free_statuses",
        f"""
        SELECT count(*) FROM spot_status
        WHERE state = 'free' AND as_of < now() - interval '{FREE_HARD_EXPIRY}'
          AND confidence >= 0.4
        """,
        0,
        availability=True,
    ),
    Check(
        "duplicate_spots_within_10m",
        """
        SELECT count(*) FROM (
          SELECT a.id FROM spot a JOIN spot b
            ON a.id < b.id AND a.kind = b.kind AND a.active AND b.active
           AND ST_DWithin(a.geom::geography, b.geom::geography, 10)
        ) duplicates
        """,
        20,
    ),
    Check(
        "harbours_without_contact",
        """
        SELECT CASE WHEN count(*) = 0 THEN 0 ELSE
          (100 * count(*) FILTER (WHERE phone IS NULL AND email IS NULL AND website IS NULL)
           / count(*))::int END
        FROM harbour
        """,
        10,
        unit="%",
    ),
    Check(
        "navaids_with_status",
        """
        SELECT count(*) FROM spot_status st
        WHERE EXISTS (SELECT 1 FROM nav_aid n WHERE n.id = st.spot_id
                        AND NOT EXISTS (SELECT 1 FROM spot s WHERE s.id = st.spot_id))
        """,
        0,
        availability=True,
    ),
)


def run_checks(session: Session, *, availability: bool = False) -> list[dict[str, object]]:
    """v1 runs the referential checks; the 🔌 ones only make sense once statuses exist."""
    results: list[dict[str, object]] = []
    for check in CHECKS:
        if check.availability and not availability:
            continue
        value = int(session.execute(text(check.sql)).scalar_one())
        results.append(
            {
                "check": check.name,
                "value": value,
                "threshold": check.threshold,
                "unit": check.unit,
                "ok": value <= check.threshold,
            }
        )
    return results


@app.command("list-checks")
def list_checks() -> None:
    """What the nightly audit asserts, and against which threshold (docs/13)."""
    for check in CHECKS:
        scope = "🔌 v2" if check.availability else "v1"
        typer.echo(f"{scope:6} {check.name:34} ≤ {check.threshold} {check.unit}")


@app.command()
def run(fail_on_violation: bool = True, availability: bool = False) -> None:
    with sync_session() as session:
        results = run_checks(session, availability=availability)
    typer.echo(json.dumps({"checks": results}, ensure_ascii=False, indent=2))
    violations = [result for result in results if not result["ok"]]
    if violations and fail_on_violation:
        typer.echo(f"{len(violations)} contrôle(s) en échec")
        raise typer.Exit(1)


if __name__ == "__main__":  # pragma: no cover
    app()
